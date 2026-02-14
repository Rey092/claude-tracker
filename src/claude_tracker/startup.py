"""Windows startup registry management."""

import logging
import os
import sys
import winreg
from pathlib import Path

log = logging.getLogger(__name__)

REG_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "ClaudeTracker"
EXE_NAME = "ClaudeTracker.exe"


def _find_installed_exe() -> str | None:
    """Search for the installed or built exe."""
    candidates = [
        # Inno Setup install (non-admin) — {autopf}
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ClaudeTracker" / EXE_NAME,
        # Inno Setup install (admin) — {pf}
        Path(os.environ.get("PROGRAMFILES", "")) / "ClaudeTracker" / EXE_NAME,
        # Dev build output
        Path(__file__).resolve().parent.parent.parent / "dist" / EXE_NAME,
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _get_exe_path() -> str:
    """Get the path to the exe for startup registration."""
    # Running as PyInstaller exe — use the running exe directly
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --startup'

    # Running from source — prefer the built/installed exe
    found = _find_installed_exe()
    if found:
        return f'"{found}" --startup'

    # Last resort fallback
    return f'"{sys.executable}" -m claude_tracker --startup'


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable_startup() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _get_exe_path())
        log.info("Startup enabled")
    except OSError as e:
        log.error("Failed to enable startup: %s", e)


def disable_startup() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
        log.info("Startup disabled")
    except FileNotFoundError:
        pass
    except OSError as e:
        log.error("Failed to disable startup: %s", e)


def set_startup(enabled: bool) -> None:
    if enabled:
        enable_startup()
    else:
        disable_startup()
