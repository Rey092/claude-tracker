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
