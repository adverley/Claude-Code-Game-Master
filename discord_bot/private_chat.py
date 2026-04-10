"""Manages multi-turn private DM conversations between players and the DM bot."""

import logging
from dataclasses import dataclass

log = logging.getLogger("dm_bot.private_chat")


@dataclass
class PrivateChat:
    character: str
    discord_name: str
    message_count: int = 0


class PrivateChatManager:
    def __init__(self):
        self._chats: dict[str, PrivateChat] = {}

    def is_active(self, user_id: str) -> bool:
        return user_id in self._chats

    def start_chat(self, user_id: str, *, character: str, discord_name: str) -> None:
        self._chats[user_id] = PrivateChat(character=character, discord_name=discord_name)
        log.info("Private chat started: %s (%s)", character, discord_name)

    def end_chat(self, user_id: str) -> None:
        chat = self._chats.pop(user_id, None)
        if chat:
            log.info("Private chat ended: %s (%s), %d messages exchanged",
                     chat.character, chat.discord_name, chat.message_count)

    def get_active_chats(self) -> dict[str, PrivateChat]:
        return dict(self._chats)

    def increment_message_count(self, user_id: str) -> None:
        if user_id in self._chats:
            self._chats[user_id].message_count += 1

    def build_prompt(self, *, character: str, discord_name: str,
                     message_content: str, is_first_message: bool) -> str:
        if is_first_message:
            return (
                f"[PRIVATE CONVERSATION with {character} ({discord_name})]\n"
                f"The player has initiated a private conversation with you.\n"
                f"Rules: No spoilers. No changes outside their character. Do not advance\n"
                f"the main plot. The player may propose a secret action — discuss it with\n"
                f"them privately. When the conversation ends, you will be asked to provide\n"
                f"a [PUBLIC] summary of any observable outcomes.\n\n"
                f"{character} says: {message_content}\n"
                f"[/PRIVATE CONVERSATION]"
            )
        return (
            f"[PRIVATE CONVERSATION with {character} continues]\n"
            f"{character} says: {message_content}\n"
            f"[/PRIVATE CONVERSATION]"
        )

    def build_done_prompt(self, *, character: str) -> str:
        return (
            f"[PRIVATE CONVERSATION with {character} — ENDING]\n"
            f"The player is ending the private conversation. Wrap up and include a\n"
            f"[PUBLIC]...[/PUBLIC] block with anything the other players would observe\n"
            f"or notice as a result. If nothing observable happened, the [PUBLIC] block\n"
            f"can be empty or omitted. Frame the [PUBLIC] content however makes\n"
            f"narrative sense — you decide whether to attribute it.\n"
            f"[/PRIVATE CONVERSATION]"
        )

    def build_process_notes(self) -> str:
        if not self._chats:
            return ""
        lines = []
        for chat in self._chats.values():
            lines.append(
                f"[NOTE: {chat.character} is currently in a private conversation with the DM. "
                f"You may hold back on advancing events that would directly involve them, "
                f"or narrate around their temporary absence.]"
            )
        return "\n".join(lines)

    def build_lite_prompt(self, *, character: str, message_content: str,
                          character_json: str, campaign_info: str) -> str:
        return (
            f"You are a D&D Dungeon Master assistant answering a quick question.\n\n"
            f"Campaign context:\n{campaign_info}\n\n"
            f"Character data:\n{character_json}\n\n"
            f"{character} asks: {message_content}\n\n"
            f"Answer mechanics, spells, inventory, and character questions only. "
            f"No plot advancement, no narrative."
        )
