import json

import pytest
import requests

from claude_tracker.providers import nanogpt

SAMPLE = {
    "active": True,
    "state": "active",
    "limits": {"weeklyInputTokens": 60000000, "dailyInputTokens": None, "dailyImages": 100},
    "period": {"currentPeriodEnd": "2026-10-11T04:18:21.000Z"},
    "weeklyInputTokens": {"used": 631288, "remaining": 59368712,
                          "percentUsed": 0.010521466666666666, "resetAt": 1791763200000},
    "dailyInputTokens": None,
    "dailyImages": {"used": 0, "remaining": 100, "percentUsed": 0, "resetAt": 1791244800000},
}


def make_response(status: int, body: bytes) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = body
    resp.url = nanogpt.USAGE_URL
    return resp


def test_parse_sample():
    usage = nanogpt.parse_usage(SAMPLE)
    assert usage.provider_id == "nanogpt"
    assert usage.error is None
    assert [b.label for b in usage.buckets] == ["Weekly tokens", "Daily images"]
    assert [b.short for b in usage.buckets] == ["Wk", "Img"]
    weekly, images = usage.buckets
    assert weekly.utilization == pytest.approx(1.0521, rel=1e-3)
    assert weekly.detail == "0.63M / 60M"
    assert weekly.resets_at.timestamp() == 1791763200
    assert images.detail == "0 / 100"
    assert usage.subtitle.startswith("renews Oct ")


def test_parse_inactive():
    usage = nanogpt.parse_usage({**SAMPLE, "active": False})
    assert usage.buckets == []
    assert usage.error == "No active NanoGPT subscription"


def test_overage_and_garbage_percent():
    data = json.loads(json.dumps(SAMPLE))
    data["weeklyInputTokens"]["percentUsed"] = 1.25
    data["dailyImages"]["percentUsed"] = "n/a"
    weekly, images = nanogpt.parse_usage(data).buckets
    assert weekly.utilization == pytest.approx(125.0)
    assert images.utilization == 0.0


def test_missing_reset_at():
    data = json.loads(json.dumps(SAMPLE))
    data["dailyImages"]["resetAt"] = None
    images = nanogpt.parse_usage(data).buckets[1]
    assert images.resets_at is None
    assert images.time_until_reset == ""


def test_fetch_empty_key_skips_request(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("must not call the API")
    monkeypatch.setattr(nanogpt.requests, "get", boom)
    assert nanogpt.fetch("   ").error == nanogpt.NO_KEY_MESSAGE


def test_fetch_strips_key(monkeypatch):
    seen = {}

    def fake_get(url, headers, timeout):
        seen["key"] = headers["x-api-key"]
        return make_response(200, json.dumps(SAMPLE).encode())
    monkeypatch.setattr(nanogpt.requests, "get", fake_get)
    usage = nanogpt.fetch("  sk-nano-test\n")
    assert seen["key"] == "sk-nano-test"
    assert usage.error is None
    assert len(usage.buckets) == 2


@pytest.mark.parametrize("status", [401, 403])
def test_fetch_rejected_key(monkeypatch, status):
    monkeypatch.setattr(nanogpt.requests, "get",
                        lambda *a, **kw: make_response(status, b'{"error":"unauthorized"}'))
    assert nanogpt.fetch("sk-nano-test").error == "NanoGPT key rejected. Update it in Settings."


def test_fetch_http_error_html_body(monkeypatch):
    monkeypatch.setattr(nanogpt.requests, "get",
                        lambda *a, **kw: make_response(502, b"<html>Bad gateway</html>"))
    assert nanogpt.fetch("sk-nano-test").error == "NanoGPT API error: HTTP 502"


def test_fetch_non_json_200(monkeypatch):
    monkeypatch.setattr(nanogpt.requests, "get",
                        lambda *a, **kw: make_response(200, b"<html>maintenance</html>"))
    assert nanogpt.fetch("sk-nano-test").error.startswith("NanoGPT API error: ")


def test_fetch_network_error(monkeypatch):
    def raise_timeout(*a, **kw):
        raise requests.ConnectTimeout("timed out")
    monkeypatch.setattr(nanogpt.requests, "get", raise_timeout)
    assert nanogpt.fetch("sk-nano-test").error == "NanoGPT API error: ConnectTimeout"
