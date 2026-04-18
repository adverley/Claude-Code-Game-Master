"""Manages multi-turn private DM conversations between players and the DM bot."""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from discord_bot.commands import parse_command, COMMANDS
from discord_bot.response_router import route_response

log = logging.getLogger("dm_bot.private_chat")

DISCORD_MSG_LIMIT = 2000


def _load_lite_context(project_dir: str, campaign: str, character: str) -> tuple[str, str]:
    """Load minimal character + campaign data for lite-mode queries."""
    base = Path(project_dir) / "world-state" / "campaigns" / campaign

    char_path = base / "characters" / f"{character.lower()}.json"
    if not char_path.exists():
        char_path = base / "character.json"
    character_json = ""
    if char_path.exists():
        character_json = char_path.read_text(encoding="utf-8")

    overview_path = base / "campaign-overview.json"
    campaign_info = ""
    if overview_path.exists():
        data = json.loads(overview_path.read_text(encoding="utf-8"))
        parts = [f"Campaign: {data.get('campaign_name', campaign)}"]
        if data.get("current_location"):
            parts.append(f"Current location: {data['current_location']}")
        campaign_info = "\n".join(parts)

    return character_json, campaign_info


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

    def build_done_prompt(self, *, character: str) -> str:
        return (
            f"[PRIVATE CONVERSATION with {character} — ENDING]\n"
            f"The player is ending the private conversation. Wrap up and include a\n"
            f"[PUBLIC]...[/PUBLIC] block with anything the other players would observe\n"
            f"or notice as a result.\n"
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

    async def handle_dm_message(self, message, ctx) -> None:
        """Main entry point for all Discord DMs from players."""
        user_id = str(message.author.id)
        content = message.content.strip()

        # Allow !characters before the join check — unregistered players can browse the roster
        parsed = parse_command(content)
        if parsed is not None and parsed[0] == "characters":
            await COMMANDS["characters"](message, parsed[1], ctx)
            return

        character = ctx.player_map.get_character(user_id)
        if character is None:
            log.info("DM from unregistered user %s (user_id=%s): rejected",
                     message.author.display_name, user_id)
            await message.channel.send(
                "I don't recognize you. Use `!join <character_name>` in the game channel first."
            )
            return

        discord_name = ctx.player_map.get_discord_name(user_id)

        if content.lower() == "!done":
            if not self.is_active(user_id):
                log.info("!done from %s (%s): no active private chat", discord_name, character)
                await message.channel.send("You don't have an active private conversation.")
                return
            log.info("!done from %s (%s): ending private conversation", discord_name, character)
            await self._handle_done(message, ctx, user_id, character, discord_name)
            return

        if parse_command(content) is not None:
            await message.channel.send(
                "Commands don't work in private conversations. "
                "Use the game channel for commands, or type `!done` to end this conversation."
            )
            return

        if not ctx.claude_bridge.is_active:
            log.info("DM (lite-mode) from %s (%s): %r", discord_name, character, content[:80])
            await self._handle_lite(message, ctx, user_id, character, discord_name, content)
            return

        is_first = not self.is_active(user_id)
        log.info("DM from %s (%s): %s message, %r",
                 discord_name, character, "first" if is_first else "follow-up", content[:80])
        if is_first:
            self.start_chat(user_id, character=character, discord_name=discord_name)
            if ctx.main_channel:
                await ctx.main_channel.send(f"*{character} pulls the DM aside for a private word...*")
            await message.channel.send(
                "*Private conversation started. Type `!done` when you're finished to wrap up and publish any results to the group.*"
            )

        prompt = self.build_prompt(
            character=character,
            discord_name=discord_name,
            message_content=content,
            is_first_message=is_first,
        )

        try:
            response = await ctx.claude_bridge.send(prompt)
            self.increment_message_count(user_id)
            routed = route_response(response)

            # Send public text + any whispers back to the player.
            # Claude often wraps DM responses in [PRIVATE:character] markers
            # even in a private conversation, so we need to capture both.
            reply = routed.public
            if reply:
                for i in range(0, len(reply), DISCORD_MSG_LIMIT):
                    await message.channel.send(reply[i:i + DISCORD_MSG_LIMIT])
            for _char_name, whisper_text in routed.whispers:
                for i in range(0, len(whisper_text), DISCORD_MSG_LIMIT):
                    await message.channel.send(whisper_text[i:i + DISCORD_MSG_LIMIT])
        except TimeoutError:
            await message.channel.send("The DM took too long to respond. Try sending your message again.")
        except RuntimeError as e:
            log.error("Claude error in private chat for %s (%s): %s", discord_name, character, e)
            await message.channel.send(f"DM error: {e}")

    async def _handle_done(self, message, ctx, user_id: str,
                           character: str, discord_name: str) -> None:
        """End a private conversation and post [PUBLIC] outcomes to channel."""
        prompt = self.build_done_prompt(character=character)
        try:
            response = await ctx.claude_bridge.send(prompt)
            routed = route_response(response)

            # Send public text + whispers back to the player (same reason as handle_dm_message)
            if routed.public:
                for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                    await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])
            for _char_name, whisper_text in routed.whispers:
                for i in range(0, len(whisper_text), DISCORD_MSG_LIMIT):
                    await message.channel.send(whisper_text[i:i + DISCORD_MSG_LIMIT])

            if ctx.main_channel:
                await ctx.main_channel.send(f"*{character} returns to the group.*")
                for announcement in routed.public_announcements:
                    for i in range(0, len(announcement), DISCORD_MSG_LIMIT):
                        await ctx.main_channel.send(announcement[i:i + DISCORD_MSG_LIMIT])
        except TimeoutError:
            await message.channel.send("The DM took too long to respond. Try `!done` again.")
            return
        except RuntimeError as e:
            log.error("Claude error on !done for %s (%s): %s", discord_name, character, e)
            await message.channel.send(f"DM error: {e}")
            return

        self.end_chat(user_id)

    async def _handle_lite(self, message, ctx, user_id: str,
                           character: str, discord_name: str, content: str) -> None:
        """Handle a DM when no session is active (lite mode)."""
        character_json, campaign_info = _load_lite_context(
            str(ctx.claude_bridge._project_dir),
            ctx.campaign_dir.name,
            character,
        )
        prompt = self.build_lite_prompt(
            character=character,
            message_content=content,
            character_json=character_json,
            campaign_info=campaign_info,
        )
        try:
            response = await ctx.claude_bridge.send_oneshot(prompt)
            await message.channel.send(
                "*(No active session — I can answer basic mechanics and character questions. I only remember this question so for follow-up questions, tell me what we already discussed...)*"
            )
            for i in range(0, len(response), DISCORD_MSG_LIMIT):
                await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
        except TimeoutError:
            await message.channel.send("The DM took too long to respond. Try again.")
        except RuntimeError as e:
            log.error("Claude lite-mode error for %s (%s): %s", discord_name, character, e)
            await message.channel.send(f"DM error: {e}")
