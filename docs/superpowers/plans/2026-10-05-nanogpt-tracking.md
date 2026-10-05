# NanoGPT Subscription Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track a NanoGPT subscription's limits next to Claude Code in Claude Tracker: a second tray icon, a NanoGPT section in the popup, and NanoGPT settings.

**Architecture:** Replace the Claude-only `api.py` with a `providers/` package where every provider returns the same `ProviderUsage` (a list of `UsageBucket`s). The tray (one `TrayManager` per provider) and the popup render that generic shape. Pure logic (parsing, formatting, layout maths, tooltip text) lives in small, unit-tested functions; Tk/pystray code stays thin.

**Tech Stack:** Python 3.12, customtkinter, pystray (win32 backend), Pillow, requests, pytest (new, dev only), uv.

**Spec:** `docs/superpowers/specs/2026-10-05-nanogpt-tracking-design.md`

## Global Constraints

- Windows only; Python `>=3.12`; run everything with `uv run …` from the repo root `C:\Projects\saas\claude_tracker`.
- No new runtime dependencies. `pytest` is added to the `dev` dependency group only.
- The NanoGPT API key is stored in plain text in `~/.claude/tracker-settings.json` (field `nanogpt_api_key`). Never log it, never put it in tests or commits.
- NanoGPT endpoint: `GET https://nano-gpt.com/api/subscription/v1/usage`, header `x-api-key: <key>`, timeout 15 s.
- `percentUsed` is a fraction 0–1 (×100 for %). `resetAt` is epoch milliseconds. A `null` bucket means "no such limit" → hidden.
- Accent colors: Claude `#D85A30`, NanoGPT `#378ADD`.
- Defaults: `claude_enabled=True`, `nanogpt_enabled=False`, `nanogpt_api_key=""`, `nanogpt_tray_icon=True`. With defaults the app must look and behave as today (one Claude icon).
- Exact user-facing copy:
  - `NanoGPT key rejected. Update it in Settings.`
  - `No active NanoGPT subscription`
  - `NanoGPT API error: <short reason>`
  - `No providers enabled. Turn one on in Settings.`
  - `Enter an API key`
  - `Connected · active plan`
  - `Waiting for data…`
- Tooltips ≤127 chars (Windows limit): `Claude: 5H 60%  |  7D 42%`, `NanoGPT: Wk 1%  |  Img 0%`, on error `<Short>: <error>`.
- One provider's failure must never blank out the other provider.
- Commit style: imperative, capitalized, no prefix (e.g. `Add NanoGPT provider`), ending with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. NanoGPT reports `percentUsed` > 1 (overage) or a non-number → % text shows the real value, the bar clamps to full, nothing crashes. *(Task 3 test `test_overage_and_garbage_percent`)*
2. A bucket with `resetAt: null` → row shows no reset timer instead of crashing. *(Task 3 test `test_missing_reset_at`)*
3. A pasted key with surrounding spaces/newline → it's stripped before use and before saving. *(Task 3 test `test_fetch_strips_key`; Task 7 saves `strip()`ed key)*
4. NanoGPT answers 502 with an HTML body → section error `NanoGPT API error: HTTP 502`, Claude unaffected. *(Task 3 test `test_fetch_http_error_html_body`)*
5. A hand-edited settings file with `"nanogpt_api_key": null` → loads as `""` instead of crashing on `.strip()`. *(Task 4 test `test_null_api_key_coerced`)*

---

## File structure

| File | Responsibility |
| --- | --- |
| `src/claude_tracker/providers/__init__.py` | Provider registry: `enabled_provider_ids`, `tray_provider_ids`, `fetch_provider` |
| `src/claude_tracker/providers/base.py` | `UsageBucket`, `ProviderUsage`, `ProviderMeta`, `PROVIDERS`, `format_amount` |
| `src/claude_tracker/providers/claude.py` | Claude OAuth + usage API (moved from `api.py`), `parse_usage`, `fetch` |
| `src/claude_tracker/providers/nanogpt.py` | NanoGPT usage API: `parse_usage`, `fetch` |
| `src/claude_tracker/layout.py` | `popup_height` (pure layout maths) |
| `src/claude_tracker/config.py` | New settings fields + null-key coercion |
| `src/claude_tracker/tray.py` | Per-provider `TrayManager`, accent stripe, `icon_values`, `tooltip_for` |
| `src/claude_tracker/widget.py` | Multi-provider refresh, popup sections, tray sync, settings dialog |
| `src/claude_tracker/main.py` | Startup wiring |
| `src/claude_tracker/api.py` | **Deleted** |
| `tests/…` | New pytest suite |

---

### Task 1: Test setup and shared provider models

**Files:**
- Modify: `pyproject.toml`
- Create: `src/claude_tracker/providers/__init__.py` (empty for now)
- Create: `src/claude_tracker/providers/base.py`
- Test: `tests/test_base.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `UsageBucket(label: str, short: str, utilization: float, resets_at: datetime | None, detail: str = "")` with property `time_until_reset -> str`
  - `ProviderUsage(provider_id: str, buckets: list[UsageBucket], subtitle: str = "", error: str | None = None)`
  - `ProviderMeta(title: str, short: str, accent: str)`; `PROVIDERS: dict[str, ProviderMeta]` with keys `"claude"`, `"nanogpt"`; `PROVIDER_ORDER = ("claude", "nanogpt")`
  - `format_amount(used: float, limit: float) -> str`

- [ ] **Step 1: Add pytest**

Run: `uv add --dev pytest`

Then append to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the failing tests**

`tests/test_base.py`:

```python
from datetime import datetime, timedelta, timezone

from claude_tracker.providers.base import PROVIDERS, UsageBucket, format_amount


def test_format_amount_millions():
    assert format_amount(631288, 60_000_000) == "0.63M / 60M"


def test_format_amount_thousands():
    assert format_amount(1500, 10_000) == "1.5K / 10K"


def test_format_amount_small():
    assert format_amount(0, 100) == "0 / 100"


def test_time_until_reset_hours():
    bucket = UsageBucket("5-hour window", "5H", 10.0,
                         datetime.now(timezone.utc) + timedelta(hours=2, minutes=5))
    assert bucket.time_until_reset.startswith("~2h")


def test_time_until_reset_none():
    assert UsageBucket("x", "X", 0.0, None).time_until_reset == ""


