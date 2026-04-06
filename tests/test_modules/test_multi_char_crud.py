"""Tests for multi-character module core operations."""

import json
import pytest
from pathlib import Path
import sys

# Will import from module once created
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude" / "modules" / "multi-character" / "lib"))


def make_campaign(tmp_path, with_single_char=False, with_multi_chars=False):
    """Helper to create a campaign directory for testing."""
    campaign_dir = tmp_path / "campaigns" / "test-campaign"
    campaign_dir.mkdir(parents=True)

    overview = {
        "campaign_name": "Test Campaign",
        "time_of_day": "Day",
        "current_date": "Day 1",
        "player_position": {"current_location": "Town Square"},
    }
    (campaign_dir / "campaign-overview.json").write_text(
        json.dumps(overview, ensure_ascii=False)
    )

    if with_single_char:
        char = {
            "id": "theron-oakshade",
            "name": "Theron Oakshade",
            "race": "Human",
            "class": "Ranger",
            "level": 1,
            "hp": {"current": 12, "max": 12},
            "ac": 14,
            "stats": {"str": 15, "dex": 16, "con": 14, "int": 9, "wis": 13, "cha": 11},
            "equipment": ["Longbow"],
            "gold": 10,
            "xp": {"current": 0, "next_level": 300},
        }
        (campaign_dir / "character.json").write_text(
            json.dumps(char, ensure_ascii=False)
        )

    if with_multi_chars:
        chars_dir = campaign_dir / "characters"
        chars_dir.mkdir()
        for cid, name, cls in [("theron-oakshade", "Theron Oakshade", "Ranger"),
                                ("lyra-moonwhisper", "Lyra Moonwhisper", "Wizard")]:
            char = {
                "id": cid,
                "name": name,
                "race": "Human",
                "class": cls,
                "level": 1,
                "hp": {"current": 10, "max": 10},
                "ac": 10,
                "stats": {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
                "equipment": [],
                "gold": 0,
                "xp": {"current": 0, "next_level": 300},
            }
            (chars_dir / f"{cid}.json").write_text(
                json.dumps(char, ensure_ascii=False)
            )

    return campaign_dir


class TestIsMultiCharacter:
    def test_false_when_no_characters_dir(self, tmp_path):
        from multi_character import is_multi_character
        campaign_dir = make_campaign(tmp_path, with_single_char=True)
        assert is_multi_character(campaign_dir) is False

    def test_true_when_characters_dir_exists(self, tmp_path):
        from multi_character import is_multi_character
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        assert is_multi_character(campaign_dir) is True


class TestListCharacters:
    def test_lists_all_characters(self, tmp_path):
        from multi_character import list_characters
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        chars = list_characters(campaign_dir)
        assert len(chars) == 2
        names = {c["name"] for c in chars}
        assert names == {"Theron Oakshade", "Lyra Moonwhisper"}

    def test_empty_when_no_characters(self, tmp_path):
        from multi_character import list_characters
        campaign_dir = make_campaign(tmp_path)
        chars = list_characters(campaign_dir)
        assert chars == []


class TestLoadCharacter:
    def test_load_by_id(self, tmp_path):
        from multi_character import load_character
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        char = load_character(campaign_dir, "theron-oakshade")
        assert char["name"] == "Theron Oakshade"

    def test_load_by_name_case_insensitive(self, tmp_path):
        from multi_character import load_character
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        char = load_character(campaign_dir, "lyra moonwhisper")
        assert char["id"] == "lyra-moonwhisper"

    def test_load_not_found_raises(self, tmp_path):
        from multi_character import load_character
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        with pytest.raises(FileNotFoundError, match="Available characters"):
            load_character(campaign_dir, "nobody")


class TestSaveCharacter:
    def test_save_creates_file(self, tmp_path):
        from multi_character import save_character
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        new_char = {
            "id": "gimli-son-of-gloin",
            "name": "Gimli",
            "race": "Dwarf",
            "class": "Fighter",
            "level": 1,
            "hp": {"current": 12, "max": 12},
        }
        save_character(campaign_dir, new_char)
        saved = json.loads((campaign_dir / "characters" / "gimli-son-of-gloin.json").read_text())
        assert saved["name"] == "Gimli"

    def test_save_overwrites_existing(self, tmp_path):
        from multi_character import save_character
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        char = {
            "id": "theron-oakshade",
            "name": "Theron Oakshade",
            "class": "Fighter",
            "level": 5,
        }
        save_character(campaign_dir, char)
        saved = json.loads((campaign_dir / "characters" / "theron-oakshade.json").read_text())
        assert saved["class"] == "Fighter"
        assert saved["level"] == 5


class TestFindCharacterFile:
    def test_find_by_id_exact(self, tmp_path):
        from multi_character import find_character_file
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        path = find_character_file(campaign_dir, "theron-oakshade")
        assert path == campaign_dir / "characters" / "theron-oakshade.json"

    def test_find_by_name_fallback(self, tmp_path):
        from multi_character import find_character_file
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        path = find_character_file(campaign_dir, "Lyra Moonwhisper")
        assert path == campaign_dir / "characters" / "lyra-moonwhisper.json"

    def test_find_not_found_raises(self, tmp_path):
        from multi_character import find_character_file
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        with pytest.raises(FileNotFoundError):
            find_character_file(campaign_dir, "nobody")


class TestMigrateToMulti:
    def test_migrate_moves_character(self, tmp_path):
        from multi_character import migrate_to_multi, is_multi_character
        campaign_dir = make_campaign(tmp_path, with_single_char=True)

        assert (campaign_dir / "character.json").exists()
        migrate_to_multi(campaign_dir)

        assert not (campaign_dir / "character.json").exists()
        assert (campaign_dir / "characters" / "theron-oakshade.json").exists()
        assert is_multi_character(campaign_dir) is True

        migrated = json.loads((campaign_dir / "characters" / "theron-oakshade.json").read_text())
        assert migrated["name"] == "Theron Oakshade"
        assert migrated["gold"] == 10

    def test_migrate_adds_to_party_array(self, tmp_path):
        from multi_character import migrate_to_multi
        campaign_dir = make_campaign(tmp_path, with_single_char=True)
        migrate_to_multi(campaign_dir)

        overview = json.loads((campaign_dir / "campaign-overview.json").read_text())
        assert "theron-oakshade" in overview["party"]

    def test_migrate_generates_id_from_name(self, tmp_path):
        from multi_character import migrate_to_multi
        campaign_dir = make_campaign(tmp_path)
        char = {"name": "Thorin Ironforge", "class": "Fighter", "level": 1}
        (campaign_dir / "character.json").write_text(json.dumps(char))

        migrate_to_multi(campaign_dir)
        assert (campaign_dir / "characters" / "thorin-ironforge.json").exists()

    def test_migrate_noop_when_already_multi(self, tmp_path):
        from multi_character import migrate_to_multi, list_characters
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        migrate_to_multi(campaign_dir)
        assert len(list_characters(campaign_dir)) == 2

    def test_migrate_when_no_character_exists(self, tmp_path):
        from multi_character import migrate_to_multi, is_multi_character
        campaign_dir = make_campaign(tmp_path)
        migrate_to_multi(campaign_dir)
        assert is_multi_character(campaign_dir) is True
