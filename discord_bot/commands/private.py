"""!private command -- ask the DM something privately."""

import logging

import discord

from discord_bot.commands import register
from discord_bot.commands._helpers import resolve_player, with_thinking
from discord_bot.discord_utils import send_chunked
from discord_bot.response_router import route_response

log = logging.getLogger("dm_bot.commands")


@register("done")
async def handle_done(message, args: str, ctx) -> None:
    """Reject !done in public channel — it only works in DM private conversations."""
    await message.channel.send("`!done` only works in a private DM conversation with the bot.")


@register("private")
async def handle_private(message, args: str, ctx) -> None:
    """Handle !private <text> -- Claude responds privately via DM."""
    player = await resolve_player(message, ctx, require_session=True)
    if player is None:
        return

    payload = ctx.message_buffer.format_for_claude(
        [],
        active_player=player.discord_name,
        active_character=player.character,
        command_text=args,
        advance_plot=False,
    )
    payload += "\n\n[This is a private message to this player only — do not address the full party.]"

    log.info("!private from %s (%s): %r", player.discord_name, player.character, args[:50] if args else "")

    async with with_thinking(message.channel):
        try:
            response = await ctx.claude_bridge.send(payload)
            routed = route_response(response)

            try:
                user = await ctx.client.fetch_user(int(player.user_id))
                await send_chunked(user, routed.public)
                for _char_name, whisper_text in routed.whispers:
                    await send_chunked(user, whisper_text)
                await message.channel.send(f"🤫 *The DM whispers to {player.character}...*")
            except discord.Forbidden:
                log.warning("Cannot DM %s (%s) — DMs disabled", player.discord_name, player.character)
                await message.channel.send(
                    f"{player.character}, your DMs are closed — enable them to receive private messages."
                )
        except TimeoutError:
            log.warning("Claude timed out for !private from %s", player.discord_name)
            await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
        except RuntimeError as e:
            log.error("Claude error for !private from %s: %s", player.discord_name, e)
            await message.channel.send(f"DM error: {e}")
