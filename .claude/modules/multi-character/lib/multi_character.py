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
