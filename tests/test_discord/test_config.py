import json
import pytest
from pathlib import Path


def write_config(tmp_path, data):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))
    return config_path


class TestLoadConfig:
    def test_loads_valid_config(self, tmp_path):
        from discord_bot.config import load_config

        path = write_config(tmp_path, {
            "bot_token": "test-token-123",
            "channel_id": "999888777",
            "campaign": "lost-mines",
        })
        cfg = load_config(path)
        assert cfg["bot_token"] == "test-token-123"
        assert cfg["channel_id"] == "999888777"
        assert cfg["campaign"] == "lost-mines"
        assert cfg["message_buffer_size"] == 50  # default

    def test_missing_required_field_raises(self, tmp_path):
        from discord_bot.config import load_config

        path = write_config(tmp_path, {
            "bot_token": "test-token-123",
            # missing channel_id and campaign
        })
        with pytest.raises(ValueError, match="channel_id"):
            load_config(path)

    def test_custom_buffer_size(self, tmp_path):
        from discord_bot.config import load_config

        path = write_config(tmp_path, {
            "bot_token": "tok",
            "channel_id": "123",
            "campaign": "test",
            "message_buffer_size": 100,
        })
        cfg = load_config(path)
        assert cfg["message_buffer_size"] == 100

    def test_missing_file_raises(self, tmp_path):
        from discord_bot.config import load_config

        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.json")
