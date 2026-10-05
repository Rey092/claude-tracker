import pytest

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


class FakeIcon:
    """Stands in for pystray.Icon; `on_init` simulates other threads racing construction."""
    on_init = None

    def __init__(self, name, icon, title, menu):
        self.name, self.icon, self.title = name, icon, title
        self.visible = False
        self.stopped = False
        if FakeIcon.on_init:
            FakeIcon.on_init()

    def run(self, setup=None):
        # pystray calls setup in its own thread once the icon is registered.
        if setup:
            setup(self)
        else:
            self.visible = True

    def stop(self):
        self.stopped = True


@pytest.fixture
def fake_pystray(monkeypatch):
    from claude_tracker import tray
    monkeypatch.setattr(tray.pystray, "Icon", FakeIcon)
    monkeypatch.setattr(tray, "_promote_tray_icon", lambda: None)
    FakeIcon.on_init = None
    yield tray
    FakeIcon.on_init = None


def test_usage_arriving_during_icon_creation_is_shown(fake_pystray):
    tm = fake_pystray.TrayManager(None, "claude")
    latest = _usage("claude", ("5H", 60.0), ("7D", 42.0))
    FakeIcon.on_init = lambda: tm.show_usage(latest)
    tm._run()
    expected = _create_split_icon(60.0, 42.0, accent="#D85A30")
    assert tm._icon.icon.tobytes() == expected.tobytes()
    assert tm._icon.title == "Claude: 5H 60%  |  7D 42%"
    assert tm._icon.visible is True


def test_stop_before_run_never_creates_icon(fake_pystray):
    tm = fake_pystray.TrayManager(None, "nanogpt")
    tm.stop()
    tm._run()
    assert tm._icon is None


def test_stop_during_icon_creation_stops_icon(fake_pystray):
    tm = fake_pystray.TrayManager(None, "nanogpt")
    FakeIcon.on_init = tm.stop
    tm._run()
    assert tm._icon.stopped is True
    assert tm._icon.visible is False
