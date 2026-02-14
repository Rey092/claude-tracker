"""System tray icon management with auto-pin support."""

import logging
import os
import threading
import winreg
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw, ImageFont

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


def _create_split_icon(
    util_5h: float = 0.0,
    util_7d: float = 0.0,
    size: int = 128,
) -> Image.Image:
    """Generate a square tray icon split into top (5H) and bottom (7D) halves.

    Each half is colored by utilization and shows the percentage if it fits.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = 6  # corner radius
    half = size // 2

    color_top = _color_for(util_5h)
    color_bot = _color_for(util_7d)

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

    # Fit percentage text in each half — big and bold, black text
    try:
        font = ImageFont.truetype("arialbd.ttf", size * 2 // 3)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", size * 3 // 8)
        except OSError:
            font = ImageFont.load_default()

    text_color = "#000000"
    for util, y_center in [(util_5h, half // 2), (util_7d, half + half // 2)]:
        text = f"{util:.0f}"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (size - tw) // 2 - bbox[0]
        ty = y_center - th // 2 - bbox[1]
        draw.text((tx, ty), text, fill=text_color, font=font)

    return img


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

                    is_ours = (tooltip == "Claude Tracker" or
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
    def __init__(self, widget: "TrackerWidget") -> None:
        self._widget = widget
        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Show / Hide", self._on_toggle, default=True),
            pystray.MenuItem("Refresh", self._on_refresh),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", self._on_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        )
        self._icon = pystray.Icon(
            "claude_tracker",
            icon=_create_split_icon(),
            title="Claude Tracker",
            menu=menu,
        )
        threading.Timer(2.0, _promote_tray_icon).start()
        self._icon.run()

    def update_icon(self, util_5h: float, util_7d: float) -> None:
        if self._icon:
            self._icon.icon = _create_split_icon(util_5h, util_7d)

    def update_tooltip(self, text: str) -> None:
        if self._icon:
            self._icon.title = text

    def stop(self) -> None:
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
