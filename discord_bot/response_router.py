"""Parse [PRIVATE:name]...[/PRIVATE] markers from Claude responses."""

import re
from dataclasses import dataclass, field

_PRIVATE_RE = re.compile(r'\[PRIVATE:([^\]]+)\](.*?)\[/PRIVATE\]', re.DOTALL)


@dataclass
class RoutedResponse:
    public: str
    whispers: list[tuple[str, str]] = field(default_factory=list)


def route_response(text: str) -> RoutedResponse:
    """Split a Claude response into public text and per-character whispers.

    Any [PRIVATE:character_name]...[/PRIVATE] blocks are removed from the
    public text and returned as (character_name, content) tuples in whispers.
    """
    whispers: list[tuple[str, str]] = []

    def _extract(match: re.Match) -> str:
        character = match.group(1).strip()
        # Strip leading/trailing whitespace — Claude often wraps content with newlines
        content = match.group(2).strip()
        whispers.append((character, content))
        return ""

    public = _PRIVATE_RE.sub(_extract, text).strip()
    return RoutedResponse(public=public, whispers=whispers)
