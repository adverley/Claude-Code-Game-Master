"""Tests for party roster management."""

import json
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude" / "modules" / "multi-character" / "lib"))


def make_campaign_with_party(tmp_path, party=None, with_chars=True):
    """Create campaign with optional party array and character files."""
    campaign_dir = tmp_path / "campaigns" / "test-campaign"
    campaign_dir.mkdir(parents=True)

    overview = {
        "campaign_name": "Test Campaign",
        "time_of_day": "Day",
        "current_date": "Day 1",
        "player_position": {"current_location": "Town Square"},
    }
    if party is not None:
        overview["party"] = party
    (campaign_dir / "campaign-overview.json").write_text(
        json.dumps(overview, ensure_ascii=False)
    )

    if with_chars:
        chars_dir = campaign_dir / "characters"
        chars_dir.mkdir()
        for cid, name in [("theron-oakshade", "Theron Oakshade"),
                          ("lyra-moonwhisper", "Lyra Moonwhisper")]:
            char = {"id": cid, "name": name, "race": "Human", "class": "Fighter",
                    "level": 1, "hp": {"current": 10, "max": 10}}
            (chars_dir / f"{cid}.json").write_text(json.dumps(char, ensure_ascii=False))

    return campaign_dir


class TestGetParty:
    def test_returns_party_array(self, tmp_path):
        from party import get_party
        campaign_dir = make_campaign_with_party(
            tmp_path, party=["theron-oakshade", "lyra-moonwhisper"]
        )
        assert get_party(campaign_dir) == ["theron-oakshade", "lyra-moonwhisper"]

    def test_returns_empty_when_no_party_field(self, tmp_path):
        from party import get_party
        campaign_dir = make_campaign_with_party(tmp_path, party=None)
        assert get_party(campaign_dir) == []


class TestAddToParty:
    def test_adds_character_id(self, tmp_path):
        from party import add_to_party, get_party
        campaign_dir = make_campaign_with_party(tmp_path, party=["theron-oakshade"])
        add_to_party(campaign_dir, "lyra-moonwhisper")
        assert get_party(campaign_dir) == ["theron-oakshade", "lyra-moonwhisper"]

    def test_creates_party_array_if_missing(self, tmp_path):
        from party import add_to_party, get_party
        campaign_dir = make_campaign_with_party(tmp_path, party=None)
        add_to_party(campaign_dir, "theron-oakshade")
        assert get_party(campaign_dir) == ["theron-oakshade"]

    def test_no_duplicate(self, tmp_path):
        from party import add_to_party, get_party
        campaign_dir = make_campaign_with_party(tmp_path, party=["theron-oakshade"])
        add_to_party(campaign_dir, "theron-oakshade")
        assert get_party(campaign_dir) == ["theron-oakshade"]


class TestRemoveFromParty:
    def test_removes_character_id(self, tmp_path):
        from party import remove_from_party, get_party
        campaign_dir = make_campaign_with_party(
            tmp_path, party=["theron-oakshade", "lyra-moonwhisper"]
        )
        remove_from_party(campaign_dir, "theron-oakshade")
        assert get_party(campaign_dir) == ["lyra-moonwhisper"]

    def test_noop_when_not_in_party(self, tmp_path):
        from party import remove_from_party, get_party
        campaign_dir = make_campaign_with_party(tmp_path, party=["theron-oakshade"])
        remove_from_party(campaign_dir, "nobody")
        assert get_party(campaign_dir) == ["theron-oakshade"]

    def test_empty_party_after_last_removal(self, tmp_path):
        from party import remove_from_party, get_party
        campaign_dir = make_campaign_with_party(tmp_path, party=["theron-oakshade"])
        remove_from_party(campaign_dir, "theron-oakshade")
        assert get_party(campaign_dir) == []


class TestGetPartyCharacters:
    def test_loads_all_party_member_data(self, tmp_path):
        from party import get_party_characters
        campaign_dir = make_campaign_with_party(
            tmp_path, party=["theron-oakshade", "lyra-moonwhisper"]
        )
        chars = get_party_characters(campaign_dir)
        assert len(chars) == 2
        names = {c["name"] for c in chars}
        assert names == {"Theron Oakshade", "Lyra Moonwhisper"}

    def test_skips_missing_party_members(self, tmp_path):
        from party import get_party_characters
        campaign_dir = make_campaign_with_party(
            tmp_path, party=["theron-oakshade", "nonexistent"]
        )
        chars = get_party_characters(campaign_dir)
        assert len(chars) == 1
        assert chars[0]["name"] == "Theron Oakshade"
