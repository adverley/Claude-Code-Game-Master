# Multi-Character Campaign Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable campaigns to have multiple playable characters stored in a `characters/` directory, managed by a new `.claude/modules/multi-character/` module with party roster tracking.

**Architecture:** A new module provides `multi_character.py` (character CRUD + migration) and `party.py` (roster management). Middleware scripts intercept `dm-player.sh` and `dm-inventory.sh` to route to the correct character file. The `InventoryManager` gets a small patch to accept a configurable character file path.

**Tech Stack:** Python 3.11+, Bash (middleware), pytest (testing), `uv run python` for all Python execution.

**Spec:** `docs/superpowers/specs/2026-04-06-multi-character-support-design.md`

---

### Task 1: Core multi_character.py — character CRUD

**Files:**
- Create: `.claude/modules/multi-character/lib/multi_character.py`
- Test: `tests/test_modules/test_multi_character.py`

- [ ] **Step 1: Create test file with tests for multi_character.py**

```python
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
            "class": "Fighter",  # changed from Ranger
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

        # Verify data preserved
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
        # Create character without id field
        char = {"name": "Thorin Ironforge", "class": "Fighter", "level": 1}
        (campaign_dir / "character.json").write_text(json.dumps(char))

        migrate_to_multi(campaign_dir)
        assert (campaign_dir / "characters" / "thorin-ironforge.json").exists()

    def test_migrate_noop_when_already_multi(self, tmp_path):
        from multi_character import migrate_to_multi, list_characters
        campaign_dir = make_campaign(tmp_path, with_multi_chars=True)
        migrate_to_multi(campaign_dir)  # should not crash
        assert len(list_characters(campaign_dir)) == 2

    def test_migrate_when_no_character_exists(self, tmp_path):
        from multi_character import migrate_to_multi, is_multi_character
        campaign_dir = make_campaign(tmp_path)
        migrate_to_multi(campaign_dir)
        # Should create characters/ dir but nothing else
        assert is_multi_character(campaign_dir) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_modules/test_multi_character.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'multi_character'`

- [ ] **Step 3: Create the module directory structure**

```bash
mkdir -p .claude/modules/multi-character/lib
mkdir -p .claude/modules/multi-character/middleware
mkdir -p .claude/modules/multi-character/tools
mkdir -p tests/test_modules
```

- [ ] **Step 4: Implement multi_character.py**

Create `.claude/modules/multi-character/lib/multi_character.py`:

