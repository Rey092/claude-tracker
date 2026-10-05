"""Tk rendering checks for the popup (needs a Windows desktop session)."""

import pytest

from claude_tracker import widget as widget_mod
from claude_tracker.config import Settings
from claude_tracker.providers.base import ProviderUsage, UsageBucket


# One Tk root per process: uv's standalone Python can't re-init Tcl for a second root.
@pytest.fixture(scope="module")
def _shared_tracker():
    mp = pytest.MonkeyPatch()
    mp.setattr(widget_mod, "_get_tray_notify_rect", lambda: None)
    w = widget_mod.TrackerWidget(Settings(nanogpt_enabled=True, nanogpt_api_key="k"))
    yield w
    w.root.destroy()
    mp.undo()


@pytest.fixture
def tracker(_shared_tracker):
    yield _shared_tracker
    _shared_tracker._close_popup()


def _bucket(label: str) -> UsageBucket:
    return UsageBucket(label, "X", 50.0, None, "1 / 2")


def _assert_popup_fits(tracker) -> None:
    tracker._show_popup()
    popup = tracker._popup_win
    popup.update()
    needed = max(child.winfo_reqheight() for child in popup.winfo_children())
    assert popup.winfo_height() >= needed


def test_popup_fits_two_providers(tracker):
    tracker._last_usage = {
        "claude": ProviderUsage("claude", [_bucket("a"), _bucket("b")]),
        "nanogpt": ProviderUsage("nanogpt", [_bucket("c"), _bucket("d")], subtitle="renews Oct 11"),
    }
    _assert_popup_fits(tracker)


def test_popup_fits_long_error(tracker):
    tracker._last_usage = {
        "claude": ProviderUsage("claude", error="Claude login expired. Run `claude` in a terminal and use /login."),
        "nanogpt": ProviderUsage("nanogpt", error="NanoGPT key rejected. Update it in Settings."),
    }
    _assert_popup_fits(tracker)
