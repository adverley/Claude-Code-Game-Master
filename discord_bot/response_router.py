"""Parse [PRIVATE:name]...[/PRIVATE], [PUBLIC]...[/PUBLIC], and [MENTAL MODEL]...[/MENTAL MODEL] markers from Claude responses."""

import re
from dataclasses import dataclass, field

_PRIVATE_RE = re.compile(r'\[PRIVATE:([^\]]+)\](.*?)\[/PRIVATE(?::[^\]]+)?\]', re.DOTALL)
_MENTAL_MODEL_RE = re.compile(r'\[MENTAL MODEL\](.*?)\[/MENTAL MODEL\]', re.DOTALL)
_PUBLIC_RE = re.compile(r'\[PUBLIC\](.*?)\[/PUBLIC\]', re.DOTALL)


@dataclass
class RoutedResponse:
    public: str
    whispers: list[tuple[str, str]] = field(default_factory=list)
    public_announcements: list[str] = field(default_factory=list)


def route_response(text: str) -> RoutedResponse:
    """Split a Claude response into public text, per-character whispers, and public announcements.

    Any [PRIVATE:character_name]...[/PRIVATE] blocks are removed from the
    public text and returned as (character_name, content) tuples in whispers.
    Any [PUBLIC]...[/PUBLIC] blocks are removed and returned in public_announcements.
    """
    whispers: list[tuple[str, str]] = []
    public_announcements: list[str] = []

    def _extract_whisper(match: re.Match) -> str:
        character = match.group(1).strip()
        content = match.group(2).strip()
        whispers.append((character, content))
        return ""

    def _extract_public(match: re.Match) -> str:
        content = match.group(1).strip()
        if content:
            # Extract any nested [PRIVATE:...] whispers from within the public block
            content = _PRIVATE_RE.sub(_extract_whisper, content).strip()
            if content:
                public_announcements.append(content)
        return ""

    text = _MENTAL_MODEL_RE.sub("", text)
    text = _PUBLIC_RE.sub(_extract_public, text)
    public = _PRIVATE_RE.sub(_extract_whisper, text).strip()
    return RoutedResponse(public=public, whispers=whispers, public_announcements=public_announcements)
