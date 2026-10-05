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
