import json

from claude_tracker import config


def test_old_settings_file_gets_defaults(monkeypatch, tmp_path):
    path = tmp_path / "tracker-settings.json"
    path.write_text(json.dumps({"refresh_interval": 90, "start_on_boot": True, "theme": "dark"}))
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    s = config.Settings.load()
    assert s.refresh_interval == 90
    assert s.claude_enabled is True
    assert s.nanogpt_enabled is False
    assert s.nanogpt_api_key == ""
    assert s.nanogpt_tray_icon is True


def test_null_api_key_coerced(monkeypatch, tmp_path):
    path = tmp_path / "tracker-settings.json"
    path.write_text(json.dumps({"nanogpt_enabled": True, "nanogpt_api_key": None}))
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    assert config.Settings.load().nanogpt_api_key == ""


def test_round_trip(monkeypatch, tmp_path):
    path = tmp_path / "tracker-settings.json"
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    s = config.Settings(nanogpt_enabled=True, nanogpt_api_key="sk-nano-test")
    s.save()
    loaded = config.Settings.load()
    assert loaded.nanogpt_enabled is True
    assert loaded.nanogpt_api_key == "sk-nano-test"
