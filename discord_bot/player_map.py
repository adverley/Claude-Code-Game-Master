"""Maps Discord user IDs to campaign characters."""

import json
from pathlib import Path
from typing import Optional


class PlayerMap:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._data: dict = {"players": {}}
        if self._path.exists():
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get_character(self, user_id: str) -> Optional[str]:
        """Get character name for a Discord user ID."""
        player = self._data["players"].get(user_id)
        return player["character"] if player else None

    def get_discord_name(self, user_id: str) -> Optional[str]:
        """Get Discord display name for a user ID."""
        player = self._data["players"].get(user_id)
        return player["discord_name"] if player else None

    def get_user_id_by_character(self, character_name: str) -> Optional[str]:
        """Reverse lookup: character name → Discord user ID. Case-insensitive."""
        name = character_name.lower()
        for user_id, data in self._data["players"].items():
            if data["character"].lower() == name:
                return user_id
        return None

    def join(self, user_id: str, discord_name: str, character: str) -> None:
        """Register or update a player's character mapping."""
        self._data["players"][user_id] = {
            "discord_name": discord_name,
            "character": character,
        }
        self._save()

    def get_all(self) -> dict[str, dict]:
        """Return all player mappings."""
        return dict(self._data["players"])
