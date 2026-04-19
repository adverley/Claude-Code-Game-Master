"""Multi-turn private DM conversations between players and the DM bot.

`PrivateChatManager` owns the state (which users have an open private chat) and
orchestrates the DM message flow. Prompt strings live in `private_chat_prompts`
(pure functions); chunked sends + whisper dispatch live in `discord_utils`.
"""

import logging
from dataclasses import dataclass

from discord_bot.commands import parse_command, COMMANDS
from discord_bot.discord_utils import send_chunked, send_claude_reply
from discord_bot.private_chat_prompts import (
    build_done_prompt,
    build_lite_prompt,
    build_process_notes,
    build_prompt,
    load_lite_context,
)
from discord_bot.response_router import route_response

log = logging.getLogger("dm_bot.private_chat")


# Legacy module-level alias: tests patch `discord_bot.private_chat._load_lite_context`.
_load_lite_context = load_lite_context


@dataclass
class PrivateChat:
    character: str
    discord_name: str
    message_count: int = 0


class PrivateChatManager:
    """State + orchestration for private player DM conversations."""

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

    # --- Prompt-builder passthroughs (preserved for tests; logic lives in private_chat_prompts) ---

    def build_prompt(self, *, character: str, discord_name: str,
                     message_content: str, is_first_message: bool) -> str:
        return build_prompt(
            character=character, discord_name=discord_name,
            message_content=message_content, is_first_message=is_first_message,
        )

    def build_done_prompt(self, *, character: str) -> str:
        return build_done_prompt(character=character)

    def build_lite_prompt(self, *, character: str, message_content: str,
                          character_json: str, campaign_info: str) -> str:
        return build_lite_prompt(
            character=character, message_content=message_content,
            character_json=character_json, campaign_info=campaign_info,
        )

    def build_process_notes(self) -> str:
        return build_process_notes(self._chats.values())

    # --- Orchestration ---

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

        prompt = build_prompt(
            character=character,
            discord_name=discord_name,
            message_content=content,
            is_first_message=is_first,
        )

        try:
            response = await ctx.claude_bridge.send(prompt)
            self.increment_message_count(user_id)
            routed = route_response(response)

            # Send public text back to the player's DM. Claude often wraps
            # DM responses in [PRIVATE:character] markers even in a private
            # conversation, so dispatch whispers to the same DM channel too.
            if routed.public:
                await send_chunked(message.channel, routed.public)
            for _char_name, whisper_text in routed.whispers:
                await send_chunked(message.channel, whisper_text)
        except TimeoutError:
            await message.channel.send("The DM took too long to respond. Try sending your message again.")
        except RuntimeError as e:
            log.error("Claude error in private chat for %s (%s): %s", discord_name, character, e)
            await message.channel.send(f"DM error: {e}")

    async def _handle_done(self, message, ctx, user_id: str,
                           character: str, discord_name: str) -> None:
        """End a private conversation and post [PUBLIC] outcomes to channel."""
        prompt = build_done_prompt(character=character)
        try:
            response = await ctx.claude_bridge.send(prompt)
            routed = route_response(response)

            if routed.public:
                await send_chunked(message.channel, routed.public)
            for _char_name, whisper_text in routed.whispers:
                await send_chunked(message.channel, whisper_text)

            if ctx.main_channel:
                await ctx.main_channel.send(f"*{character} returns to the group.*")
                for announcement in routed.public_announcements:
                    await send_chunked(ctx.main_channel, announcement)
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
        character_json, campaign_info = _load_lite_context(ctx.campaign_dir, character)
        prompt = build_lite_prompt(
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
            await send_chunked(message.channel, response)
        except TimeoutError:
            await message.channel.send("The DM took too long to respond. Try again.")
        except RuntimeError as e:
            log.error("Claude lite-mode error for %s (%s): %s", discord_name, character, e)
            await message.channel.send(f"DM error: {e}")