```python
"""Core multi-character operations: CRUD, migration, file resolution."""

import json
from pathlib import Path
from typing import Dict, List, Optional


def _name_to_id(name: str) -> str:
    """Convert character name to file-safe ID."""
    return name.lower().replace(" ", "-").replace("'", "").replace('"', "")


def is_multi_character(campaign_dir: Path) -> bool:
    """Return True if campaign uses characters/ directory format."""
    return (campaign_dir / "characters").is_dir()


def list_characters(campaign_dir: Path) -> List[Dict]:
    """Return list of all character data dicts from characters/ directory."""
    chars_dir = campaign_dir / "characters"
    if not chars_dir.is_dir():
        return []
    characters = []
    for f in sorted(chars_dir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                characters.append(json.load(fh))
        except (json.JSONDecodeError, IOError):
            continue
    return characters


def find_character_file(campaign_dir: Path, name: str) -> Path:
    """Resolve a character name to its file path.

    Searches by id first (exact filename match), then falls back to matching
    the name field inside each JSON file (case-insensitive).
    Raises FileNotFoundError listing available characters if not found.
    """
    chars_dir = campaign_dir / "characters"
    if not chars_dir.is_dir():
        raise FileNotFoundError(f"No characters/ directory in {campaign_dir}")

    # Try exact id match (filename)
    id_guess = _name_to_id(name)
    id_path = chars_dir / f"{id_guess}.json"
    if id_path.exists():
        return id_path

    # Fallback: search by name field inside each file
    name_lower = name.lower()
    available = []
    for f in sorted(chars_dir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            char_name = data.get("name", "")
            available.append(f"{data.get('id', f.stem)} ({char_name})")
            if char_name.lower() == name_lower:
                return f
        except (json.JSONDecodeError, IOError):
            continue

    available_str = ", ".join(available) if available else "none"
    raise FileNotFoundError(
        f"Character '{name}' not found. Available characters: {available_str}"
    )


def load_character(campaign_dir: Path, name: str) -> Dict:
    """Load a specific character by name or ID. Raises FileNotFoundError if not found."""
    path = find_character_file(campaign_dir, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_character(campaign_dir: Path, character_data: Dict) -> Path:
    """Save character data to characters/<id>.json. Returns the file path."""
    chars_dir = campaign_dir / "characters"
    chars_dir.mkdir(parents=True, exist_ok=True)

    char_id = character_data.get("id") or _name_to_id(character_data["name"])
    file_path = chars_dir / f"{char_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(character_data, f, indent=2, ensure_ascii=False)
    return file_path


def migrate_to_multi(campaign_dir: Path) -> None:
    """Migrate single character.json to characters/ directory format.

    - If already multi-character, no-op.
    - If character.json exists, moves it to characters/<id>.json and deletes the original.
    - Updates campaign-overview.json with party array.
    - If no character.json exists, just creates the characters/ directory.
    """
    chars_dir = campaign_dir / "characters"
    single_file = campaign_dir / "character.json"

    if chars_dir.is_dir() and not single_file.exists():
        return  # Already migrated

    chars_dir.mkdir(parents=True, exist_ok=True)

    if single_file.exists():
        with open(single_file, "r", encoding="utf-8") as f:
            char_data = json.load(f)

        char_id = char_data.get("id") or _name_to_id(char_data["name"])
        char_data["id"] = char_id  # Ensure id field exists

        dest = chars_dir / f"{char_id}.json"
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(char_data, f, indent=2, ensure_ascii=False)

        single_file.unlink()

        # Update campaign overview with party array
        overview_file = campaign_dir / "campaign-overview.json"
        if overview_file.exists():
            with open(overview_file, "r", encoding="utf-8") as f:
                overview = json.load(f)
            party = overview.get("party", [])
            if char_id not in party:
                party.append(char_id)
            overview["party"] = party
            with open(overview_file, "w", encoding="utf-8") as f:
                json.dump(overview, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_modules/test_multi_character.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add .claude/modules/multi-character/lib/multi_character.py tests/test_modules/test_multi_character.py
git commit -m "feat(multi-character): add core character CRUD and migration logic"
```

---

### Task 2: Party roster management — party.py

**Files:**
- Create: `.claude/modules/multi-character/lib/party.py`
- Test: `tests/test_modules/test_party.py`

- [ ] **Step 1: Write tests for party.py**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_modules/test_party.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'party'`

- [ ] **Step 3: Implement party.py**

Create `.claude/modules/multi-character/lib/party.py`:

```python
"""Party roster management — add/remove characters, load party data."""

import json
from pathlib import Path
from typing import Dict, List


