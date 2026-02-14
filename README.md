# Claude Tracker

Windows system tray widget that shows your Claude Code usage limits (5-hour and 7-day) in real-time.

![Tray Icon](docs/tray_icon.png)

The icon sits in your notification area (like the keyboard or language icons) and shows both limits at a glance — top half is 5-hour, bottom half is 7-day. Colors indicate usage level: green (<50%), yellow (50-80%), pink/red (>80%).

Click the icon to see a detailed popup:

![Popup](docs/popup.png)

## Install

### Option 1: Installer (recommended)

1. Go to [Releases](../../releases) and download `ClaudeTracker-Setup.exe`
2. Run the installer — choose install location, optional desktop shortcut and Windows startup
3. To update, just run the new installer over the existing installation

### Option 2: Run from source

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```
git clone https://github.com/user/claude-tracker.git
cd claude-tracker
uv run python -m claude_tracker
```

## Prerequisites

You must be logged into Claude Code — the app reads your OAuth token from `~/.claude/.credentials.json`.

## Features

- **Split tray icon** — 5H (top) and 7D (bottom) with color-coded backgrounds and percentage numbers
- **Auto-pin** — automatically promotes the icon to always-visible in the notification area
- **Popup flyout** — click the icon for detailed usage bars, reset timers, refresh/settings/exit
- **Tooltip** — hover the icon to see `Claude: 5H 60% | 7D 42%`
- **Auto-refresh** — polls usage every 60 seconds (configurable)
- **Start on boot** — optional Windows startup (via installer or app settings)
- **Settings** — refresh interval, start on boot

## Build

### Build .exe only

```
uv add pyinstaller --dev
uv run pyinstaller build.spec
```

Output: `dist/ClaudeTracker.exe`

### Build installer

Requires [Inno Setup](https://jrsoftware.org/isinfo.php).

```
uv run pyinstaller build.spec
iscc installer.iss
```

Output: `Output/ClaudeTracker-Setup.exe`

## Settings

Stored at `~/.claude/tracker-settings.json`:

```json
{
  "refresh_interval": 60,
  "start_on_boot": false,
  "theme": "dark"
}
```

## How it works

Reads the OAuth token from `~/.claude/.credentials.json` and calls `GET https://api.anthropic.com/api/oauth/usage` with the `anthropic-beta: oauth-2025-04-20` header. Automatically refreshes expired tokens.
