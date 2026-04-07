import json
import pytest
from pathlib import Path
from discord_bot.player_map import PlayerMap


def make_player_map_file(tmp_path, data=None):
    path = tmp_path / "player-map.json"
    if data is not None:
        path.write_text(json.dumps(data))
    return path


class TestPlayerMap:
    def test_load_existing_file(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {
                "111": {"discord_name": "Erik", "character": "thorin"}
            }
        })
        pm = PlayerMap(path)
        assert pm.get_character("111") == "thorin"
        assert pm.get_discord_name("111") == "Erik"

    def test_missing_user_returns_none(self, tmp_path):
        path = make_player_map_file(tmp_path, {"players": {}})
        pm = PlayerMap(path)
        assert pm.get_character("999") is None
        assert pm.get_discord_name("999") is None

    def test_join_adds_player(self, tmp_path):
        path = make_player_map_file(tmp_path, {"players": {}})
        pm = PlayerMap(path)
        pm.join("222", "Sara", "elara")

        assert pm.get_character("222") == "elara"
        assert pm.get_discord_name("222") == "Sara"

        # Verify persisted to disk
        reloaded = json.loads(path.read_text())
        assert reloaded["players"]["222"]["character"] == "elara"

    def test_join_overwrites_existing(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "thorin"}}
        })
        pm = PlayerMap(path)
        pm.join("111", "Erik", "gandalf")
        assert pm.get_character("111") == "gandalf"

    def test_creates_file_if_missing(self, tmp_path):
        path = tmp_path / "player-map.json"
        pm = PlayerMap(path)
        pm.join("111", "Erik", "thorin")
        assert path.exists()
        assert pm.get_character("111") == "thorin"

    def test_get_all_players(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {
                "111": {"discord_name": "Erik", "character": "thorin"},
                "222": {"discord_name": "Sara", "character": "elara"},
            }
        })
        pm = PlayerMap(path)
        players = pm.get_all()
        assert len(players) == 2

    def test_get_user_id_by_character_found(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {
                "111": {"discord_name": "Erik", "character": "thorin"},
                "222": {"discord_name": "Sara", "character": "elara"},
            }
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("thorin") == "111"
        assert pm.get_user_id_by_character("elara") == "222"

    def test_get_user_id_by_character_case_insensitive(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "thorin"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("THORIN") == "111"
        assert pm.get_user_id_by_character("Thorin") == "111"

    def test_get_user_id_by_character_not_found(self, tmp_path):
        path = make_player_map_file(tmp_path, {"players": {}})
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("nobody") is None
