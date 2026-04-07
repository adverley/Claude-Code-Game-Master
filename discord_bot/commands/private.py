"""!private command -- ask the DM something privately."""

import logging
import discord
from discord_bot.commands import register

DISCORD_MSG_LIMIT = 2000
log = logging.getLogger("dm_bot.commands")


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
        await thinking_msg.delete()

        try:
            user = await ctx.client.fetch_user(int(user_id))
            for i in range(0, len(response), DISCORD_MSG_LIMIT):
                await user.send(response[i:i + DISCORD_MSG_LIMIT])
            await message.channel.send(f"🤫 *The DM whispers to {character}...*")
        except discord.Forbidden:
            log.warning("Cannot DM %s (%s) — DMs disabled", discord_name, character)
            await message.channel.send(
                f"{character}, your DMs are closed — enable them to receive private messages."
            )
    except TimeoutError:
        log.warning("Claude timed out for !private from %s", discord_name)
        await thinking_msg.delete()
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !private from %s: %s", discord_name, e)
        await thinking_msg.delete()
        await message.channel.send(f"DM error: {e}")
