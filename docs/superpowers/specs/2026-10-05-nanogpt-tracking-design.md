# NanoGPT subscription tracking — design

Date: 2026-10-05
Status: draft, awaiting review

## Goal

Track a NanoGPT subscription's usage limits in Claude Tracker alongside Claude Code,
with the same at-a-glance tray experience. Claude tracking keeps working unchanged
for users who never configure NanoGPT.

## Success criteria

- With a valid NanoGPT API key configured, a second tray icon shows weekly-token %
  (top) and daily-image % (bottom), and the popup shows a NanoGPT section with bars,
  absolute amounts, and reset timers.
- With no key configured (default), the app looks and behaves exactly as today.
- Errors in one provider (bad key, network) never blank out the other provider.
- Either provider can be disabled in Settings.

## NanoGPT API

`GET https://nano-gpt.com/api/subscription/v1/usage` with header
`x-api-key: <key>` (also accepts `Authorization: Bearer <key>`). Relevant response
fields (verified against a live key):

```json
{
  "active": true,
  "state": "active",
  "limits": {"weeklyInputTokens": 60000000, "dailyInputTokens": null, "dailyImages": 100},
  "period": {"currentPeriodEnd": "2026-10-11T04:18:21.000Z"},
  "weeklyInputTokens": {"used": 631288, "remaining": 59368712, "percentUsed": 0.0105, "resetAt": 1791763200000},
  "dailyInputTokens": null,
  "dailyImages": {"used": 0, "remaining": 100, "percentUsed": 0, "resetAt": 1791244800000}
}
```

- `percentUsed` is a **fraction 0–1** → multiply by 100.
- `resetAt` is **epoch milliseconds**.
- A bucket is `null` when the plan has no such limit → hide it.
- `active: false` → show "No active NanoGPT subscription" as the section error.
- HTTP 401/403 → "NanoGPT key rejected. Update it in Settings."

## Architecture

Introduce a provider abstraction so UI code stops assuming "5h + 7d".

### Data model (`providers/base.py`)

```python
@dataclass
class UsageBucket:            # moved from api.py, unchanged API + new fields
    label: str                # "5-hour window", "Weekly tokens"
    utilization: float        # 0-100
    resets_at: datetime | None
    detail: str = ""          # "0.63M / 60M", "0 / 100"; empty for Claude
    time_until_reset: property (existing logic)

@dataclass
class ProviderUsage:
    provider_id: str          # "claude" | "nanogpt"
    title: str                # "Claude Code" | "NanoGPT"
    buckets: list[UsageBucket]
    subtitle: str = ""        # "renews Oct 11"
    error: str | None = None
```

Each provider module exposes `fetch() -> ProviderUsage` and never raises
(errors go into `error`, mirroring today's `fetch_usage`).

### Modules

| File | Change |
| --- | --- |
| `providers/__init__.py` | `enabled_providers(settings) -> list[Callable[[], ProviderUsage]]` |
| `providers/base.py` | `UsageBucket`, `ProviderUsage`, number formatting helper (`631288 → "0.63M"`) |
| `providers/claude.py` | Current `api.py` logic moved here; returns `ProviderUsage` with buckets `5-hour window`, `7-day window` |
| `providers/nanogpt.py` | New. Calls the endpoint above with `settings.nanogpt_api_key`; buckets in fixed order: weekly tokens, daily tokens, daily images (null ones dropped) |
| `api.py` | Removed (imports updated) |
| `config.py` | New fields: `claude_enabled: bool = True`, `nanogpt_enabled: bool = False`, `nanogpt_api_key: str = ""`, `nanogpt_tray_icon: bool = True` |
| `tray.py` | `TrayManager` per provider (see Tray) |
| `widget.py` | Popup and settings rendered from `list[ProviderUsage]` |

The API key is stored in **plain text** in `~/.claude/tracker-settings.json`
(user decision). It is never logged; log lines show at most the last 4 chars.

### Polling

`refresh()` calls each enabled provider's `fetch()` in turn on the Tk thread (same as
today; two short HTTP calls with 15 s timeouts). Results stored as
`self._last_usage: dict[str, ProviderUsage]`. One refresh interval applies to all.

