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
