"""Tests for InventoryManager configurable character_file parameter."""

import json
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".claude" / "modules" / "inventory-system" / "lib"))


def make_campaign_with_inventory(tmp_path, use_multi=False):
    """Create a campaign with character data for inventory testing."""
    campaign_dir = tmp_path / "campaigns" / "test-campaign"
    campaign_dir.mkdir(parents=True)

    char = {
        "id": "theron-oakshade",
        "name": "Theron Oakshade",
        "race": "Human",
        "class": "Ranger",
        "level": 1,
        "hp": {"current": 12, "max": 12},
        "ac": 14,
        "stats": {"str": 15, "dex": 16, "con": 14, "int": 9, "wis": 13, "cha": 11},
        "equipment": ["Longbow", "20 Arrows"],
        "gold": 50,
        "xp": {"current": 0, "next_level": 300},
    }

    if use_multi:
        chars_dir = campaign_dir / "characters"
        chars_dir.mkdir()
        (chars_dir / "theron-oakshade.json").write_text(
            json.dumps(char, ensure_ascii=False)
        )
    else:
        (campaign_dir / "character.json").write_text(
            json.dumps(char, ensure_ascii=False)
        )

    return campaign_dir


class TestInventoryManagerCharacterFile:
    def test_default_loads_character_json(self, tmp_path):
        from inventory_manager import InventoryManager
        campaign_dir = make_campaign_with_inventory(tmp_path, use_multi=False)
        mgr = InventoryManager(campaign_dir)
        assert mgr.character["name"] == "Theron Oakshade"

    def test_custom_path_loads_from_characters_dir(self, tmp_path):
        from inventory_manager import InventoryManager
        campaign_dir = make_campaign_with_inventory(tmp_path, use_multi=True)
        mgr = InventoryManager(campaign_dir, character_file="characters/theron-oakshade.json")
        assert mgr.character["name"] == "Theron Oakshade"

    def test_custom_path_saves_to_correct_file(self, tmp_path):
        from inventory_manager import InventoryManager
        campaign_dir = make_campaign_with_inventory(tmp_path, use_multi=True)
        mgr = InventoryManager(campaign_dir, character_file="characters/theron-oakshade.json")
        mgr.character["gold"] = 999
        mgr._save_character()
        saved = json.loads((campaign_dir / "characters" / "theron-oakshade.json").read_text())
        assert saved["gold"] == 999
