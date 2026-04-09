"""Maps Discord user IDs to campaign characters."""

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


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

    @staticmethod
    def _normalize(name: str) -> str:
        """Strip accents, punctuation, and spaces → lowercase alphanumeric.

        'Aldric Ironfeld' → 'aldricironfeld'
        'aldric-ironfeld' → 'aldricironfeld'
        'aldric_ironfeld' → 'aldricironfeld'
        'Áldrïc Ïrönféld' → 'aldricironfeld'
        """
        nfkd = unicodedata.normalize("NFKD", name)
        without_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]", "", without_accents.lower())

    def get_user_id_by_character(self, character_name: str) -> Optional[str]:
        """Reverse lookup: character name → Discord user ID.

        Best-effort matching in priority order:
        1. Exact (case-insensitive)
        2. Normalized (strips accents, punctuation, spaces — catches
           slug, underscore, concatenated, and accented forms)
        3. First name
        4. Last name
        5. Any individual word in a multi-part name
        """
        name = character_name.lower()
        norm = self._normalize(character_name)

        # 1. Exact (case-insensitive)
        for user_id, data in self._data["players"].items():
            if data["character"].lower() == name:
                return user_id

        # 2. Normalized (slugs, underscores, accents, concatenated)
        if norm:
            for user_id, data in self._data["players"].items():
                if self._normalize(data["character"]) == norm:
                    return user_id

        # 3. First name
        for user_id, data in self._data["players"].items():
            parts = data["character"].split()
            if len(parts) > 1 and self._normalize(parts[0]) == norm:
                return user_id

        # 4. Last name
        for user_id, data in self._data["players"].items():
            parts = data["character"].split()
            if len(parts) > 1 and self._normalize(parts[-1]) == norm:
                return user_id

        # 5. Any word in a 3+-part name (first/last already covered above)
        for user_id, data in self._data["players"].items():
            parts = data["character"].split()
            if len(parts) > 2 and norm in [self._normalize(w) for w in parts]:
                log.warning(
                    "Fuzzy word-match: %r resolved to %r (user %s) via partial name",
                    character_name, data["character"], user_id,
                )
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
