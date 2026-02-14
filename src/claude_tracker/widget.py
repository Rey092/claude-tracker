"""Tray-icon-driven popup flyout UI.

The system tray icon is the primary interface (pinned like keyboard/language
icons). Click the tray icon to show a detailed popup flyout above the
notification area.
"""

import ctypes
import ctypes.wintypes
import logging
import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk

from claude_tracker.api import UsageData, fetch_usage
from claude_tracker.config import Settings
from claude_tracker.startup import is_startup_enabled, set_startup

if TYPE_CHECKING:
    from claude_tracker.tray import TrayManager

log = logging.getLogger(__name__)

# Colors
POPUP_BG = "#1e1e2e"
POPUP_BORDER = "#3a3a4a"
COLOR_FG = "#e0e0e0"
COLOR_LABEL = "#888888"
COLOR_GREEN = "#22c55e"
COLOR_YELLOW = "#eab308"
COLOR_RED = "#ef4444"
COLOR_BAR_BG = "#333333"

user32 = ctypes.windll.user32


def _color_for(util: float) -> str:
    if util >= 80:
        return COLOR_RED
    if util >= 50:
        return COLOR_YELLOW
    return COLOR_GREEN


def _get_tray_notify_rect() -> tuple[int, int, int, int] | None:
    taskbar = user32.FindWindowW("Shell_TrayWnd", None)
    if not taskbar:
        return None
    tray = user32.FindWindowExW(taskbar, 0, "TrayNotifyWnd", None)
    if not tray:
        return None
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(tray, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


class TrackerWidget:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tray: "TrayManager | None" = None
        self._refresh_job: str | None = None
        self._popup_win: ctk.CTkToplevel | None = None
        self._last_usage: UsageData | None = None
        self._popup_5h: dict | None = None
        self._popup_7d: dict | None = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title("")
        self.root.overrideredirect(True)
        self.root.withdraw()  # hidden — tray icon is the UI

    def _get_dpi_scale(self) -> float:
        try:
            return ctk.ScalingTracker.get_window_scaling(self.root)
        except Exception:
            return 1.0

    # ── Popup Flyout ─────────────────────────────────────────────

    def toggle_popup(self) -> None:
        if self._popup_win and self._popup_win.winfo_exists():
            self._close_popup()
        else:
            self._show_popup()

    def _show_popup(self) -> None:
        if self._popup_win and self._popup_win.winfo_exists():
            return

        popup = ctk.CTkToplevel(self.root)
        popup.title("")
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        popup.configure(fg_color=POPUP_BG)
        self._popup_win = popup

        popup_w, popup_h = 300, 220
        scale = self._get_dpi_scale()
        popup_w_phys = int(popup_w * scale)
        popup_h_phys = int(popup_h * scale)

        # Position above the notification area
        tray_rect = _get_tray_notify_rect()
        if tray_rect:
            tray_cx = (tray_rect[0] + tray_rect[2]) // 2
            x = tray_cx - popup_w_phys // 2
            y = tray_rect[1] - popup_h_phys - 12
        else:
            sw_phys = int(self.root.winfo_screenwidth() * scale)
            sh_phys = int(self.root.winfo_screenheight() * scale)
            x = sw_phys - popup_w_phys - 20
            y = sh_phys - popup_h_phys - 60

        # Keep on screen
        screen_w_phys = int(self.root.winfo_screenwidth() * scale)
        x = max(8, min(x, screen_w_phys - popup_w_phys - 8))

        popup.geometry(f"{popup_w}x{popup_h}+{x}+{y}")

        self._build_popup(popup)
        if self._last_usage:
            self._update_popup(self._last_usage)

        popup.bind("<FocusOut>", lambda _: self.root.after(200, self._close_popup_if_inactive))
        popup.after(100, lambda: popup.focus_force())

    def _build_popup(self, popup: ctk.CTkToplevel) -> None:
        frame = ctk.CTkFrame(popup, fg_color=POPUP_BG, corner_radius=10,
                             border_width=1, border_color=POPUP_BORDER)
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(frame, text="Claude Code Usage",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLOR_FG).pack(anchor="w", padx=14, pady=(12, 8))

        self._popup_5h = self._build_popup_row(frame, "5-Hour Window")
        self._popup_7d = self._build_popup_row(frame, "7-Day Window")

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=14, pady=(10, 12))

        ctk.CTkButton(btn_frame, text="Refresh", width=70, height=28,
                      command=self.refresh, fg_color="#333344",
                      hover_color="#444455", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkButton(btn_frame, text="Settings", width=70, height=28,
                      command=self.open_settings, fg_color="#333344",
                      hover_color="#444455", font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Exit", width=50, height=28,
                      command=self.quit_app, fg_color="#442222",
                      hover_color="#553333", font=ctk.CTkFont(size=11)).pack(side="right")

    def _build_popup_row(self, parent: ctk.CTkFrame, title: str) -> dict:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 6))

        header = ctk.CTkFrame(row, fg_color="transparent")
        header.pack(fill="x")
        ctk.CTkLabel(header, text=title, font=ctk.CTkFont(size=11),
                     text_color=COLOR_LABEL).pack(side="left")
        timer = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=10),
                             text_color=COLOR_LABEL)
        timer.pack(side="right")

        bar_row = ctk.CTkFrame(row, fg_color="transparent")
        bar_row.pack(fill="x", pady=(2, 0))
        bar = ctk.CTkProgressBar(bar_row, height=12, corner_radius=4,
                                 fg_color=COLOR_BAR_BG, progress_color=COLOR_GREEN)
        bar.set(0)
        bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        pct = ctk.CTkLabel(bar_row, text="0%", font=ctk.CTkFont(size=12, weight="bold"),
                           text_color=COLOR_FG, width=40, anchor="e")
        pct.pack(side="right")

        return {"bar": bar, "pct": pct, "timer": timer}

    def _update_popup(self, usage: UsageData) -> None:
        if not self._popup_win or not self._popup_win.winfo_exists():
            return
        for bucket, row in [(usage.five_hour, self._popup_5h), (usage.seven_day, self._popup_7d)]:
            if row is None:
                continue
            color = _color_for(bucket.utilization)
            row["bar"].configure(progress_color=color)
            row["bar"].set(bucket.utilization / 100.0)
            row["pct"].configure(text=f"{bucket.utilization:.0f}%")
            row["timer"].configure(text=f"resets {bucket.time_until_reset}" if bucket.time_until_reset else "")

    def _close_popup(self) -> None:
        if self._popup_win and self._popup_win.winfo_exists():
            self._popup_win.destroy()
        self._popup_win = None
        self._popup_5h = None
        self._popup_7d = None

    def _close_popup_if_inactive(self) -> None:
        if not self._popup_win or not self._popup_win.winfo_exists():
            return
        try:
            focused = self._popup_win.focus_get()
            if focused:
                return
        except KeyError:
            pass
        self._close_popup()

    # ── Public API ───────────────────────────────────────────────

    def set_tray(self, tray: "TrayManager") -> None:
        self.tray = tray

    def refresh(self) -> None:
        log.info("Refreshing usage data...")
        usage = fetch_usage()
        self._apply_usage(usage)

    def _apply_usage(self, usage: UsageData) -> None:
        self._last_usage = usage
        self._update_popup(usage)

        if self.tray:
            self.tray.update_icon(usage.five_hour.utilization, usage.seven_day.utilization)
            self.tray.update_tooltip(
                f"Claude: 5H {usage.five_hour.utilization:.0f}%  |  7D {usage.seven_day.utilization:.0f}%"
            )

    def start_polling(self) -> None:
        self._poll()

    def _poll(self) -> None:
        self.refresh()
        interval_ms = self.settings.refresh_interval * 1000
        self._refresh_job = self.root.after(interval_ms, self._poll)

    def show(self) -> None:
        pass  # root stays hidden; popup is the visible UI

    def hide_to_tray(self) -> None:
        self._close_popup()

    def open_settings(self) -> None:
        self._close_popup()
        SettingsDialog(self)

    def quit_app(self) -> None:
        self._close_popup()
        if self._refresh_job:
            self.root.after_cancel(self._refresh_job)
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


