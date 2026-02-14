"""Entry point for Claude Code Usage Tracker."""

import logging

from claude_tracker.config import Settings
from claude_tracker.startup import is_startup_enabled, set_startup
from claude_tracker.tray import TrayManager
from claude_tracker.widget import TrackerWidget

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)


def main() -> None:
    log.info("Starting Claude Tracker...")

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


if __name__ == "__main__":
    main()
