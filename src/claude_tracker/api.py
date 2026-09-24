"""Usage API client and token management."""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
# Public OAuth client ID used by Claude Code; the token endpoint rejects
# refresh requests without it (400 Bad Request).
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"


@dataclass
class UsageBucket:
    utilization: float  # percentage 0-100
    resets_at: datetime | None

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
class UsageData:
    five_hour: UsageBucket
    seven_day: UsageBucket
    error: str | None = None


def _parse_bucket(data: dict | None) -> UsageBucket:
    if not data:
        return UsageBucket(utilization=0.0, resets_at=None)
    resets_at = None
    if data.get("resets_at"):
        try:
            resets_at = datetime.fromisoformat(data["resets_at"])
        except ValueError:
            pass
    return UsageBucket(
        utilization=float(data.get("utilization", 0.0)),
        resets_at=resets_at,
    )


def _read_credentials() -> dict:
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(f"Credentials not found at {CREDENTIALS_PATH}")
    data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    return data["claudeAiOauth"]


def _save_credentials(oauth: dict) -> None:
    data = {}
    if CREDENTIALS_PATH.exists():
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    data["claudeAiOauth"] = oauth
    CREDENTIALS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _refresh_token(oauth: dict) -> dict:
    """Refresh the OAuth access token."""
    log.info("Refreshing OAuth token...")
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": oauth["refreshToken"],
        "client_id": CLIENT_ID,
    }
    if oauth.get("scopes"):
        payload["scope"] = " ".join(oauth["scopes"])
    resp = requests.post(TOKEN_URL, json=payload, timeout=15)
    if not resp.ok:
        log.error("Token refresh failed: %s %s", resp.status_code, resp.text[:300])
    resp.raise_for_status()
    new_data = resp.json()
    oauth["accessToken"] = new_data["access_token"]
    oauth["refreshToken"] = new_data.get("refresh_token", oauth["refreshToken"])
    oauth["expiresAt"] = int(time.time() * 1000) + new_data.get("expires_in", 3600) * 1000
    if new_data.get("scope"):
        oauth["scopes"] = new_data["scope"].split()
    _save_credentials(oauth)
    return oauth


def fetch_usage() -> UsageData:
    """Fetch current usage data from the Anthropic API."""
    try:
        oauth = _read_credentials()

        # Refresh if token is expired (expiresAt is in milliseconds)
        if oauth.get("expiresAt", 0) < int(time.time() * 1000):
            oauth = _refresh_token(oauth)

        resp = requests.get(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {oauth['accessToken']}",
                "anthropic-beta": "oauth-2025-04-20",
            },
            timeout=15,
        )

        if resp.status_code == 401:
            # Try refreshing the token once
            oauth = _refresh_token(oauth)
            resp = requests.get(
                USAGE_URL,
                headers={
                    "Authorization": f"Bearer {oauth['accessToken']}",
                    "anthropic-beta": "oauth-2025-04-20",
                },
                timeout=15,
            )

        resp.raise_for_status()
        data = resp.json()

        return UsageData(
            five_hour=_parse_bucket(data.get("five_hour")),
            seven_day=_parse_bucket(data.get("seven_day")),
        )

    except FileNotFoundError as e:
        log.error("Credentials file not found: %s", e)
        return UsageData(
            five_hour=UsageBucket(0.0, None),
            seven_day=UsageBucket(0.0, None),
            error="No credentials found. Log in to Claude Code first.",
        )
    except requests.RequestException as e:
        log.error("API request failed: %s", e)
        return UsageData(
            five_hour=UsageBucket(0.0, None),
            seven_day=UsageBucket(0.0, None),
            error=f"API error: {e}",
        )
    except Exception as e:
        log.error("Unexpected error: %s", e)
        return UsageData(
            five_hour=UsageBucket(0.0, None),
            seven_day=UsageBucket(0.0, None),
            error=str(e),
        )