def _load_overview(campaign_dir: Path) -> Dict:
    """Load campaign-overview.json."""
    overview_file = campaign_dir / "campaign-overview.json"
    with open(overview_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_overview(campaign_dir: Path, overview: Dict) -> None:
    """Save campaign-overview.json."""
    overview_file = campaign_dir / "campaign-overview.json"
    with open(overview_file, "w", encoding="utf-8") as f:
        json.dump(overview, f, indent=2, ensure_ascii=False)


def get_party(campaign_dir: Path) -> List[str]:
    """Return the party array from campaign overview, or empty list."""
    overview = _load_overview(campaign_dir)
    return overview.get("party", [])


def add_to_party(campaign_dir: Path, character_id: str) -> None:
    """Add a character ID to the party array. Creates the array if missing. No-op if already present."""
    overview = _load_overview(campaign_dir)
    party = overview.get("party", [])
    if character_id not in party:
        party.append(character_id)
    overview["party"] = party
    _save_overview(campaign_dir, overview)


def remove_from_party(campaign_dir: Path, character_id: str) -> None:
    """Remove a character ID from the party array. No-op if not present."""
    overview = _load_overview(campaign_dir)
    party = overview.get("party", [])
    party = [cid for cid in party if cid != character_id]
    overview["party"] = party
    _save_overview(campaign_dir, overview)


def get_party_characters(campaign_dir: Path) -> List[Dict]:
    """Load full character data for all party members. Skips missing characters."""
    party_ids = get_party(campaign_dir)
    chars_dir = campaign_dir / "characters"
    characters = []
    for cid in party_ids:
        char_file = chars_dir / f"{cid}.json"
        if not char_file.exists():
            continue
        try:
            with open(char_file, "r", encoding="utf-8") as f:
                characters.append(json.load(f))
        except (json.JSONDecodeError, IOError):
            continue
    return characters
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_modules/test_party.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add .claude/modules/multi-character/lib/party.py tests/test_modules/test_party.py
git commit -m "feat(multi-character): add party roster management"
```

---

### Task 3: Module metadata — module.json

**Files:**
- Create: `.claude/modules/multi-character/module.json`

- [ ] **Step 1: Create module.json**

Create `.claude/modules/multi-character/module.json`:

```json
{
  "id": "multi-character",
  "name": "Multi-Character Support",
  "version": "1.0.0",
  "author": "DM System",
  "description": "Multi-character campaign support with party roster management",
  "category": "character-mechanics",
  "genre_tags": ["fantasy", "scifi", "modern", "horror", "survival"],
  "tags": ["multi-character", "party", "multiplayer"],
  "enabled_by_default": true,
  "dependencies": [],
  "incompatible_with": [],
  "middleware": ["dm-player.sh", "dm-inventory.sh"],
  "tools": ["dm-party.sh"],
  "features": [
    "Multiple playable characters per campaign",
    "Party roster tracking in campaign overview",
    "On-demand migration from single-character format",
    "Character lookup by name or ID",
    "Party management CLI (list, add, remove)"
  ],
  "adds_to_core": {
    "tools": ["dm-party.sh"],
    "commands": {
      "dm-party.sh list": "Show all PCs in party with summary stats",
      "dm-party.sh add <name>": "Add character to party roster",
      "dm-party.sh remove <name>": "Remove character from party roster",
      "dm-party.sh migrate": "Manually trigger single-to-multi migration"
    },
    "data_fields": {
      "campaign-overview.json": {
        "party": ["<character-id>"]
      },
      "characters/<id>.json": "Same schema as character.json"
    }
  },
  "architecture": "Middleware intercepts dm-player.sh to route character commands to characters/<id>.json. Middleware intercepts dm-inventory.sh to pass --character-file. Party roster stored in campaign-overview.json party array.",
  "replaces": []
}
```

- [ ] **Step 2: Commit**

```bash
git add .claude/modules/multi-character/module.json
git commit -m "feat(multi-character): add module metadata"
```

---

### Task 4: dm-player.sh middleware

**Files:**
- Create: `.claude/modules/multi-character/middleware/dm-player.sh`
- Test: `tests/test_modules/test_multi_character_middleware.sh` (bash integration test)

- [ ] **Step 1: Create the middleware script**

Create `.claude/modules/multi-character/middleware/dm-player.sh`:

```bash
#!/bin/bash
# multi-character middleware for dm-player.sh
# Routes character commands to characters/<id>.json when in multi-character mode.
# Falls through to CORE (exit 1) when campaign uses single-character format.

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_DIR/../../.." && pwd)"

source "$PROJECT_ROOT/tools/common.sh"

if [ "$1" = "--help" ]; then
    echo ""
    echo "  Multi-Character Commands:"
    echo "    show-all                     Show all party members"
    echo "    (All commands require explicit character name in multi-character mode)"
    exit 1
fi

ACTION="$1"
shift

# Check if this campaign uses multi-character format
CAMPAIGN_DIR=$(get_campaign_dir)
if [ -z "$CAMPAIGN_DIR" ]; then
    exit 1  # No campaign, let CORE handle the error
fi

# If characters/ directory doesn't exist, fall through to CORE
if [ ! -d "$CAMPAIGN_DIR/characters" ]; then
    exit 1
fi

# In multi-character mode, route commands to the correct character file
case "$ACTION" in
    show)
        if [ -z "$1" ]; then
            # show without name: show all party members
            exec uv run python -c "
import sys, json
sys.path.insert(0, '$MODULE_DIR/lib')
from party import get_party_characters
from pathlib import Path
chars = get_party_characters(Path('$CAMPAIGN_DIR'))
if not chars:
    print('[INFO] No characters in party')
    sys.exit(0)
for c in chars:
    hp = c.get('hp', {})
    gold = c.get('gold', 0)
    conds = c.get('conditions', [])
    line = f\"{c.get('name', '?')} - {c.get('race', '?')} {c.get('class', '?')} Level {c.get('level', 1)} (HP: {hp.get('current', 0)}/{hp.get('max', 0)}, Gold: {gold})\"
    if conds:
        line += f' | Conditions: {\", \".join(conds)}'
    print(line)
