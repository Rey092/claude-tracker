"""Tray-icon-driven popup flyout UI.

The system tray icon is the primary interface (pinned like keyboard/language
icons). Click the tray icon to show a detailed popup flyout above the
notification area.
"""

import ctypes
import ctypes.wintypes
import logging
import math
import threading
import tkinter as tk

import customtkinter as ctk

from claude_tracker.config import Settings
from claude_tracker.providers import enabled_provider_ids, fetch_provider, nanogpt, tray_provider_ids
from claude_tracker.providers.base import PROVIDERS, ProviderUsage, UsageBucket
from claude_tracker.startup import is_startup_enabled, set_startup
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
COLOR_WARN = "#fbbf24"
POPUP_W = 300
NO_PROVIDERS_MESSAGE = "No providers enabled. Turn one on in Settings."
WAITING_MESSAGE = "Waiting for data…"

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
        self.trays: dict[str, TrayManager] = {}
        self._refresh_job: str | None = None
        self._popup_win: ctk.CTkToplevel | None = None
        self._popup_frame: ctk.CTkFrame | None = None
        self._popup_content: ctk.CTkFrame | None = None
        self._last_usage: dict[str, ProviderUsage] = {}

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

        self._build_popup(popup)
        self._render_popup()

        popup.bind("<FocusOut>", lambda _: self.root.after(200, self._close_popup_if_inactive))
        popup.after(100, lambda: popup.focus_force())

    def _place_popup(self, popup_h: int) -> None:
        """Size the popup and anchor it above the notification area."""
        popup_w = POPUP_W
        scale = self._get_dpi_scale()
        popup_w_phys = int(popup_w * scale)
        popup_h_phys = int(popup_h * scale)

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

        self._popup_win.geometry(f"{popup_w}x{popup_h}+{x}+{y}")

    def _build_popup(self, popup: ctk.CTkToplevel) -> None:
        frame = ctk.CTkFrame(popup, fg_color=POPUP_BG, corner_radius=10,
                             border_width=1, border_color=POPUP_BORDER)
        frame.pack(fill="both", expand=True)
        self._popup_frame = frame

        self._popup_content = ctk.CTkFrame(frame, fg_color="transparent")
        self._popup_content.pack(fill="x", pady=(12, 0))

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=14, pady=(10, 12))

        ctk.CTkButton(btn_frame, text="Refresh", width=70, height=28,
                      command=self.refresh, fg_color="#333344",
                      hover_color="#444455", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkButton(btn_frame, text="Settings", width=70, height=28,
                      command=self.open_settings, fg_color="#333344",
                      hover_color="#444455", font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
        ctk.CTkButton(btn_frame, text="Exit", width=50, height=28,
                      command=self.quit_app, fg_color="#442222",
                      hover_color="#553333", font=ctk.CTkFont(size=11)).pack(side="right")

    def _render_popup(self) -> None:
        """Rebuild the provider sections from the latest data and resize."""
        if not self._popup_win or not self._popup_win.winfo_exists() or not self._popup_content:
            return
        for child in self._popup_content.winfo_children():
            child.destroy()

        ids = enabled_provider_ids(self.settings)
        if not ids:
            self._build_message(self._popup_content, NO_PROVIDERS_MESSAGE, COLOR_LABEL)
        for i, pid in enumerate(ids):
            if i:
                ctk.CTkFrame(self._popup_content, height=1, fg_color=POPUP_BORDER).pack(
                    fill="x", padx=14, pady=6)
            self._build_section(self._popup_content, pid, self._last_usage.get(pid))

        # Size to what the widgets actually request (physical px) so nothing clips.
        self._popup_frame.update_idletasks()
        needed = self._popup_frame.winfo_reqheight()
        self._place_popup(math.ceil(needed / self._get_dpi_scale()))

    def _build_section(self, parent: ctk.CTkFrame, pid: str, usage: ProviderUsage | None) -> None:
        meta = PROVIDERS[pid]
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(0, 6))
        ctk.CTkLabel(header, text="■", text_color=meta.accent, width=12,
                     font=ctk.CTkFont(size=12)).pack(side="left")
        ctk.CTkLabel(header, text=meta.title, text_color=COLOR_FG,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(4, 0))
        if usage and usage.subtitle:
            ctk.CTkLabel(header, text=usage.subtitle, text_color=COLOR_LABEL,
                         font=ctk.CTkFont(size=10)).pack(side="right")

        if usage is None:
            self._build_message(parent, WAITING_MESSAGE, COLOR_LABEL)
        elif usage.error:
            self._build_message(parent, usage.error, COLOR_WARN)
        else:
            for bucket in usage.buckets:
                self._build_bucket_row(parent, bucket)

    def _build_message(self, parent: ctk.CTkFrame, text: str, color: str) -> None:
        ctk.CTkLabel(parent, text=text, text_color=color, font=ctk.CTkFont(size=11),
                     wraplength=POPUP_W - 30, justify="left").pack(anchor="w", padx=14, pady=(0, 6))

    def _build_bucket_row(self, parent: ctk.CTkFrame, bucket: UsageBucket) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 6))

        header = ctk.CTkFrame(row, fg_color="transparent")
        header.pack(fill="x")
        title = f"{bucket.label} · {bucket.detail}" if bucket.detail else bucket.label
        ctk.CTkLabel(header, text=title, font=ctk.CTkFont(size=11),
                     text_color=COLOR_LABEL).pack(side="left")
        reset = f"resets {bucket.time_until_reset}" if bucket.time_until_reset else ""
        ctk.CTkLabel(header, text=reset, font=ctk.CTkFont(size=10),
                     text_color=COLOR_LABEL).pack(side="right")

        bar_row = ctk.CTkFrame(row, fg_color="transparent")
        bar_row.pack(fill="x", pady=(2, 0))
        bar = ctk.CTkProgressBar(bar_row, height=12, corner_radius=4, fg_color=COLOR_BAR_BG,
                                 progress_color=_color_for(bucket.utilization))
        bar.set(min(1.0, max(0.0, bucket.utilization / 100.0)))
        bar.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(bar_row, text=f"{bucket.utilization:.0f}%",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=COLOR_FG, width=40, anchor="e").pack(side="right")

    def _close_popup(self) -> None:
        if self._popup_win and self._popup_win.winfo_exists():
            self._popup_win.destroy()
        self._popup_win = None
        self._popup_frame = None
        self._popup_content = None

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

    def sync_tray_icons(self) -> None:
        """Start/stop tray icons to match the current settings."""
        wanted = tray_provider_ids(self.settings)
        for pid in list(self.trays):
            if pid not in wanted:
                self.trays.pop(pid).stop()
        for pid in wanted:
            if pid not in self.trays:
                tray = TrayManager(self, pid)
                self.trays[pid] = tray
                tray.show_usage(self._last_usage.get(pid))
                tray.start()

    def refresh(self) -> None:
        log.info("Refreshing usage data...")
        results = {pid: fetch_provider(pid, self.settings)
                   for pid in enabled_provider_ids(self.settings)}
        self._apply_usage(results)

    def _apply_usage(self, results: dict[str, ProviderUsage]) -> None:
        self._last_usage = results
        self._render_popup()
        for pid, tray in self.trays.items():
            tray.show_usage(results.get(pid))

    def apply_settings(self) -> None:
        """Re-sync icons and restart polling after settings change."""
        if self._refresh_job:
            self.root.after_cancel(self._refresh_job)
            self._refresh_job = None
        self._last_usage = {}
        self.sync_tray_icons()
        self.start_polling()

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
        for tray in self.trays.values():
            tray.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


