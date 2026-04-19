"""Pure prompt builders and context loader for private DM conversations.

All functions here are side-effect free (except `load_lite_context`, which reads
campaign files from disk). They are extracted so `PrivateChatManager` can focus
on state and orchestration.
"""

import json
from pathlib import Path


def build_prompt(*, character: str, discord_name: str, message_content: str,
                 is_first_message: bool) -> str:
    """Build the prompt for an active-session private DM (first or follow-up)."""
    if is_first_message:
        return (
            f"[PRIVATE CONVERSATION with {character} ({discord_name})]\n"
            f"The player has initiated a private conversation with you.\n"
            f"Rules: No spoilers. No changes outside their character. Do not advance\n"
            f"the main plot. The player may propose a secret action — discuss it with\n"
            f"them privately. Keep this conversation SHORT!\n "
            f"{character} says: {message_content}\n"
            f"[/PRIVATE CONVERSATION]"
        )
    return (
        f"[PRIVATE CONVERSATION with {character} continues but try to wrap it up.!]\n"
        f"do NOT advance the story plot or introduce new events. Focus on resolving the player's proposed action or question.\n"
        f"{character} says: {message_content}\n"
        f"[/PRIVATE CONVERSATION]"
    )


def build_done_prompt(*, character: str) -> str:
    """Build the wrap-up prompt when a player ends their private conversation."""
    return (
        f"[PRIVATE CONVERSATION with {character} — ENDING]\n"
        f"The player is ending the private conversation. Wrap up and include a\n"
        f"[PUBLIC]...[/PUBLIC] block with anything the other players would observe\n"
        f"or notice as a result.\n"
        f"[/PRIVATE CONVERSATION]"
    )


def build_lite_prompt(*, character: str, message_content: str,
                      character_json: str, campaign_info: str) -> str:
    """Build the prompt for a lite-mode (no session) question from a player."""
    return (
        f"You are a D&D Dungeon Master assistant answering a quick question.\n\n"
        f"Campaign context:\n{campaign_info}\n\n"
        f"Character data:\n{character_json}\n\n"
        f"{character} asks: {message_content}\n\n"
        f"Answer mechanics, spells, inventory, and character questions only. "
        f"No plot advancement, no narrative."
    )


def build_process_notes(chats) -> str:
    """Build the process-time notes injected into the main plot prompt.

    chats: iterable of PrivateChat objects (only `.character` is read).
    """
    lines = []
    for chat in chats:
        lines.append(
            f"[NOTE: {chat.character} is currently in a private conversation with the DM. "
            f"You may hold back on advancing events that would directly involve them, "
            f"or narrate around their temporary absence.]"
        )
    return "\n".join(lines)


def load_lite_context(campaign_dir: Path, character: str) -> tuple[str, str]:
    """Load minimal character + campaign data for lite-mode queries.

    Returns (character_json_text, campaign_info_lines). Missing files yield empty strings.
    """
    campaign_dir = Path(campaign_dir)

    char_path = campaign_dir / "characters" / f"{character.lower()}.json"
    if not char_path.exists():
        char_path = campaign_dir / "character.json"
    character_json = char_path.read_text(encoding="utf-8") if char_path.exists() else ""

    overview_path = campaign_dir / "campaign-overview.json"
    campaign_info = ""
    if overview_path.exists():
        data = json.loads(overview_path.read_text(encoding="utf-8"))
        parts = [f"Campaign: {data.get('campaign_name', campaign_dir.name)}"]
        if data.get("current_location"):
            parts.append(f"Current location: {data['current_location']}")
        campaign_info = "\n".join(parts)

    return character_json, campaign_info