def test_provider_meta():
    assert PROVIDERS["claude"].accent == "#D85A30"
    assert PROVIDERS["nanogpt"].accent == "#378ADD"
    assert PROVIDERS["nanogpt"].title == "NanoGPT"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'claude_tracker.providers'`

- [ ] **Step 4: Implement**

Create empty `src/claude_tracker/providers/__init__.py`.

`src/claude_tracker/providers/base.py`:

```python
"""Provider-neutral usage models shared by the tray and popup."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class UsageBucket:
    label: str  # "5-hour window", "Weekly tokens"
    short: str  # tooltip label: "5H", "Wk"
    utilization: float  # percentage, may exceed 100 on overage
    resets_at: datetime | None
    detail: str = ""  # "0.63M / 60M"; empty when not meaningful

    @property
    def time_until_reset(self) -> str:
        if not self.resets_at:
            return ""
        now = datetime.now(timezone.utc)
        delta = self.resets_at - now
        total_seconds = max(0, int(delta.total_seconds()))
        if total_seconds == 0:
            return "now"
        hours, remainder = divmod(total_seconds, 3600)
        minutes = remainder // 60
        if hours >= 24:
            days = hours // 24
            remaining_hours = hours % 24
            return f"~{days}d {remaining_hours}h"
        if hours > 0:
            return f"~{hours}h {minutes}m"
        return f"~{minutes}m"


@dataclass
class ProviderUsage:
    provider_id: str
    buckets: list[UsageBucket] = field(default_factory=list)
    subtitle: str = ""  # "renews Oct 11"
    error: str | None = None


@dataclass(frozen=True)
class ProviderMeta:
    title: str  # popup section header
    short: str  # tooltip prefix
    accent: str  # stripe / dot color


PROVIDERS: dict[str, ProviderMeta] = {
    "claude": ProviderMeta(title="Claude Code", short="Claude", accent="#D85A30"),
    "nanogpt": ProviderMeta(title="NanoGPT", short="NanoGPT", accent="#378ADD"),
}
PROVIDER_ORDER = ("claude", "nanogpt")


def _scaled(value: float, divisor: float, suffix: str) -> str:
    text = f"{value / divisor:.2f}".rstrip("0").rstrip(".")
    return f"{text}{suffix}"


def format_amount(used: float, limit: float) -> str:
    """Format "used / limit" in the limit's unit, e.g. "0.63M / 60M"."""
    if limit >= 1_000_000:
        divisor, suffix = 1_000_000, "M"
    elif limit >= 1_000:
        divisor, suffix = 1_000, "K"
    else:
        divisor, suffix = 1, ""
    return f"{_scaled(used, divisor, suffix)} / {_scaled(limit, divisor, suffix)}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_base.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/claude_tracker/providers tests/test_base.py
git commit -m "Add provider usage models and pytest

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Move Claude to a provider module

**Files:**
- Create: `src/claude_tracker/providers/claude.py`
- Delete: `src/claude_tracker/api.py`
- Modify: `src/claude_tracker/widget.py` (imports + `refresh`/`_apply_usage`/`_update_popup` only — kept minimal so the app still runs; Task 6 rewrites these)
- Test: `tests/test_claude.py`

**Interfaces:**
- Consumes: `UsageBucket`, `ProviderUsage` from Task 1.
- Produces: `claude.parse_usage(data: dict) -> ProviderUsage`, `claude.fetch() -> ProviderUsage` (never raises; on error `buckets == []` and `error` set). `LOGIN_EXPIRED_MESSAGE` kept.

- [ ] **Step 1: Write the failing tests**

`tests/test_claude.py`:

```python
from claude_tracker.providers import claude


def test_parse_usage_two_buckets():
    usage = claude.parse_usage({
        "five_hour": {"utilization": 60.0, "resets_at": "2026-10-05T09:00:00+00:00"},
        "seven_day": {"utilization": 42.5, "resets_at": None},
    })
    assert usage.provider_id == "claude"
    assert usage.error is None
    assert [b.short for b in usage.buckets] == ["5H", "7D"]
    assert [b.label for b in usage.buckets] == ["5-hour window", "7-day window"]
    assert usage.buckets[0].utilization == 60.0
    assert usage.buckets[0].resets_at.hour == 9
    assert usage.buckets[1].resets_at is None


def test_parse_usage_missing_buckets_are_zero():
    usage = claude.parse_usage({})
    assert [b.utilization for b in usage.buckets] == [0.0, 0.0]


def test_fetch_without_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(claude, "CREDENTIALS_PATH", tmp_path / "missing.json")
    usage = claude.fetch()
    assert usage.buckets == []
    assert usage.error == "No credentials found. Log in to Claude Code first."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_claude.py -v`
Expected: FAIL with `ImportError: cannot import name 'claude'`

- [ ] **Step 3: Create `providers/claude.py`**

Copy `src/claude_tracker/api.py` to `src/claude_tracker/providers/claude.py`, then in the new file:

1. Change the module docstring to `"""Claude Code usage provider (OAuth usage API)."""`.
2. Delete the `UsageBucket` and `UsageData` dataclasses and `_parse_bucket`, and remove the now-unused `from dataclasses import dataclass` import. Add:

```python
from claude_tracker.providers.base import ProviderUsage, UsageBucket

PROVIDER_ID = "claude"


def _parse_bucket(label: str, short: str, data: dict | None) -> UsageBucket:
    if not data:
        return UsageBucket(label, short, 0.0, None)
    resets_at = None
    if data.get("resets_at"):
        try:
            resets_at = datetime.fromisoformat(data["resets_at"])
        except ValueError:
            pass
    return UsageBucket(label, short, float(data.get("utilization", 0.0)), resets_at)


def parse_usage(data: dict) -> ProviderUsage:
    return ProviderUsage(PROVIDER_ID, [
        _parse_bucket("5-hour window", "5H", data.get("five_hour")),
        _parse_bucket("7-day window", "7D", data.get("seven_day")),
    ])


def _error(message: str) -> ProviderUsage:
    return ProviderUsage(PROVIDER_ID, [], error=message)
```

3. Rename `fetch_usage` to `fetch`, set its return annotation to `-> ProviderUsage`, docstring `"""Fetch current Claude usage. Never raises."""`. Replace its success return with `return parse_usage(resp.json())` and every `return UsageData(...)` in the `except` blocks with `return _error(<same message as before>)`:

```python
    except FileNotFoundError as e:
        log.error("Credentials file not found: %s", e)
        return _error("No credentials found. Log in to Claude Code first.")
    except LoginExpiredError as e:
        log.error("Login expired: %s", e)
        return _error(LOGIN_EXPIRED_MESSAGE)
    except requests.RequestException as e:
        log.error("API request failed: %s", e)
        return _error(f"API error: {e}")
    except Exception as e:
        log.error("Unexpected error: %s", e)
        return _error(str(e))
```

Leave `_read_credentials`, `_save_credentials`, `_refresh_token`, `LoginExpiredError`, constants unchanged.

Delete `src/claude_tracker/api.py`.

