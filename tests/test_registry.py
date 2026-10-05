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
