"""Settings persistence for Claude Tracker."""

import json
from dataclasses import dataclass, asdict
from pathlib import Path


SETTINGS_PATH = Path.home() / ".claude" / "tracker-settings.json"


@dataclass
class Settings:
    refresh_interval: int = 60  # seconds (1 minute)
    start_on_boot: bool = False
    theme: str = "dark"

    def save(self) -> None:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls) -> "Settings":
        if not SETTINGS_PATH.exists():
            settings = cls()
            settings.save()
            return settings
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            known_fields = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in known_fields}
            return cls(**filtered)
        except (json.JSONDecodeError, TypeError):
            return cls()