## UI

### Tray

- One pystray icon per enabled provider that has a tray icon turned on
  (Claude: always while enabled; NanoGPT: `nanogpt_tray_icon`).
- Same split rendering. Top/bottom values = the provider's first two buckets
  (Claude: 5h/7d; NanoGPT: weekly tokens / daily images). If a provider has only
  one bucket, both halves show it.
- New 3-px left stripe in the provider accent color: Claude `#D85A30` (coral),
  NanoGPT `#378ADD` (blue).
- Tooltips: `Claude: 5H 60%  |  7D 42%`, `NanoGPT: Wk 1%  |  Img 0%`; on error
  `<Title>: <error>` truncated to 127 chars.
- Each icon gets its own pystray name/title (`claude_tracker`, `claude_tracker_nanogpt`)
  so Windows tracks them separately; auto-pin matches either tooltip prefix.
- Left-click on any icon toggles the same shared popup; menus identical.
- Toggling providers/tray icon in Settings starts/stops icons without restart.

**Verified (2026-10-05 probe):** two pystray `Icon`s, each in its own thread, register
and update independently on Windows 11 (pystray gives each instance its own window
class, hWnd and uID). Fallback, only if field issues appear: a single icon that rotates
between enabled providers every 5 s (the left stripe shows which one is displayed;
tooltip always lists both).

### Popup

- Sections stacked in provider order (Claude, NanoGPT), separated by a 1-px line.
- Section header: accent dot + title, optional right-aligned subtitle ("renews Oct 11").
- Each bucket row as today; label includes `detail` when present
  ("Weekly tokens · 0.63M / 60M").
- Section error shown as an amber line under the header, replacing its bars.
- Popup height computed from content (header + rows + buttons) instead of fixed 220.
- Window title becomes "Usage" when more than one provider is enabled; stays
  "Claude Code Usage" otherwise.

### Settings dialog

Below the existing fields:

- "Claude Code" row — `Enabled` checkbox.
- "NanoGPT" row — `Enabled` checkbox, `API key` entry (masked with `show="•"`),
  `Test` button (runs `nanogpt.fetch()` with the typed key, shows
  "Connected · active plan" or the error inline), `Show NanoGPT tray icon` checkbox.
- Saving with NanoGPT enabled and an empty key shows inline "Enter an API key"
  and doesn't save.
- Dialog height grows to fit (~380 px).

## Error handling

| Case | Behavior |
| --- | --- |
| No key / NanoGPT disabled | Provider not polled, no section, no icon |
| 401/403 | Section error "NanoGPT key rejected. Update it in Settings." |
| `active: false` | Section error "No active NanoGPT subscription" |
| Network/other | Section error "NanoGPT API error: …" (short) |
| Both providers disabled | Popup shows "No providers enabled. Turn one on in Settings." and the Claude icon stays (grey) so the app remains reachable |

## Testing

No tests exist today. Add `pytest` as a dev dependency and:

- `tests/test_nanogpt.py` — parse the sample response above (fraction → %, ms → datetime,
  null buckets dropped, detail formatting), 401 → error, `active:false` → error,
  using a mocked `requests.get`.
- `tests/test_claude.py` — existing parsing still produces two buckets.
- `tests/test_config.py` — old settings file without new keys loads with defaults.
- Manual: run from source with the test key, check both icons, popup, settings
  Test button, disabling each provider, bad key.

## Out of scope

- Pay-as-you-go NanoGPT balance (`/api/check-balance`).
- Per-provider refresh intervals.
- Encrypted key storage.
- README/screenshots update (follow-up after the UI lands).