"
        else
            # show <name>: show specific character
            exec $PYTHON_CMD "$LIB_DIR/player_manager.py" show "$1"
        fi
        ;;

    show-all)
        exec uv run python -c "
import sys, json
sys.path.insert(0, '$MODULE_DIR/lib')
from party import get_party_characters
from pathlib import Path
chars = get_party_characters(Path('$CAMPAIGN_DIR'))
if not chars:
    print('[INFO] No characters in party')
    sys.exit(0)
for c in chars:
    hp = c.get('hp', {})
    gold = c.get('gold', 0)
    conds = c.get('conditions', [])
    line = f\"{c.get('name', '?')} - {c.get('race', '?')} {c.get('class', '?')} Level {c.get('level', 1)} (HP: {hp.get('current', 0)}/{hp.get('max', 0)}, Gold: {gold})\"
    if conds:
        line += f' | Conditions: {\", \".join(conds)}'
    print(line)
"
        ;;

    save-json)
        # Route save to characters/<id>.json and add to party
        exec uv run python -c "
import sys, json
sys.path.insert(0, '$MODULE_DIR/lib')
from multi_character import save_character, is_multi_character, migrate_to_multi
from party import add_to_party
from pathlib import Path

campaign_dir = Path('$CAMPAIGN_DIR')
char_json = ' '.join(sys.argv[1:])
char_data = json.loads(char_json)
char_id = char_data.get('id') or char_data['name'].lower().replace(' ', '-').replace(\"'\", '').replace('\"', '')
char_data['id'] = char_id

# If character.json exists (single-char), migrate first
single_file = campaign_dir / 'character.json'
if single_file.exists() and not is_multi_character(campaign_dir):
    migrate_to_multi(campaign_dir)

path = save_character(campaign_dir, char_data)
add_to_party(campaign_dir, char_id)
result = {'success': True, 'character_id': char_id, 'file_path': str(path)}
print(json.dumps(result, indent=2, ensure_ascii=False))
" "$@"
        ;;

    get|hp|xp|gold|inventory|condition|loot|level-check)
        # These commands require a character name — pass through to CORE
        # CORE's PlayerManager already supports characters/ directory (legacy format)
        exit 1
        ;;

    list)
        # List all character IDs from characters/ directory
        exec uv run python -c "
import sys
sys.path.insert(0, '$MODULE_DIR/lib')
from multi_character import list_characters
from pathlib import Path
chars = list_characters(Path('$CAMPAIGN_DIR'))
for c in chars:
    cid = c.get('id', 'unknown')
    print(cid)
"
        ;;

    *)
        exit 1  # Unknown action, let CORE handle
        ;;
esac
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x .claude/modules/multi-character/middleware/dm-player.sh
```

- [ ] **Step 3: Commit**

```bash
git add .claude/modules/multi-character/middleware/dm-player.sh
git commit -m "feat(multi-character): add dm-player.sh middleware"
```

---

### Task 5: dm-party.sh CLI tool

**Files:**
- Create: `.claude/modules/multi-character/tools/dm-party.sh`

- [ ] **Step 1: Create dm-party.sh**

Create `.claude/modules/multi-character/tools/dm-party.sh`:

```bash
#!/usr/bin/env bash
# dm-party.sh — Party roster management CLI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_ROOT/../../.." && pwd)"

source "$PROJECT_ROOT/tools/common.sh"
require_active_campaign

ACTION="${1:-}"
shift 2>/dev/null || true

CAMPAIGN_DIR=$(get_campaign_dir)

case "$ACTION" in
    list)
        uv run python -c "
import sys, json
sys.path.insert(0, '$MODULE_ROOT/lib')
from party import get_party_characters
from pathlib import Path
chars = get_party_characters(Path('$CAMPAIGN_DIR'))
if not chars:
    print('[INFO] No characters in party')
    sys.exit(0)
print('Party Members:')
print('-' * 60)
for c in chars:
    hp = c.get('hp', {})
    gold = c.get('gold', 0)
    print(f\"  {c.get('name', '?')} - {c.get('race', '?')} {c.get('class', '?')} Lv{c.get('level', 1)} (HP: {hp.get('current', 0)}/{hp.get('max', 0)}, Gold: {gold})\")
print(f'\nTotal: {len(chars)} character(s)')
"
        ;;

    add)
        if [ -z "${1:-}" ]; then
            echo "Usage: dm-party.sh add <character-name>"
            exit 1
        fi
        NAME="$1"
        uv run python -c "
