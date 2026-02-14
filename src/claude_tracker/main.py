"""Entry point for Claude Code Usage Tracker."""

import logging

from claude_tracker.config import Settings
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

    widget = TrackerWidget(settings)
    tray = TrayManager(widget)
    widget.set_tray(tray)

    tray.start()
    widget.start_polling()
    widget.run()


if __name__ == "__main__":
    main()