- [ ] **Step 4: Keep the widget running on the new shape**

In `src/claude_tracker/widget.py`:

Replace `from claude_tracker.api import UsageData, fetch_usage` with:

```python
from claude_tracker.providers import claude
from claude_tracker.providers.base import ProviderUsage
```

Change `self._last_usage: UsageData | None = None` to `self._last_usage: ProviderUsage | None = None`.

Replace `_update_popup`, `refresh`, `_apply_usage` with:

```python
    def _update_popup(self, usage: ProviderUsage) -> None:
        if not self._popup_win or not self._popup_win.winfo_exists():
            return
        for bucket, row in zip(usage.buckets, [self._popup_5h, self._popup_7d]):
            if row is None:
                continue
            color = _color_for(bucket.utilization)
            row["bar"].configure(progress_color=color)
            row["bar"].set(bucket.utilization / 100.0)
            row["pct"].configure(text=f"{bucket.utilization:.0f}%")
            row["timer"].configure(text=f"resets {bucket.time_until_reset}" if bucket.time_until_reset else "")
```

```python
    def refresh(self) -> None:
        log.info("Refreshing usage data...")
        self._apply_usage(claude.fetch())

    def _apply_usage(self, usage: ProviderUsage) -> None:
        self._last_usage = usage
        self._update_popup(usage)

        if self.tray:
            utils = [b.utilization for b in usage.buckets] + [0.0, 0.0]
            self.tray.update_icon(utils[0], utils[1])
            if usage.error:
                # Windows caps tray tooltips at 127 chars
                self.tray.update_tooltip(f"Claude Tracker: {usage.error}"[:127])
            else:
                self.tray.update_tooltip(
                    f"Claude: 5H {utils[0]:.0f}%  |  7D {utils[1]:.0f}%"
                )
```

- [ ] **Step 5: Run tests and an import smoke check**

Run: `uv run pytest -v`
Expected: all pass (9 tests).

Run: `uv run python -c "import claude_tracker.widget, claude_tracker.tray, claude_tracker.main"`
Expected: no output, exit 0.

Run: `git grep -n "claude_tracker.api\|fetch_usage\|UsageData" -- src`
Expected: no matches.

- [ ] **Step 6: Commit**

```bash
git add -A src/claude_tracker tests/test_claude.py
git commit -m "Move Claude usage client into providers package

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: NanoGPT provider

**Files:**
- Create: `src/claude_tracker/providers/nanogpt.py`
- Test: `tests/test_nanogpt.py`

**Interfaces:**
- Consumes: `UsageBucket`, `ProviderUsage`, `format_amount` from Task 1.
- Produces: `nanogpt.parse_usage(data: dict) -> ProviderUsage`, `nanogpt.fetch(api_key: str) -> ProviderUsage` (never raises), constants `KEY_REJECTED_MESSAGE`, `INACTIVE_MESSAGE`, `NO_KEY_MESSAGE`.

- [ ] **Step 1: Write the failing tests**

`tests/test_nanogpt.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_nanogpt.py -v`
Expected: FAIL with `ImportError: cannot import name 'nanogpt'`

- [ ] **Step 3: Implement**

`src/claude_tracker/providers/nanogpt.py`:

```python
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
```

Note: log lines only include status codes / exception class names, never headers or the key.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_nanogpt.py -v`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add src/claude_tracker/providers/nanogpt.py tests/test_nanogpt.py
git commit -m "Add NanoGPT subscription usage provider

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Settings fields and provider registry

**Files:**
- Modify: `src/claude_tracker/config.py`
- Modify: `src/claude_tracker/providers/__init__.py`
- Test: `tests/test_config.py`, `tests/test_registry.py`