import sys
sys.path.insert(0, '$MODULE_ROOT/lib')
from multi_character import find_character_file
from party import add_to_party
from pathlib import Path

campaign_dir = Path('$CAMPAIGN_DIR')
name = '$NAME'
try:
    find_character_file(campaign_dir, name)
except FileNotFoundError as e:
    print(f'[ERROR] {e}', file=sys.stderr)
    sys.exit(1)

# Use the id from the filename
from multi_character import load_character
char = load_character(campaign_dir, name)
char_id = char.get('id', name.lower().replace(' ', '-'))
add_to_party(campaign_dir, char_id)
print(f'[SUCCESS] Added {char.get(\"name\", name)} to party')
"
        ;;

    remove)
        if [ -z "${1:-}" ]; then
            echo "Usage: dm-party.sh remove <character-name>"
            exit 1
        fi
        NAME="$1"
        uv run python -c "
import sys
sys.path.insert(0, '$MODULE_ROOT/lib')
from party import remove_from_party
from pathlib import Path

campaign_dir = Path('$CAMPAIGN_DIR')
char_id = '$NAME'.lower().replace(' ', '-').replace(\"'\", '').replace('\"', '')
remove_from_party(campaign_dir, char_id)
print(f'[SUCCESS] Removed {char_id} from party')
"
        ;;

    migrate)
        uv run python -c "
import sys
sys.path.insert(0, '$MODULE_ROOT/lib')
from multi_character import migrate_to_multi, is_multi_character
from pathlib import Path

campaign_dir = Path('$CAMPAIGN_DIR')
if is_multi_character(campaign_dir) and not (campaign_dir / 'character.json').exists():
    print('[INFO] Campaign already uses multi-character format')
    sys.exit(0)
migrate_to_multi(campaign_dir)
print('[SUCCESS] Migrated to multi-character format')
"
        ;;

    *)
        echo "D&D Party Management"
        echo "Usage: dm-party.sh <action> [args]"
        echo ""
        echo "Actions:"
        echo "  list              Show all PCs in party with stats"
        echo "  add <name>        Add character to party roster"
        echo "  remove <name>     Remove character from party roster"
        echo "  migrate           Manually migrate to multi-character format"
        ;;
esac
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x .claude/modules/multi-character/tools/dm-party.sh
```

- [ ] **Step 3: Commit**

```bash
git add .claude/modules/multi-character/tools/dm-party.sh
git commit -m "feat(multi-character): add dm-party.sh CLI tool"
```

---

### Task 6: Patch InventoryManager for configurable character file

**Files:**
- Modify: `.claude/modules/inventory-system/lib/inventory_manager.py:18-21` (constructor)
- Modify: `.claude/modules/inventory-system/lib/inventory_manager.py:542-552` (CLI entry point)
- Test: `tests/test_modules/test_inventory_character_file.py`

- [ ] **Step 1: Write tests for the InventoryManager patch**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_modules/test_inventory_character_file.py -v`
Expected: FAIL — `TypeError: InventoryManager.__init__() got an unexpected keyword argument 'character_file'`

- [ ] **Step 3: Patch InventoryManager constructor**

In `.claude/modules/inventory-system/lib/inventory_manager.py`, change lines 18-20:

```python
# Before (line 18-20):
    def __init__(self, campaign_path: Path):
        self.campaign_path = campaign_path
        self.character_file = campaign_path / "character.json"

# After:
    def __init__(self, campaign_path: Path, character_file: str = "character.json"):
        self.campaign_path = campaign_path
        self.character_file = campaign_path / character_file
```

- [ ] **Step 4: Patch CLI entry point to accept --character-file**

In `.claude/modules/inventory-system/lib/inventory_manager.py`, add argparse argument after `args = parser.parse_args()` (around line 536). Change the CLI section:

Find the block at lines 498-552 and add `--character-file` as a top-level parser argument. Change:

```python
# Before (line 498):
    parser = argparse.ArgumentParser(description="Unified Inventory Manager")

# After:
    parser = argparse.ArgumentParser(description="Unified Inventory Manager")
    parser.add_argument('--character-file', default="character.json",
                        help='Character file path relative to campaign (default: character.json)')
```

