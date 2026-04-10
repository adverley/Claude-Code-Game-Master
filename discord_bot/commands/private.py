"""!private command -- ask the DM something privately."""

import logging
import discord
from discord_bot.commands import register
from discord_bot.response_router import route_response

DISCORD_MSG_LIMIT = 2000
log = logging.getLogger("dm_bot.commands")


@register("done")
async def handle_done(message, args: str, ctx) -> None:
    """Reject !done in public channel — it only works in DM private conversations."""
    await message.channel.send("`!done` only works in a private DM conversation with the bot.")


@register("private")
async def handle_private(message, args: str, ctx) -> None:
    """Handle !private <text> -- Claude responds privately via DM."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)
    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return
    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return
    discord_name = ctx.player_map.get_discord_name(user_id)

    payload = ctx.message_buffer.format_for_claude(
        [],
        active_player=discord_name,
        active_character=character,
        command_text=args,
        advance_plot=False,
    )
    payload += "\n\n[This is a private message to this player only — do not address the full party.]"

    log.info("!private from %s (%s): %r", discord_name, character, args[:50] if args else "")

    thinking_msg = await message.channel.send("*The DM is thinking...*")
    try:
        response = await ctx.claude_bridge.send(payload)
        routed = route_response(response)

        try:
            user = await ctx.client.fetch_user(int(user_id))
            if routed.public:
                for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                    await user.send(routed.public[i:i + DISCORD_MSG_LIMIT])
            for _char_name, whisper_text in routed.whispers:
                for i in range(0, len(whisper_text), DISCORD_MSG_LIMIT):
                    await user.send(whisper_text[i:i + DISCORD_MSG_LIMIT])
            await message.channel.send(f"🤫 *The DM whispers to {character}...*")
        except discord.Forbidden:
            log.warning("Cannot DM %s (%s) — DMs disabled", discord_name, character)
            await message.channel.send(
                f"{character}, your DMs are closed — enable them to receive private messages."
            )
    except TimeoutError:
        log.warning("Claude timed out for !private from %s", discord_name)
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !private from %s: %s", discord_name, e)
        await message.channel.send(f"DM error: {e}")
    finally:
        await thinking_msg.delete()
