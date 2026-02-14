"""Entry point for Claude Code Usage Tracker."""

import logging
import sys
import time
from pathlib import Path

LOG_PATH = Path.home() / ".claude" / "tracker.log"


def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
        ],
    )


def main() -> None:
    _setup_logging()
    log = logging.getLogger(__name__)

    is_autostart = "--startup" in sys.argv

    try:
        if is_autostart:
            log.info("Auto-start mode — waiting for desktop to be ready...")
            time.sleep(5)

        log.info("Starting Claude Tracker...")

        from claude_tracker.config import Settings
        from claude_tracker.startup import is_startup_enabled, set_startup
        from claude_tracker.tray import TrayManager
        from claude_tracker.widget import TrackerWidget

        settings = Settings.load()

        # Re-apply startup registry entry if setting is enabled but registry
        # was lost (e.g. after Windows reinstall).
        if settings.start_on_boot and not is_startup_enabled():
            log.info("Restoring missing startup registry entry")
            set_startup(True)

        widget = TrackerWidget(settings)
        tray = TrayManager(widget)
        widget.set_tray(tray)

        tray.start()
        widget.start_polling()
        widget.run()
    except Exception:
        log.exception("Fatal error during startup")
        sys.exit(1)


if __name__ == "__main__":
    main()