And change the InventoryManager instantiation at line 552:

```python
# Before:
    manager = InventoryManager(campaign_path)

# After:
    manager = InventoryManager(campaign_path, character_file=args.character_file)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_modules/test_inventory_character_file.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run existing inventory tests to verify no regression**

Run: `uv run pytest tests/ -k inventory -v`
Expected: All existing inventory tests still PASS

- [ ] **Step 7: Commit**

```bash
git add .claude/modules/inventory-system/lib/inventory_manager.py tests/test_modules/test_inventory_character_file.py
git commit -m "feat(inventory): accept configurable character_file path (default: character.json)"
```

---

### Task 7: dm-inventory.sh middleware for multi-character

**Files:**
- Create: `.claude/modules/multi-character/middleware/dm-inventory.sh`

- [ ] **Step 1: Create the middleware script**

Create `.claude/modules/multi-character/middleware/dm-inventory.sh`:

```bash
#!/bin/bash
# multi-character middleware for dm-inventory.sh
# Resolves character name to file path and passes --character-file to InventoryManager.
# Falls through to CORE (exit 1) when campaign uses single-character format.

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "$MODULE_DIR/../../.." && pwd)"

source "$PROJECT_ROOT/tools/common.sh"

if [ "$1" = "--help" ]; then
    echo ""
    echo "  Multi-Character: inventory commands use --character-file to target specific characters"
    exit 1
fi

CAMPAIGN_DIR=$(get_campaign_dir)
if [ -z "$CAMPAIGN_DIR" ]; then
    exit 1
fi

# If not multi-character, fall through to CORE
if [ ! -d "$CAMPAIGN_DIR/characters" ]; then
    exit 1
fi

# Find the character argument in the command
# inventory_manager.py subcommands (update, show, loot) take 'character' as first positional arg
# We need to resolve that name to a --character-file path

# Extract the subcommand and character name
SUBCMD="${1:-}"
CHAR_NAME="${2:-}"

if [ -z "$CHAR_NAME" ]; then
    exit 1  # No character specified, let CORE handle
fi

# Resolve character name to file path
CHAR_FILE=$(uv run python -c "
import sys
sys.path.insert(0, '$MODULE_DIR/lib')
from multi_character import find_character_file
from pathlib import Path
try:
    path = find_character_file(Path('$CAMPAIGN_DIR'), '$CHAR_NAME')
    # Output relative path from campaign dir
    print(path.relative_to(Path('$CAMPAIGN_DIR')))
except FileNotFoundError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
" 2>&1)

rc=$?
if [ $rc -ne 0 ]; then
    echo "$CHAR_FILE" >&2  # Print the error message
    exit $rc
fi

# Forward to the inventory-system module's tool with --character-file injected
INVENTORY_MODULE="$PROJECT_ROOT/.claude/modules/inventory-system"
exec uv run python "$INVENTORY_MODULE/lib/inventory_manager.py" --character-file "$CHAR_FILE" "$@"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x .claude/modules/multi-character/middleware/dm-inventory.sh
```

- [ ] **Step 3: Commit**

```bash
git add .claude/modules/multi-character/middleware/dm-inventory.sh
git commit -m "feat(multi-character): add dm-inventory.sh middleware for character routing"
```

---

### Task 8: Integration tests

**Files:**
- Create: `tests/test_modules/test_multi_character_integration.py`

- [ ] **Step 1: Write integration tests**

```python
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
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest tests/test_modules/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_modules/test_multi_character_integration.py
git commit -m "test(multi-character): add integration tests for end-to-end flows"
```

---

### Task 9: Run full test suite and verify no regressions

**Files:** None (verification only)

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS, including existing `tests/test_discord/test_multi_character.py` and `tests/test_player_manager.py`

- [ ] **Step 2: Verify module is listed**

Run: `bash tools/dm-module.sh list`
Expected: `multi-character` appears in the module list

- [ ] **Step 3: Verify dm-party.sh help**

Run: `bash .claude/modules/multi-character/tools/dm-party.sh`
Expected: Shows usage help with list/add/remove/migrate actions

- [ ] **Step 4: Final commit if any fixups were needed**

If any test failures required fixes, commit those fixes:

```bash
git add -A
git commit -m "fix(multi-character): address test failures from full suite run"
```