**Interfaces:**
- Consumes: `claude.fetch`, `nanogpt.fetch`, `PROVIDER_ORDER`.
- Produces:
  - `Settings` fields `claude_enabled: bool = True`, `nanogpt_enabled: bool = False`, `nanogpt_api_key: str = ""`, `nanogpt_tray_icon: bool = True`
  - `enabled_provider_ids(settings) -> list[str]` (order = `PROVIDER_ORDER`; NanoGPT only if enabled **and** key non-blank)
  - `tray_provider_ids(settings) -> list[str]` (enabled minus NanoGPT when `nanogpt_tray_icon` is off; `["claude"]` if that's empty, so the app stays reachable)
  - `fetch_provider(provider_id: str, settings) -> ProviderUsage`

- [ ] **Step 1: Write the failing tests**

`tests/test_config.py`:

```python
import json

from claude_tracker import config


def test_old_settings_file_gets_defaults(monkeypatch, tmp_path):
    path = tmp_path / "tracker-settings.json"
    path.write_text(json.dumps({"refresh_interval": 90, "start_on_boot": True, "theme": "dark"}))
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    s = config.Settings.load()
    assert s.refresh_interval == 90
    assert s.claude_enabled is True
    assert s.nanogpt_enabled is False
    assert s.nanogpt_api_key == ""
    assert s.nanogpt_tray_icon is True


def test_null_api_key_coerced(monkeypatch, tmp_path):
    path = tmp_path / "tracker-settings.json"
    path.write_text(json.dumps({"nanogpt_enabled": True, "nanogpt_api_key": None}))
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    assert config.Settings.load().nanogpt_api_key == ""


def test_round_trip(monkeypatch, tmp_path):
    path = tmp_path / "tracker-settings.json"
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    s = config.Settings(nanogpt_enabled=True, nanogpt_api_key="sk-nano-test")
    s.save()
    loaded = config.Settings.load()
    assert loaded.nanogpt_enabled is True
    assert loaded.nanogpt_api_key == "sk-nano-test"
```

`tests/test_registry.py`:

```python
from claude_tracker.config import Settings
from claude_tracker.providers import enabled_provider_ids, fetch_provider, tray_provider_ids
from claude_tracker.providers import claude, nanogpt
from claude_tracker.providers.base import ProviderUsage


def test_defaults_claude_only():
    s = Settings()
    assert enabled_provider_ids(s) == ["claude"]
    assert tray_provider_ids(s) == ["claude"]


def test_nanogpt_needs_key():
    s = Settings(nanogpt_enabled=True, nanogpt_api_key="  ")
    assert enabled_provider_ids(s) == ["claude"]


def test_both_enabled():
    s = Settings(nanogpt_enabled=True, nanogpt_api_key="k")
    assert enabled_provider_ids(s) == ["claude", "nanogpt"]
    assert tray_provider_ids(s) == ["claude", "nanogpt"]


def test_nanogpt_tray_icon_off():
    s = Settings(nanogpt_enabled=True, nanogpt_api_key="k", nanogpt_tray_icon=False)
    assert tray_provider_ids(s) == ["claude"]


def test_only_nanogpt():
    s = Settings(claude_enabled=False, nanogpt_enabled=True, nanogpt_api_key="k")
    assert enabled_provider_ids(s) == ["nanogpt"]
    assert tray_provider_ids(s) == ["nanogpt"]


def test_nothing_enabled_keeps_claude_icon():
    s = Settings(claude_enabled=False)
    assert enabled_provider_ids(s) == []
    assert tray_provider_ids(s) == ["claude"]


def test_fetch_provider_dispatch(monkeypatch):
    monkeypatch.setattr(claude, "fetch", lambda: ProviderUsage("claude"))
    monkeypatch.setattr(nanogpt, "fetch", lambda key: ProviderUsage("nanogpt", subtitle=key))
    s = Settings(nanogpt_api_key="k")
    assert fetch_provider("claude", s).provider_id == "claude"
    assert fetch_provider("nanogpt", s).subtitle == "k"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py tests/test_registry.py -v`
Expected: FAIL (`TypeError: ... unexpected keyword argument 'nanogpt_enabled'` / `ImportError: cannot import name 'enabled_provider_ids'`)

- [ ] **Step 3: Implement settings**

In `src/claude_tracker/config.py`, add fields to `Settings` after `theme`:

```python
    claude_enabled: bool = True
    nanogpt_enabled: bool = False
    nanogpt_api_key: str = ""  # stored in plain text by design
    nanogpt_tray_icon: bool = True
```

In `Settings.load`, after the `filtered = …` line add:

```python
            if not isinstance(filtered.get("nanogpt_api_key", ""), str):
                filtered["nanogpt_api_key"] = ""
```

- [ ] **Step 4: Implement registry**

`src/claude_tracker/providers/__init__.py`:

```python
"""Provider registry: which providers are on, and how to fetch each."""

from typing import TYPE_CHECKING

from claude_tracker.providers import claude, nanogpt
from claude_tracker.providers.base import PROVIDER_ORDER, ProviderUsage

if TYPE_CHECKING:
    from claude_tracker.config import Settings


def enabled_provider_ids(settings: "Settings") -> list[str]:
    enabled = {
        "claude": settings.claude_enabled,
        "nanogpt": settings.nanogpt_enabled and bool(settings.nanogpt_api_key.strip()),
    }
    return [pid for pid in PROVIDER_ORDER if enabled[pid]]


def tray_provider_ids(settings: "Settings") -> list[str]:
    ids = [pid for pid in enabled_provider_ids(settings)
           if pid != "nanogpt" or settings.nanogpt_tray_icon]
    # Always keep one icon so the app stays reachable.
    return ids or ["claude"]


def fetch_provider(provider_id: str, settings: "Settings") -> ProviderUsage:
    if provider_id == "claude":
        return claude.fetch()
    if provider_id == "nanogpt":
        return nanogpt.fetch(settings.nanogpt_api_key)
    raise ValueError(f"Unknown provider: {provider_id}")
```

Note: `nanogpt.fetch` must be looked up at call time (`nanogpt.fetch(...)`, as above), not imported by name, so tests can monkeypatch it.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/claude_tracker/config.py src/claude_tracker/providers/__init__.py tests/test_config.py tests/test_registry.py
git commit -m "Add NanoGPT settings and provider registry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Per-provider tray icons

**Files:**
- Modify: `src/claude_tracker/tray.py`
- Test: `tests/test_tray.py`

**Interfaces:**
- Consumes: `ProviderUsage`, `PROVIDERS` (Task 1).
- Produces:
  - `_create_split_icon(util_top: float | None = None, util_bot: float | None = None, accent: str | None = None, size: int = 128) -> Image.Image` (`None` half = grey with "-")
  - `icon_values(usage: ProviderUsage | None) -> tuple[float | None, float | None]`
  - `tooltip_for(provider_id: str, usage: ProviderUsage | None) -> str` (≤127 chars)
  - `TrayManager(widget, provider_id: str)` with `start()`, `stop()`, `show_usage(usage: ProviderUsage | None)`. `update_icon`/`update_tooltip` are removed.
  - Initial tooltip `"Claude Tracker"` for claude, `"Claude Tracker NanoGPT"` for nanogpt; auto-pin matches the `"Claude Tracker"` prefix.

- [ ] **Step 1: Write the failing tests**

`tests/test_tray.py`:

```python
from claude_tracker.providers.base import ProviderUsage, UsageBucket
from claude_tracker.tray import _create_split_icon, icon_values, tooltip_for


def _usage(pid, *utils, error=None):
    buckets = [UsageBucket(f"b{i}", s, u, None) for i, (s, u) in enumerate(utils)]
    return ProviderUsage(pid, buckets, error=error)


def test_icon_values_two_buckets():
    assert icon_values(_usage("nanogpt", ("Wk", 1.0), ("Img", 0.0))) == (1.0, 0.0)


def test_icon_values_one_bucket_fills_both():
    assert icon_values(_usage("nanogpt", ("Wk", 30.0))) == (30.0, 30.0)


def test_icon_values_error_or_missing_is_grey():
    assert icon_values(None) == (None, None)
    assert icon_values(_usage("claude", error="boom")) == (None, None)


def test_tooltip_claude():
    assert tooltip_for("claude", _usage("claude", ("5H", 60.4), ("7D", 42.0))) == "Claude: 5H 60%  |  7D 42%"


def test_tooltip_nanogpt():
    assert tooltip_for("nanogpt", _usage("nanogpt", ("Wk", 1.05), ("Img", 0.0))) == "NanoGPT: Wk 1%  |  Img 0%"


def test_tooltip_error_truncated():
    text = tooltip_for("nanogpt", _usage("nanogpt", error="x" * 300))
    assert text.startswith("NanoGPT: xxx")
    assert len(text) <= 127


def test_tooltip_no_data():
    # Fallback icon (no data for this provider): neutral, since other providers may be on.
    assert tooltip_for("claude", None) == "Claude Tracker"


def test_icon_has_accent_stripe():
    img = _create_split_icon(50.0, None, accent="#378ADD")
    assert img.size == (128, 128)
    assert img.getpixel((2, 64))[:3] == (0x37, 0x8A, 0xDD)


def test_icon_without_accent_has_no_stripe():
    img = _create_split_icon(10.0, 10.0)
    assert img.getpixel((2, 100))[:3] == (0x86, 0xEF, 0xAC)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_tray.py -v`
Expected: FAIL with `ImportError: cannot import name 'icon_values'`

- [ ] **Step 3: Implement the icon and helper functions**

In `src/claude_tracker/tray.py`:

Add import: `from claude_tracker.providers.base import PROVIDERS, ProviderUsage`

Add constants near `_color_for`:

```python
COLOR_NO_DATA = "#d4d4d8"  # light grey when a provider has no data / errored
```

Replace `_create_split_icon` with:

```python
def _create_split_icon(
    util_top: float | None = None,
    util_bot: float | None = None,
    accent: str | None = None,
    size: int = 128,
) -> Image.Image:
    """Generate a square tray icon split into top and bottom halves.

    Each half is colored by utilization and shows the percentage; ``None`` draws a
    grey half with "-". ``accent`` draws a provider stripe on the left edge.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = 6  # corner radius
    half = size // 2

    color_top = _color_for(util_top) if util_top is not None else COLOR_NO_DATA
    color_bot = _color_for(util_bot) if util_bot is not None else COLOR_NO_DATA

    # Top half with rounded top corners
    draw.rounded_rectangle([0, 0, size - 1, half], radius=r, fill=color_top)
    # Fill bottom of top half to make it flat at the seam
    draw.rectangle([0, half - r, size - 1, half], fill=color_top)

    # Bottom half with rounded bottom corners
    draw.rounded_rectangle([0, half, size - 1, size - 1], radius=r, fill=color_bot)
    # Fill top of bottom half to make it flat at the seam
    draw.rectangle([0, half, size - 1, half + r], fill=color_bot)

    # Thin separator line
    draw.line([(2, half), (size - 3, half)], fill="#00000066", width=1)

    stripe = size // 10 if accent else 0
    if accent:
        draw.rectangle([0, 0, stripe - 1, size - 1], fill=accent)

    # Fit percentage text in each half — big and bold, black text
    try:
        font = ImageFont.truetype("arialbd.ttf", size * 2 // 3)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", size * 3 // 8)
        except OSError:
            font = ImageFont.load_default()

    text_color = "#000000"
    for util, y_center in [(util_top, half // 2), (util_bot, half + half // 2)]:
        text = f"{util:.0f}" if util is not None else "-"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = stripe + (size - stripe - tw) // 2 - bbox[0]
        ty = y_center - th // 2 - bbox[1]
        draw.text((tx, ty), text, fill=text_color, font=font)

    return img


def icon_values(usage: ProviderUsage | None) -> tuple[float | None, float | None]:
    """Top/bottom utilization for a provider's icon; (None, None) means grey."""
    if usage is None or usage.error or not usage.buckets:
        return None, None
    top = usage.buckets[0].utilization
    bot = usage.buckets[1].utilization if len(usage.buckets) > 1 else top
    return top, bot


def tooltip_for(provider_id: str, usage: ProviderUsage | None) -> str:
    # Windows caps tray tooltips at 127 chars
    if usage is None:
        return "Claude Tracker"
    short = PROVIDERS[provider_id].short
    if usage.error:
        return f"{short}: {usage.error}"[:127]
    parts = [f"{b.short} {b.utilization:.0f}%" for b in usage.buckets[:2]]
    return f"{short}: {'  |  '.join(parts)}"[:127]
```

In `_promote_tray_icon`, change the match line to:

```python
                    is_ours = (tooltip.startswith("Claude Tracker") or
                               (path_val and exe_path in path_val.lower()))
```

- [ ] **Step 4: Make `TrayManager` per-provider**

Replace the `TrayManager` class's `__init__`, `_run`, `update_icon`, `update_tooltip` with (keep `start`, `stop`, `_on_*` handlers as they are):

```python
class TrayManager:
    def __init__(self, widget: "TrackerWidget", provider_id: str) -> None:
        self._widget = widget
        self.provider_id = provider_id
        self._accent = PROVIDERS[provider_id].accent
        self._usage: ProviderUsage | None = None
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def _run(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide", self._on_toggle, default=True),
            pystray.MenuItem("Refresh", self._on_refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", self._on_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        )
        suffix = "" if self.provider_id == "claude" else f"_{self.provider_id}"
        # The initial tooltip is what Windows stores as InitialTooltip; auto-pin
        # matches on its "Claude Tracker" prefix.
        title = "Claude Tracker" if self.provider_id == "claude" else f"Claude Tracker {PROVIDERS[self.provider_id].title}"
        self._icon = pystray.Icon(
            f"claude_tracker{suffix}",
            icon=_create_split_icon(*icon_values(self._usage), accent=self._accent),
            title=title,
            menu=menu,
        )
        threading.Timer(2.0, _promote_tray_icon).start()
        self._icon.run()

    def show_usage(self, usage: ProviderUsage | None) -> None:
        self._usage = usage
        if self._icon:
            self._icon.icon = _create_split_icon(*icon_values(usage), accent=self._accent)
            self._icon.title = tooltip_for(self.provider_id, usage)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_tray.py -v`
Expected: 9 passed

(`widget.py` still calls `update_icon`/`update_tooltip` and `TrayManager(widget)`; Task 6 fixes that. Don't run the app between Task 5 and Task 6.)

- [ ] **Step 6: Commit**

```bash
git add src/claude_tracker/tray.py tests/test_tray.py
git commit -m "Make tray icons per-provider with accent stripe

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Multi-provider popup, refresh, and tray sync

**Files:**
- Create: `src/claude_tracker/layout.py`
- Modify: `src/claude_tracker/widget.py`
- Modify: `src/claude_tracker/main.py`
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `enabled_provider_ids`, `tray_provider_ids`, `fetch_provider` (Task 4); `TrayManager(widget, provider_id)`, `.show_usage()`, `.stop()` (Task 5); `ProviderUsage`, `PROVIDERS` (Task 1).
- Produces:
  - `layout.popup_height(sections: list[tuple[int, bool]]) -> int` — each tuple is `(bucket_count, shows_message)`; logical px.
  - `TrackerWidget.trays: dict[str, TrayManager]`, `TrackerWidget.sync_tray_icons() -> None`, `TrackerWidget.apply_settings() -> None` (used by Task 7), `TrackerWidget._last_usage: dict[str, ProviderUsage]`.

- [ ] **Step 1: Write the failing layout tests**

`tests/test_layout.py`:

```python
from claude_tracker.layout import popup_height


def test_two_providers_taller_than_one():
    assert popup_height([(2, False), (2, False)]) > popup_height([(2, False)])


def test_error_section_shorter_than_two_rows():
    assert popup_height([(0, True)]) < popup_height([(2, False)])


def test_empty_state_has_room_for_message_and_buttons():
    assert popup_height([]) >= 100


def test_claude_only_roughly_matches_old_popup():
    assert 150 <= popup_height([(2, False)]) <= 230
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'claude_tracker.layout'`

- [ ] **Step 3: Implement `layout.py`**

```python
"""Popup layout maths (logical pixels), kept free of Tk for testing."""

TOP_PAD = 12
SECTION_HEADER = 28
BUCKET_ROW = 42
MESSAGE = 40  # error / waiting / empty-state line (allows 2 wrapped lines)
SEPARATOR = 13
BUTTONS = 52


def popup_height(sections: list[tuple[int, bool]]) -> int:
    """Height for sections given as (bucket_count, shows_message)."""
    if not sections:
        return TOP_PAD + MESSAGE + BUTTONS
    height = TOP_PAD + BUTTONS + SEPARATOR * (len(sections) - 1)
    for bucket_count, shows_message in sections:
        body = MESSAGE if shows_message or bucket_count == 0 else BUCKET_ROW * bucket_count
        height += SECTION_HEADER + body
    return height
```

Run: `uv run pytest tests/test_layout.py -v` → 4 passed.

- [ ] **Step 4: Rewrite the widget's provider-facing parts**

In `src/claude_tracker/widget.py`:

Imports — replace the provider/tray imports with:

```python
from claude_tracker.config import Settings
from claude_tracker.layout import popup_height
from claude_tracker.providers import enabled_provider_ids, fetch_provider, tray_provider_ids
from claude_tracker.providers.base import PROVIDERS, ProviderUsage, UsageBucket
from claude_tracker.startup import is_startup_enabled, set_startup
from claude_tracker.tray import TrayManager
```

Remove the `TYPE_CHECKING` block and the `from typing import TYPE_CHECKING` import (tray is now imported directly; `tray.py` only imports `widget` under `TYPE_CHECKING`, so there's no cycle).

Add constants after `COLOR_BAR_BG`:

```python
COLOR_WARN = "#fbbf24"
POPUP_W = 300
NO_PROVIDERS_MESSAGE = "No providers enabled. Turn one on in Settings."
WAITING_MESSAGE = "Waiting for data…"
```

Replace `TrackerWidget.__init__` state lines with:

```python
        self.settings = settings
        self.trays: dict[str, TrayManager] = {}
        self._refresh_job: str | None = None
        self._popup_win: ctk.CTkToplevel | None = None
        self._popup_content: ctk.CTkFrame | None = None
        self._last_usage: dict[str, ProviderUsage] = {}
```

(keep the `ctk.set_…` and `self.root` lines that follow.)

Replace `_show_popup`, `_build_popup`, `_build_popup_row`, `_update_popup`, `_close_popup` with:

```python
    def _show_popup(self) -> None:
        if self._popup_win and self._popup_win.winfo_exists():
            return

        popup = ctk.CTkToplevel(self.root)
        popup.title("")
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=POPUP_BG)
        self._popup_win = popup

        self._build_popup(popup)
        self._render_popup()

        popup.bind("<FocusOut>", lambda _: self.root.after(200, self._close_popup_if_inactive))
        popup.after(100, lambda: popup.focus_force())

    def _place_popup(self, popup_h: int) -> None:
        """Size the popup and anchor it above the notification area."""
        popup_w = POPUP_W
        scale = self._get_dpi_scale()
        popup_w_phys = int(popup_w * scale)
        popup_h_phys = int(popup_h * scale)

        tray_rect = _get_tray_notify_rect()
        if tray_rect:
            tray_cx = (tray_rect[0] + tray_rect[2]) // 2
            x = tray_cx - popup_w_phys // 2
            y = tray_rect[1] - popup_h_phys - 12
        else:
            sw_phys = int(self.root.winfo_screenwidth() * scale)
            sh_phys = int(self.root.winfo_screenheight() * scale)
            x = sw_phys - popup_w_phys - 20
            y = sh_phys - popup_h_phys - 60

        # Keep on screen
        screen_w_phys = int(self.root.winfo_screenwidth() * scale)
        x = max(8, min(x, screen_w_phys - popup_w_phys - 8))

        self._popup_win.geometry(f"{popup_w}x{popup_h}+{x}+{y}")

    def _build_popup(self, popup: ctk.CTkToplevel) -> None:
        frame = ctk.CTkFrame(popup, fg_color=POPUP_BG, corner_radius=10,
                             border_width=1, border_color=POPUP_BORDER)
        frame.pack(fill="both", expand=True)

        self._popup_content = ctk.CTkFrame(frame, fg_color="transparent")
        self._popup_content.pack(fill="x", pady=(12, 0))

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=14, pady=(10, 12))

        ctk.CTkButton(btn_frame, text="Refresh", width=70, height=28,
                      command=self.refresh, fg_color="#333344",
                      hover_color="#444455", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkButton(btn_frame, text="Settings", width=70, height=28,
                      command=self.open_settings, fg_color="#333344",
                      hover_color="#444455", font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Exit", width=50, height=28,
                      command=self.quit_app, fg_color="#442222",
                      hover_color="#553333", font=ctk.CTkFont(size=11)).pack(side="right")

    def _render_popup(self) -> None:
        """Rebuild the provider sections from the latest data and resize."""
        if not self._popup_win or not self._popup_win.winfo_exists() or not self._popup_content:
            return
        for child in self._popup_content.winfo_children():
            child.destroy()

        ids = enabled_provider_ids(self.settings)
        if not ids:
            self._build_message(self._popup_content, NO_PROVIDERS_MESSAGE, COLOR_LABEL)
        sections = []
        for i, pid in enumerate(ids):
            if i:
                ctk.CTkFrame(self._popup_content, height=1, fg_color=POPUP_BORDER).pack(
                    fill="x", padx=14, pady=6)
            usage = self._last_usage.get(pid)
            self._build_section(self._popup_content, pid, usage)
            shows_message = usage is None or bool(usage.error)
            sections.append((len(usage.buckets) if usage else 0, shows_message))

        self._place_popup(popup_height(sections))

    def _build_section(self, parent: ctk.CTkFrame, pid: str, usage: ProviderUsage | None) -> None:
        meta = PROVIDERS[pid]
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(header, text="■", text_color=meta.accent, width=12,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkLabel(header, text=meta.title, text_color=COLOR_FG,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(4, 0))
        if usage and usage.subtitle:
            ctk.CTkLabel(header, text=usage.subtitle, text_color=COLOR_LABEL,
                         font=ctk.CTkFont(size=10)).pack(side="right")

        if usage is None:
            self._build_message(parent, WAITING_MESSAGE, COLOR_LABEL)
        elif usage.error:
            self._build_message(parent, usage.error, COLOR_WARN)
        else:
            for bucket in usage.buckets:
                self._build_bucket_row(parent, bucket)

    def _build_message(self, parent: ctk.CTkFrame, text: str, color: str) -> None:
        ctk.CTkLabel(parent, text=text, text_color=color, font=ctk.CTkFont(size=11),
                     wraplength=POPUP_W - 30, justify="left").pack(anchor="w", padx=14, pady=(0, 6))

    def _build_bucket_row(self, parent: ctk.CTkFrame, bucket: UsageBucket) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 6))

        header = ctk.CTkFrame(row, fg_color="transparent")
        header.pack(fill="x")
        title = f"{bucket.label} · {bucket.detail}" if bucket.detail else bucket.label
        ctk.CTkLabel(header, text=title, font=ctk.CTkFont(size=11),
                     text_color=COLOR_LABEL).pack(side="left")
        reset = f"resets {bucket.time_until_reset}" if bucket.time_until_reset else ""
        ctk.CTkLabel(header, text=reset, font=ctk.CTkFont(size=10),
                     text_color=COLOR_LABEL).pack(side="right")

        bar_row = ctk.CTkFrame(row, fg_color="transparent")
        bar_row.pack(fill="x", pady=(2, 0))
        bar = ctk.CTkProgressBar(bar_row, height=12, corner_radius=4, fg_color=COLOR_BAR_BG,
                                 progress_color=_color_for(bucket.utilization))
        bar.set(min(1.0, max(0.0, bucket.utilization / 100.0)))
        bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(bar_row, text=f"{bucket.utilization:.0f}%",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLOR_FG, width=40, anchor="e").pack(side="right")

    def _close_popup(self) -> None:
        if self._popup_win and self._popup_win.winfo_exists():
            self._popup_win.destroy()
        self._popup_win = None
        self._popup_content = None
