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

    def test_get_user_id_by_character_first_name_match(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "Aldric Ironfeld"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("Aldric") == "111"
        assert pm.get_user_id_by_character("aldric") == "111"

    def test_get_user_id_by_character_exact_beats_first_name(self, tmp_path):
        path = make_player_map_file(tmp_path, {
            "players": {
                "111": {"discord_name": "Erik", "character": "Aldric Ironfeld"},
                "222": {"discord_name": "Sara", "character": "Aldric"},
            }
        })
        pm = PlayerMap(path)
        # Exact match on "Aldric" should return Sara, not Erik
        assert pm.get_user_id_by_character("Aldric") == "222"

    def test_get_user_id_by_character_not_found(self, tmp_path):
        path = make_player_map_file(tmp_path, {"players": {}})
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("nobody") is None

    def test_get_user_id_by_character_slug(self, tmp_path):
        """[PRIVATE:aldric-ironfeld] should match 'Aldric Ironfeld'."""
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "Aldric Ironfeld"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("aldric-ironfeld") == "111"

    def test_get_user_id_by_character_underscore(self, tmp_path):
        """aldric_ironfeld should match 'Aldric Ironfeld'."""
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "Aldric Ironfeld"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("aldric_ironfeld") == "111"

    def test_get_user_id_by_character_concatenated(self, tmp_path):
        """aldricironfeld should match 'Aldric Ironfeld'."""
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "Aldric Ironfeld"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("aldricironfeld") == "111"

    def test_get_user_id_by_character_accented(self, tmp_path):
        """Accented input should match after unicode normalization."""
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "Aldric Ironfeld"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("Áldrïc Ïrönféld") == "111"

    def test_get_user_id_by_character_last_name(self, tmp_path):
        """Last name alone should match."""
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "Aldric Ironfeld"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("Ironfeld") == "111"

    def test_get_user_id_by_character_middle_name(self, tmp_path):
        """Middle name should match for 3+-part names."""
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Sara", "character": "Tara Von Strudel"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("Von") == "111"

    def test_get_user_id_by_character_exact_beats_normalized(self, tmp_path):
        """Exact match takes priority over normalized match."""
        path = make_player_map_file(tmp_path, {
            "players": {
                "111": {"discord_name": "Erik", "character": "Aldric-Ironfeld"},
                "222": {"discord_name": "Sara", "character": "Aldric Ironfeld"},
            }
        })
        pm = PlayerMap(path)
        # 'aldric-ironfeld' is exact for 111, not just normalized
        assert pm.get_user_id_by_character("Aldric-Ironfeld") == "111"

    def test_get_user_id_by_character_apostrophe(self, tmp_path):
        """Names with apostrophes like D'Artagnan should match slug forms."""
        path = make_player_map_file(tmp_path, {
            "players": {"111": {"discord_name": "Erik", "character": "D'Artagnan"}}
        })
        pm = PlayerMap(path)
        assert pm.get_user_id_by_character("dartagnan") == "111"
        assert pm.get_user_id_by_character("d-artagnan") == "111"

