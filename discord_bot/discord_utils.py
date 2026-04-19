"""Shared Discord send/dispatch helpers used by all commands."""

import logging

import discord

log = logging.getLogger("dm_bot.discord_utils")

DISCORD_MSG_LIMIT = 2000


async def send_chunked(target, text: str) -> None:
    """Send text to a Discord Messageable, splitting into <=2000 char chunks."""
    if not text:
        return
    for i in range(0, len(text), DISCORD_MSG_LIMIT):
        await target.send(text[i:i + DISCORD_MSG_LIMIT])


async def dispatch_whispers(whispers, player_map, client, channel) -> None:
    """Route [PRIVATE:name] blocks to each character's DM and post a 🤫 ack in channel.

    whispers: iterable of (character_name, whisper_text) tuples from route_response.
    """
    for char_name, whisper_text in whispers:
        user_id = player_map.get_user_id_by_character(char_name)
        if user_id is None:
            log.warning("No player mapped to character %r — skipping whisper", char_name)
            continue
        try:
            user = await client.fetch_user(int(user_id))
            await send_chunked(user, whisper_text)
            await channel.send(f"🤫 *The DM whispers to {char_name}...*")
        except discord.Forbidden:
            log.warning("Cannot DM character %r — DMs disabled", char_name)
            await channel.send(
                f"{char_name}, your DMs are closed — enable them to receive private messages."
            )


async def send_claude_reply(routed, *, channel, player_map, client) -> None:
    """Post routed.public to the channel and dispatch routed.whispers to DMs."""
    if routed.public:
        await send_chunked(channel, routed.public)
    await dispatch_whispers(routed.whispers, player_map, client, channel)