class SettingsDialog:
    def __init__(self, widget: TrackerWidget) -> None:
        self._widget = widget
        self._settings = widget.settings

        self._win = ctk.CTkToplevel(widget.root)
        self._win.title("Claude Tracker Settings")
        self._win.geometry("320x200")
        self._win.resizable(False, False)
        self._win.attributes("-topmost", True)
        self._win.configure(fg_color=POPUP_BG)
        self._win.grab_set()

        self._build()

    def _build(self) -> None:
        pad = {"padx": 16, "pady": (8, 0)}

        ctk.CTkLabel(self._win, text="Refresh interval (seconds):",
                     text_color=COLOR_FG).pack(anchor="w", **pad)
        self._interval_var = tk.StringVar(value=str(self._settings.refresh_interval))
        ctk.CTkEntry(self._win, textvariable=self._interval_var, width=100,
                     fg_color=COLOR_BAR_BG, text_color=COLOR_FG).pack(anchor="w", padx=16, pady=4)

        self._boot_var = tk.BooleanVar(value=is_startup_enabled())
        ctk.CTkCheckBox(self._win, text="Start on boot", variable=self._boot_var,
                        text_color=COLOR_FG, fg_color=COLOR_GREEN,
                        hover_color="#16a34a").pack(anchor="w", **pad)

        btn_frame = ctk.CTkFrame(self._win, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=16)
        ctk.CTkButton(btn_frame, text="Save", width=80, command=self._save,
                      fg_color=COLOR_GREEN, hover_color="#16a34a",
                      text_color="#000000").pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text="Cancel", width=80, command=self._win.destroy,
                      fg_color=COLOR_BAR_BG, hover_color="#45475a").pack(side="right")

    def _save(self) -> None:
        try:
            interval = max(30, int(self._interval_var.get()))
            self._settings.refresh_interval = interval
        except ValueError:
            pass

        set_startup(self._boot_var.get())
        self._settings.start_on_boot = self._boot_var.get()
        self._settings.save()

        if self._widget._refresh_job:
            self._widget.root.after_cancel(self._widget._refresh_job)
        self._widget.start_polling()

        self._win.destroy()
