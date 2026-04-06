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