```

Replace `set_tray`, `refresh`, `_apply_usage` with:

```python
    def sync_tray_icons(self) -> None:
        """Start/stop tray icons to match the current settings."""
        wanted = tray_provider_ids(self.settings)
        for pid in list(self.trays):
            if pid not in wanted:
                self.trays.pop(pid).stop()
        for pid in wanted:
            if pid not in self.trays:
                tray = TrayManager(self, pid)
                self.trays[pid] = tray
                tray.show_usage(self._last_usage.get(pid))
                tray.start()

    def refresh(self) -> None:
        log.info("Refreshing usage data...")
        results = {pid: fetch_provider(pid, self.settings)
                   for pid in enabled_provider_ids(self.settings)}
        self._apply_usage(results)

    def _apply_usage(self, results: dict[str, ProviderUsage]) -> None:
        self._last_usage = results
        self._render_popup()
        for pid, tray in self.trays.items():
            tray.show_usage(results.get(pid))

    def apply_settings(self) -> None:
        """Re-sync icons and restart polling after settings change."""
        if self._refresh_job:
            self.root.after_cancel(self._refresh_job)
            self._refresh_job = None
        self._last_usage = {}
        self.sync_tray_icons()
        self.start_polling()
```

In `quit_app`, replace the `if self.tray: self.tray.stop()` lines with:

```python
        for tray in self.trays.values():
            tray.stop()
