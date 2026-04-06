"""Integration tests for multi-character module end-to-end flows."""

import json
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude" / "modules" / "multi-character" / "lib"))


def make_empty_campaign(tmp_path):
    """Campaign with no characters at all."""
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
    return campaign_dir


def make_single_char_campaign(tmp_path):
    """Campaign with old-style character.json."""
    campaign_dir = make_empty_campaign(tmp_path)
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
    (campaign_dir / "character.json").write_text(json.dumps(char, ensure_ascii=False))
    return campaign_dir


class TestFirstCharacterCreation:
    """Creating the first character in an empty campaign."""

    def test_first_char_creates_characters_dir(self, tmp_path):
        from multi_character import save_character, is_multi_character
        from party import add_to_party
        campaign_dir = make_empty_campaign(tmp_path)

        char = {"id": "theron-oakshade", "name": "Theron Oakshade", "class": "Ranger", "level": 1}
        save_character(campaign_dir, char)
        add_to_party(campaign_dir, "theron-oakshade")

        assert is_multi_character(campaign_dir) is True
        assert (campaign_dir / "characters" / "theron-oakshade.json").exists()

        overview = json.loads((campaign_dir / "campaign-overview.json").read_text())
        assert overview["party"] == ["theron-oakshade"]


class TestSecondCharacterMigration:
    """Adding a second character triggers migration from character.json."""

    def test_migration_then_add(self, tmp_path):
        from multi_character import save_character, migrate_to_multi, is_multi_character, list_characters
        from party import add_to_party, get_party
        campaign_dir = make_single_char_campaign(tmp_path)

        # Simulate what the middleware does: detect single-char, migrate, then save
        assert not is_multi_character(campaign_dir)
        migrate_to_multi(campaign_dir)
        assert is_multi_character(campaign_dir)
        assert not (campaign_dir / "character.json").exists()

        # Add second character
        new_char = {
            "id": "lyra-moonwhisper",
            "name": "Lyra Moonwhisper",
            "race": "Elf",
            "class": "Wizard",
            "level": 1,
            "hp": {"current": 8, "max": 8},
        }
        save_character(campaign_dir, new_char)
        add_to_party(campaign_dir, "lyra-moonwhisper")

        # Verify both characters exist
        chars = list_characters(campaign_dir)
        assert len(chars) == 2

        party = get_party(campaign_dir)
        assert "theron-oakshade" in party
        assert "lyra-moonwhisper" in party


class TestSingleCharCampaignUnchanged:
    """Single-character campaigns that never add a second PC work as before."""

    def test_single_char_not_migrated(self, tmp_path):
        from multi_character import is_multi_character
        campaign_dir = make_single_char_campaign(tmp_path)
        assert is_multi_character(campaign_dir) is False
        assert (campaign_dir / "character.json").exists()


class TestPartyRoundTrip:
    """Add then remove then re-add a character."""

    def test_remove_and_readd(self, tmp_path):
        from multi_character import save_character
        from party import add_to_party, remove_from_party, get_party
        campaign_dir = make_empty_campaign(tmp_path)

        char = {"id": "theron-oakshade", "name": "Theron Oakshade", "class": "Ranger", "level": 1}
        save_character(campaign_dir, char)
        add_to_party(campaign_dir, "theron-oakshade")
        assert get_party(campaign_dir) == ["theron-oakshade"]

        remove_from_party(campaign_dir, "theron-oakshade")
        assert get_party(campaign_dir) == []

        # Character file still exists
        assert (campaign_dir / "characters" / "theron-oakshade.json").exists()

        add_to_party(campaign_dir, "theron-oakshade")
        assert get_party(campaign_dir) == ["theron-oakshade"]


class TestDuplicateCharacterId:
    """Saving a character with the same ID overwrites (no duplicate files)."""

    def test_overwrite_same_id(self, tmp_path):
        from multi_character import save_character, list_characters
        campaign_dir = make_empty_campaign(tmp_path)

        char_v1 = {"id": "theron-oakshade", "name": "Theron Oakshade", "class": "Ranger", "level": 1}
        save_character(campaign_dir, char_v1)

        char_v2 = {"id": "theron-oakshade", "name": "Theron Oakshade", "class": "Fighter", "level": 3}
        save_character(campaign_dir, char_v2)

        chars = list_characters(campaign_dir)
        assert len(chars) == 1
        assert chars[0]["class"] == "Fighter"


class TestEmptyParty:
    """Removing all members results in empty party, no crashes."""

    def test_empty_party_operations(self, tmp_path):
        from party import get_party, get_party_characters, remove_from_party
        campaign_dir = make_empty_campaign(tmp_path)
        # No party field at all
        assert get_party(campaign_dir) == []
        assert get_party_characters(campaign_dir) == []
        # Removing from empty party is a no-op
        remove_from_party(campaign_dir, "nobody")
        assert get_party(campaign_dir) == []