class SettingsDialog:
    def __init__(self, widget: TrackerWidget) -> None:
        self._widget = widget
        self._settings = widget.settings

        self._win = ctk.CTkToplevel(widget.root)
        self._win.title("Claude Tracker Settings")
        self._win.geometry("340x420")
        self._win.resizable(False, False)
        self._win.attributes("-topmost", True)
        self._win.configure(fg_color=POPUP_BG)
        self._win.grab_set()

        self._build()

    def _section_header(self, title: str, accent: str, variable: tk.BooleanVar) -> None:
        row = ctk.CTkFrame(self._win, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 0))
        ctk.CTkLabel(row, text="■", text_color=accent, width=12).pack(side="left")
        ctk.CTkLabel(row, text=title, text_color=COLOR_FG,
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=(4, 0))
        ctk.CTkCheckBox(row, text="Enabled", variable=variable, text_color=COLOR_FG,
                        fg_color=COLOR_GREEN, hover_color="#16a34a").pack(side="right")

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

        ctk.CTkFrame(self._win, height=1, fg_color=POPUP_BORDER).pack(fill="x", padx=16, pady=(12, 0))

        self._claude_var = tk.BooleanVar(value=self._settings.claude_enabled)
        self._section_header(PROVIDERS["claude"].title, PROVIDERS["claude"].accent, self._claude_var)

        self._nano_var = tk.BooleanVar(value=self._settings.nanogpt_enabled)
        self._section_header(PROVIDERS["nanogpt"].title, PROVIDERS["nanogpt"].accent, self._nano_var)

        ctk.CTkLabel(self._win, text="API key", text_color=COLOR_LABEL,
                     font=ctk.CTkFont(size=11)).pack(anchor="w", padx=16, pady=(6, 0))
        key_row = ctk.CTkFrame(self._win, fg_color="transparent")
        key_row.pack(fill="x", padx=16, pady=(2, 0))
        self._key_var = tk.StringVar(value=self._settings.nanogpt_api_key)
        ctk.CTkEntry(key_row, textvariable=self._key_var, show="•", width=230,
                     fg_color=COLOR_BAR_BG, text_color=COLOR_FG).pack(side="left")
        ctk.CTkButton(key_row, text="Test", width=60, command=self._test_key,
                      fg_color="#333344", hover_color="#444455").pack(side="right")

        self._status = ctk.CTkLabel(self._win, text="", font=ctk.CTkFont(size=11),
                                    text_color=COLOR_LABEL, wraplength=300, justify="left")
        self._status.pack(anchor="w", padx=16, pady=(4, 0))

        self._nano_tray_var = tk.BooleanVar(value=self._settings.nanogpt_tray_icon)
        ctk.CTkCheckBox(self._win, text="Show NanoGPT tray icon", variable=self._nano_tray_var,
                        text_color=COLOR_FG, fg_color=COLOR_GREEN,
                        hover_color="#16a34a").pack(anchor="w", **pad)

        btn_frame = ctk.CTkFrame(self._win, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=16, pady=16)
        ctk.CTkButton(btn_frame, text="Save", width=80, command=self._save,
                      fg_color=COLOR_GREEN, hover_color="#16a34a",
                      text_color="#000000").pack(side="right", padx=(8, 0))
        ctk.CTkButton(btn_frame, text="Cancel", width=80, command=self._win.destroy,
                      fg_color=COLOR_BAR_BG, hover_color="#45475a").pack(side="right")

    def _set_status(self, text: str, color: str) -> None:
        try:
            if self._win.winfo_exists():
                self._status.configure(text=text, text_color=color)
        except tk.TclError:
            pass  # dialog closed while a test was running

    def _test_key(self) -> None:
        key = self._key_var.get().strip()
        if not key:
            self._set_status(nanogpt.NO_KEY_MESSAGE, COLOR_RED)
            return
        self._set_status("Testing…", COLOR_LABEL)

        def work() -> None:
            result = nanogpt.fetch(key)
            self._widget.root.after(0, lambda: self._show_test_result(result))

        threading.Thread(target=work, daemon=True).start()

    def _show_test_result(self, result: ProviderUsage) -> None:
        if result.error:
            self._set_status(result.error, COLOR_RED)
        else:
            self._set_status("Connected · active plan", COLOR_GREEN)

    def _save(self) -> None:
        key = self._key_var.get().strip()
        if self._nano_var.get() and not key:
            self._set_status(nanogpt.NO_KEY_MESSAGE, COLOR_RED)
            return

        try:
            interval = max(30, int(self._interval_var.get()))
            self._settings.refresh_interval = interval
        except ValueError:
            pass

        set_startup(self._boot_var.get())
        self._settings.start_on_boot = self._boot_var.get()
        self._settings.claude_enabled = self._claude_var.get()
        self._settings.nanogpt_enabled = self._nano_var.get()
        self._settings.nanogpt_api_key = key
        self._settings.nanogpt_tray_icon = self._nano_tray_var.get()
        self._settings.save()

        self._widget.apply_settings()
        self._win.destroy()