```

- [ ] **Step 5: Update `main.py`**

Remove `from claude_tracker.tray import TrayManager` and replace:

```python
        widget = TrackerWidget(settings)
        tray = TrayManager(widget)
        widget.set_tray(tray)

        tray.start()
        widget.start_polling()
```

with:

```python
        widget = TrackerWidget(settings)
        widget.sync_tray_icons()
        widget.start_polling()
```

- [ ] **Step 6: Check nothing references removed names**

Run: `git grep -n "set_tray\|self\.tray\b\|update_icon\|update_tooltip\|_popup_5h\|_popup_7d" -- src`
Expected: no matches.

Run: `uv run pytest -v` → all pass.
Run: `uv run python -c "import claude_tracker.main"` → exit 0.

- [ ] **Step 7: Manual check, Claude only (defaults)**

Run: `uv run python -m claude_tracker` (the installed `ClaudeTracker.exe` can stay running; you'll just see its icon too).
Expected: one new icon with a coral left stripe and live 5H/7D numbers. Click it: popup shows a "Claude Code" section with two bars, sized to fit, no clipped buttons. Exit from the popup.

- [ ] **Step 8: Commit**

```bash
git add src/claude_tracker/layout.py src/claude_tracker/widget.py src/claude_tracker/main.py tests/test_layout.py
git commit -m "Render popup and tray icons from all enabled providers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: NanoGPT section in Settings

