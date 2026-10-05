"""NanoGPT subscription usage provider."""

import logging
from datetime import datetime, timezone

import requests

from claude_tracker.providers.base import ProviderUsage, UsageBucket, format_amount

log = logging.getLogger(__name__)

PROVIDER_ID = "nanogpt"
USAGE_URL = "https://nano-gpt.com/api/subscription/v1/usage"

KEY_REJECTED_MESSAGE = "NanoGPT key rejected. Update it in Settings."
INACTIVE_MESSAGE = "No active NanoGPT subscription"
NO_KEY_MESSAGE = "Enter an API key"

# (response key, popup label, tooltip label), in display order.
_BUCKETS = (
    ("weeklyInputTokens", "Weekly tokens", "Wk"),
    ("dailyInputTokens", "Daily tokens", "Day"),
    ("dailyImages", "Daily images", "Img"),
)


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ms_to_dt(value) -> datetime | None:
    if not isinstance(value, (int, float)):
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


def _renews(period: dict) -> str:
    raw = period.get("currentPeriodEnd")
    if not raw:
        return ""
    try:
        end = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return ""
    return f"renews {end:%b} {end.day}"


def parse_usage(data: dict) -> ProviderUsage:
    if not data.get("active"):
        return ProviderUsage(PROVIDER_ID, [], error=INACTIVE_MESSAGE)
    limits = data.get("limits") or {}
    buckets = []
    for key, label, short in _BUCKETS:
        bucket = data.get(key)
        if not isinstance(bucket, dict):
            continue  # plan has no such limit
        limit = _to_float(limits.get(key))
        detail = format_amount(_to_float(bucket.get("used")), limit) if limit else ""
        buckets.append(UsageBucket(
            label=label,
            short=short,
            utilization=max(0.0, _to_float(bucket.get("percentUsed")) * 100),
            resets_at=_ms_to_dt(bucket.get("resetAt")),
            detail=detail,
        ))
    return ProviderUsage(PROVIDER_ID, buckets, subtitle=_renews(data.get("period") or {}))


def _describe(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(exc, requests.HTTPError) and response is not None:
        return f"HTTP {response.status_code}"
    return type(exc).__name__


def fetch(api_key: str) -> ProviderUsage:
    """Fetch NanoGPT subscription usage. Never raises."""
    key = (api_key or "").strip()
    if not key:
        return ProviderUsage(PROVIDER_ID, [], error=NO_KEY_MESSAGE)
    try:
        resp = requests.get(USAGE_URL, headers={"x-api-key": key}, timeout=15)
        if resp.status_code in (401, 403):
            log.error("NanoGPT rejected the API key (HTTP %s)", resp.status_code)
            return ProviderUsage(PROVIDER_ID, [], error=KEY_REJECTED_MESSAGE)
        resp.raise_for_status()
        return parse_usage(resp.json())
    except requests.RequestException as e:  # includes JSON decode errors
        log.error("NanoGPT request failed: %s", _describe(e))
        return ProviderUsage(PROVIDER_ID, [], error=f"NanoGPT API error: {_describe(e)}")
    except Exception as e:
        log.error("Unexpected NanoGPT error: %s", type(e).__name__)
        return ProviderUsage(PROVIDER_ID, [], error=f"NanoGPT API error: {type(e).__name__}")
