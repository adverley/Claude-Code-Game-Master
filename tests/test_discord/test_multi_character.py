"""Test that PlayerManager supports characters/ directory for multi-player Discord sessions."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from player_manager import PlayerManager


def make_multi_character_campaign(tmp_path):
    """Campaign with characters/ directory instead of character.json."""
    campaign_dir = tmp_path / "world-state" / "campaigns" / "test-campaign"
    campaign_dir.mkdir(parents=True)
    ws = tmp_path / "world-state"
    (ws / "active-campaign.txt").write_text("test-campaign")

    overview = {
        "campaign_name": "Test Campaign",
        "time_of_day": "Day",
        "current_date": "Day 1",
    }
    (campaign_dir / "campaign-overview.json").write_text(
        json.dumps(overview, ensure_ascii=False)
    )

    chars_dir = campaign_dir / "characters"
    chars_dir.mkdir()

    thorin = {
        "name": "Thorin",
        "level": 3,
        "hp": {"current": 30, "max": 35},
        "gold": 200,
        "xp": 1000,
        "equipment": ["Warhammer", "Shield"],
    }
    (chars_dir / "thorin.json").write_text(json.dumps(thorin, ensure_ascii=False))

    elara = {
        "name": "Elara",
        "level": 3,
        "hp": {"current": 22, "max": 22},
        "gold": 150,
        "xp": 900,
        "equipment": ["Longbow", "Arrows"],
    }
    (chars_dir / "elara.json").write_text(json.dumps(elara, ensure_ascii=False))

    return str(ws), campaign_dir


class TestMultiCharacter:
    def test_load_character_from_characters_dir(self, tmp_path):
        ws, camp = make_multi_character_campaign(tmp_path)
        mgr = PlayerManager(ws)
        char = mgr.get_player("thorin")
        assert char is not None
        assert char["name"] == "Thorin"
        assert char["level"] == 3

    def test_list_players_from_characters_dir(self, tmp_path):
        ws, camp = make_multi_character_campaign(tmp_path)
        mgr = PlayerManager(ws)
        players = mgr.list_players()
        assert "thorin" in players
        assert "elara" in players

    def test_modify_hp_multi_character(self, tmp_path):
        ws, camp = make_multi_character_campaign(tmp_path)
        mgr = PlayerManager(ws)
        result = mgr.modify_hp("thorin", -10)
        assert result["success"] is True
        assert result["current_hp"] == 20

        # Elara should be unaffected
        elara = mgr.get_player("elara")
        assert elara["hp"]["current"] == 22

    def test_show_all_players_multi(self, tmp_path):
        ws, camp = make_multi_character_campaign(tmp_path)
        mgr = PlayerManager(ws)
        summaries = mgr.show_all_players()
        assert len(summaries) == 2