**Files:**
- Modify: `src/claude_tracker/widget.py` (`SettingsDialog` only)

**Interfaces:**
- Consumes: `nanogpt.fetch(api_key) -> ProviderUsage`, `nanogpt.NO_KEY_MESSAGE` (Task 3); `Settings` fields (Task 4); `TrackerWidget.apply_settings()` (Task 6); `PROVIDERS`.
- Produces: user-facing settings; no new code interfaces.

No unit tests: this is Tk widget wiring over already-tested functions. Verified manually in Step 3.

- [ ] **Step 1: Implement**

Add to the imports at the top of `widget.py`:

```python
import threading

from claude_tracker.providers import nanogpt
```

Replace the whole `SettingsDialog` class with:

```python
class SettingsDialog:
    def __init__(self, widget: TrackerWidget) -> None:
        self._widget = widget
        self._settings = widget.settings

        self._win = ctk.CTkToplevel(widget.root)
        self._win.title("Claude Tracker Settings")
        self._win.geometry("340x420")
        self._win.resizable(False, False)
        self._win.attributes("-topmost", True)
        self._win.configure(fg_color=POPUP_BG)
        self._win.grab_set()

        self._build()

    def _section_header(self, title: str, accent: str, variable: tk.BooleanVar) -> None:
        row = ctk.CTkFrame(self._win, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 0))
        ctk.CTkLabel(row, text="■", text_color=accent, width=12).pack(side="left")
        ctk.CTkLabel(row, text=title, text_color=COLOR_FG,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(4, 0))
        ctk.CTkCheckBox(row, text="Enabled", variable=variable, text_color=COLOR_FG,
                        fg_color=COLOR_GREEN, hover_color="#16a34a").pack(side="right")

    def _build(self) -> None:
        pad = {"padx": 16, "pady": (8, 0)}

        ctk.CTkLabel(self._win, text="Refresh interval (seconds):",
                     text_color=COLOR_FG).pack(anchor="w", **pad)
        self._interval_var = tk.StringVar(value=str(self._settings.refresh_interval))
        ctk.CTkEntry(self._win, textvariable=self._interval_var, width=100,
                     fg_color=COLOR_BAR_BG, text_color=COLOR_FG).pack(anchor="w", padx=16, pady=4)

        self._boot_var = tk.BooleanVar(value=is_startup_enabled())
        ctk.CTkCheckBox(self._win, text="Start on boot", variable=self._boot_var,
                        text_color=COLOR_FG, fg_color=COLOR_GREEN,
                        hover_color="#16a34a").pack(anchor="w", **pad)

        ctk.CTkFrame(self._win, height=1, fg_color=POPUP_BORDER).pack(fill="x", padx=16, pady=(12, 0))

        self._claude_var = tk.BooleanVar(value=self._settings.claude_enabled)
        self._section_header(PROVIDERS["claude"].title, PROVIDERS["claude"].accent, self._claude_var)

        self._nano_var = tk.BooleanVar(value=self._settings.nanogpt_enabled)
        self._section_header(PROVIDERS["nanogpt"].title, PROVIDERS["nanogpt"].accent, self._nano_var)

        ctk.CTkLabel(self._win, text="API key", text_color=COLOR_LABEL,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        key_row = ctk.CTkFrame(self._win, fg_color="transparent")
        key_row.pack(fill="x", padx=16, pady=(2, 0))
        self._key_var = tk.StringVar(value=self._settings.nanogpt_api_key)
        ctk.CTkEntry(key_row, textvariable=self._key_var, show="•", width=230,
                     fg_color=COLOR_BAR_BG, text_color=COLOR_FG).pack(side="left")
        ctk.CTkButton(key_row, text="Test", width=60, command=self._test_key,
                      fg_color="#333344", hover_color="#444455").pack(side="right")

        self._status = ctk.CTkLabel(self._win, text="", font=ctk.CTkFont(size=11),
                                    text_color=COLOR_LABEL, wraplength=300, justify="left")
        self._status.pack(anchor="w", padx=16, pady=(4, 0))

        self._nano_tray_var = tk.BooleanVar(value=self._settings.nanogpt_tray_icon)
        ctk.CTkCheckBox(self._win, text="Show NanoGPT tray icon", variable=self._nano_tray_var,
                        text_color=COLOR_FG, fg_color=COLOR_GREEN,
                        hover_color="#16a34a").pack(anchor="w", **pad)

        btn_frame = ctk.CTkFrame(self._win, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=16, pady=16)
        ctk.CTkButton(btn_frame, text="Save", width=80, command=self._save,
                      fg_color=COLOR_GREEN, hover_color="#16a34a",
                      text_color="#000000").pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text="Cancel", width=80, command=self._win.destroy,
                      fg_color=COLOR_BAR_BG, hover_color="#45475a").pack(side="right")

    def _set_status(self, text: str, color: str) -> None:
        try:
            if self._win.winfo_exists():
                self._status.configure(text=text, text_color=color)
        except tk.TclError:
            pass  # dialog closed while a test was running

    def _test_key(self) -> None:
        key = self._key_var.get().strip()
        if not key:
            self._set_status(nanogpt.NO_KEY_MESSAGE, COLOR_RED)
            return
        self._set_status("Testing…", COLOR_LABEL)

        def work() -> None:
            result = nanogpt.fetch(key)
            self._widget.root.after(0, lambda: self._show_test_result(result))

        threading.Thread(target=work, daemon=True).start()

    def _show_test_result(self, result: ProviderUsage) -> None:
        if result.error:
            self._set_status(result.error, COLOR_RED)
        else:
            self._set_status("Connected · active plan", COLOR_GREEN)

    def _save(self) -> None:
        key = self._key_var.get().strip()
        if self._nano_var.get() and not key:
            self._set_status(nanogpt.NO_KEY_MESSAGE, COLOR_RED)
            return

        try:
            interval = max(30, int(self._interval_var.get()))
            self._settings.refresh_interval = interval
        except ValueError:
            pass

        set_startup(self._boot_var.get())
        self._settings.start_on_boot = self._boot_var.get()
        self._settings.claude_enabled = self._claude_var.get()
        self._settings.nanogpt_enabled = self._nano_var.get()
        self._settings.nanogpt_api_key = key
        self._settings.nanogpt_tray_icon = self._nano_tray_var.get()
        self._settings.save()

        self._widget.apply_settings()
        self._win.destroy()
```

