"""System tray icon management with auto-pin support."""

import logging
import os
import threading
import winreg
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw, ImageFont

from claude_tracker.providers.base import PROVIDERS, ProviderUsage

if TYPE_CHECKING:
    from claude_tracker.widget import TrackerWidget

log = logging.getLogger(__name__)


def _color_for(util: float) -> str:
    """Light pastel colors for icon background so black text is readable."""
    if util >= 80:
        return "#fca5a5"  # light red / pink
    if util >= 50:
        return "#fde047"  # light yellow
    return "#86efac"  # light green


COLOR_NO_DATA = "#d4d4d8"  # light grey when a provider has no data / errored


def _create_split_icon(
    util_top: float | None = None,
    util_bot: float | None = None,
    accent: str | None = None,
    size: int = 128,
) -> Image.Image:
    """Generate a square tray icon split into top and bottom halves.

    Each half is colored by utilization and shows the percentage; ``None`` draws a
    grey half with "-". ``accent`` draws a provider stripe on the left edge.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = 6  # corner radius
    half = size // 2

    color_top = _color_for(util_top) if util_top is not None else COLOR_NO_DATA
    color_bot = _color_for(util_bot) if util_bot is not None else COLOR_NO_DATA

    # Top half with rounded top corners
    draw.rounded_rectangle([0, 0, size - 1, half], radius=r, fill=color_top)
    # Fill bottom of top half to make it flat at the seam
    draw.rectangle([0, half - r, size - 1, half], fill=color_top)

    # Bottom half with rounded bottom corners
    draw.rounded_rectangle([0, half, size - 1, size - 1], radius=r, fill=color_bot)
    # Fill top of bottom half to make it flat at the seam
    draw.rectangle([0, half, size - 1, half + r], fill=color_bot)

    # Thin separator line
    draw.line([(2, half), (size - 3, half)], fill="#00000066", width=1)

    stripe = size // 10 if accent else 0
    if accent:
        draw.rectangle([0, 0, stripe - 1, size - 1], fill=accent)

    # Fit percentage text in each half — big and bold, black text
    try:
        font = ImageFont.truetype("arialbd.ttf", size * 2 // 3)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", size * 3 // 8)
        except OSError:
            font = ImageFont.load_default()

    text_color = "#000000"
    for util, y_center in [(util_top, half // 2), (util_bot, half + half // 2)]:
        text = f"{util:.0f}" if util is not None else "-"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = stripe + (size - stripe - tw) // 2 - bbox[0]
        ty = y_center - th // 2 - bbox[1]
        draw.text((tx, ty), text, fill=text_color, font=font)

    return img


def icon_values(usage: ProviderUsage | None) -> tuple[float | None, float | None]:
    """Top/bottom utilization for a provider's icon; (None, None) means grey."""
    if usage is None or usage.error or not usage.buckets:
        return None, None
    top = usage.buckets[0].utilization
    bot = usage.buckets[1].utilization if len(usage.buckets) > 1 else top
    return top, bot


def tooltip_for(provider_id: str, usage: ProviderUsage | None) -> str:
    # Windows caps tray tooltips at 127 chars
    if usage is None:
        return "Claude Tracker"
    short = PROVIDERS[provider_id].short
    if usage.error:
        return f"{short}: {usage.error}"[:127]
    parts = [f"{b.short} {b.utilization:.0f}%" for b in usage.buckets[:2]]
    return f"{short}: {'  |  '.join(parts)}"[:127]


def _promote_tray_icon() -> bool:
    """Try to auto-pin (promote) our tray icon so it's always visible."""
    try:
        exe_path = os.path.abspath(os.sys.executable).lower()
        key_path = r"Control Panel\NotifyIconSettings"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

        promoted = False
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                i += 1
            except OSError:
                break
            try:
                subkey = winreg.OpenKey(key, subkey_name, access=winreg.KEY_READ | winreg.KEY_SET_VALUE)
                try:
                    tooltip = ""
                    try:
                        tooltip, _ = winreg.QueryValueEx(subkey, "InitialTooltip")
                    except FileNotFoundError:
                        pass

                    path_val = ""
                    try:
                        path_val, _ = winreg.QueryValueEx(subkey, "ExecutablePath")
                    except FileNotFoundError:
                        pass

                    is_ours = (tooltip.startswith("Claude Tracker") or
                               (path_val and exe_path in path_val.lower()))

                    if is_ours:
                        try:
                            current, _ = winreg.QueryValueEx(subkey, "IsPromoted")
                            if current == 1:
                                promoted = True
                                continue
                        except FileNotFoundError:
                            pass
                        winreg.SetValueEx(subkey, "IsPromoted", 0, winreg.REG_DWORD, 1)
                        log.info("Promoted tray icon: %s", subkey_name)
                        promoted = True
                except Exception:
                    pass
                finally:
                    winreg.CloseKey(subkey)
            except OSError:
                continue

        winreg.CloseKey(key)
        if promoted:
            _restart_explorer_tray()
        return promoted
    except Exception as e:
        log.warning("Could not auto-promote tray icon: %s", e)
        return False


def _restart_explorer_tray() -> None:
    import ctypes
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "TraySettings")


class TrayManager:
    def __init__(self, widget: "TrackerWidget", provider_id: str) -> None:
        self._widget = widget
        self.provider_id = provider_id
        self._accent = PROVIDERS[provider_id].accent
        self._usage: ProviderUsage | None = None
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None
        # Set once the shell has registered the icon (pystray setup callback).
        self._ready = threading.Event()
        self._stopped = threading.Event()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        if self._stopped.is_set():
            return
        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide", self._on_toggle, default=True),
            pystray.MenuItem("Refresh", self._on_refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", self._on_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        )
        suffix = "" if self.provider_id == "claude" else f"_{self.provider_id}"
        # The initial tooltip is what Windows stores as InitialTooltip; auto-pin
        # matches on its "Claude Tracker" prefix.
        title = "Claude Tracker" if self.provider_id == "claude" else f"Claude Tracker {PROVIDERS[self.provider_id].title}"
        self._icon = pystray.Icon(
            f"claude_tracker{suffix}",
            icon=_create_split_icon(*icon_values(self._usage), accent=self._accent),
            title=title,
            menu=menu,
        )
        threading.Timer(2.0, _promote_tray_icon).start()
        self._icon.run(setup=self._on_ready)

    def _on_ready(self, icon: pystray.Icon) -> None:
        # Runs on pystray's setup thread after the icon is registered with its
        # initial tooltip, so updating the title no longer affects auto-pin.
        if self._stopped.is_set():
            icon.stop()
            return
        icon.visible = True
        self._ready.set()
        self._apply(self._usage)

    def _apply(self, usage: ProviderUsage | None) -> None:
        if self._icon:
            self._icon.icon = _create_split_icon(*icon_values(usage), accent=self._accent)
            self._icon.title = tooltip_for(self.provider_id, usage)

    def show_usage(self, usage: ProviderUsage | None) -> None:
        self._usage = usage
        if self._ready.is_set():
            self._apply(usage)

    def stop(self) -> None:
        self._stopped.set()
        if self._icon:
            self._icon.stop()

    def _on_toggle(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._widget.root.after(0, self._widget.toggle_popup)

    def _on_refresh(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._widget.root.after(0, self._widget.refresh)

    def _on_settings(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._widget.root.after(0, self._widget.open_settings)

    def _on_exit(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        self._widget.root.after(0, self._widget.quit_app)
