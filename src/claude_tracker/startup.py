"""Windows startup registry management."""

import logging
import sys
import winreg

log = logging.getLogger(__name__)

REG_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "ClaudeTracker"


def _get_exe_path() -> str:
    """Get the path to the running executable or script."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return f'"{sys.executable}" -m claude_tracker'


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
