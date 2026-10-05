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