- [ ] **Step 2: Run tests and import check**

Run: `uv run pytest -v` → all pass.
Run: `uv run python -c "import claude_tracker.widget"` → exit 0.

- [ ] **Step 3: Manual end-to-end check**

Note: the installed `ClaudeTracker.exe` shares `~/.claude/tracker-settings.json`; if you save settings from the **installed** app it will drop the new fields. Exit the installed app for this check (tray → Exit).

Run: `uv run python -m claude_tracker`, then via the icon open Settings and verify:

1. Click **Test** with an empty key → red `Enter an API key`.
2. Paste the NanoGPT key (with a trailing space) → **Test** → green `Connected · active plan`.
3. Type a bogus key `sk-nano-bogus` → **Test** → red `NanoGPT key rejected. Update it in Settings.`
4. Tick NanoGPT **Enabled** with an empty key → **Save** → red `Enter an API key`, dialog stays open.
5. Real key, NanoGPT enabled → **Save** → a second icon with a blue stripe appears; tooltip `NanoGPT: Wk …%  |  Img …%`; popup shows both sections, NanoGPT with `Weekly tokens · …M / 60M`, `Daily images · … / 100`, `renews Oct 11`.
6. Untick **Show NanoGPT tray icon** → Save → blue icon disappears, popup still shows NanoGPT.
7. Untick Claude **Enabled** → Save → popup shows only NanoGPT; the Claude icon remains greyed with tooltip `Claude Tracker` (since NanoGPT has no icon) and still opens the popup.
8. Untick both → Save → popup reads `No providers enabled. Turn one on in Settings.`
9. Restore: Claude on, NanoGPT on with tray icon → Save. Open `~/.claude/tracker-settings.json` and confirm the key has no whitespace.
10. Disconnect network (or set an invalid proxy) and click Refresh → each section shows its own error line; buttons still visible.

- [ ] **Step 4: Commit**

```bash
git add src/claude_tracker/widget.py
git commit -m "Add NanoGPT section to settings dialog

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Frozen build check

**Files:** none changed unless the build fails.

- [ ] **Step 1: Build the exe**

Run: `uv run pyinstaller build.spec --noconfirm`
Expected: `dist/ClaudeTracker.exe` built without errors (the new `claude_tracker.providers` package is found through normal imports).

- [ ] **Step 2: Run the built exe**

Exit any running tracker, run `dist\ClaudeTracker.exe`, and confirm both icons show live numbers and the popup opens. Check `~/.claude/tracker.log` has no tracebacks and no API key in it:

Run: `grep -c "sk-nano" ~/.claude/tracker.log`
Expected: `0`

- [ ] **Step 3: Commit (only if the build needed a fix, e.g. a `hiddenimports` entry)**

```bash
git add build.spec
git commit -m "Fix frozen build for providers package

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
