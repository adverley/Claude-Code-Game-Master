"""!dm and !process commands -- send prompts to Claude via the bridge."""

import logging
import discord
from discord_bot.commands import register
from discord_bot.response_router import route_response

DISCORD_MSG_LIMIT = 2000
log = logging.getLogger("dm_bot.commands")


async def _dispatch_whispers(whispers, player_map, client, channel) -> None:
    """Send whisper DMs to players and post channel acknowledgements."""
    for char_name, whisper_text in whispers:
        user_id = player_map.get_user_id_by_character(char_name)
        if user_id is None:
            log.warning("No player mapped to character %r — skipping whisper", char_name)
            continue
        try:
            user = await client.fetch_user(int(user_id))
            for i in range(0, len(whisper_text), DISCORD_MSG_LIMIT):
                await user.send(whisper_text[i:i + DISCORD_MSG_LIMIT])
            await channel.send(f"🤫 *The DM whispers to {char_name}...*")
        except discord.Forbidden:
            log.warning("Cannot DM character %r — DMs disabled", char_name)
            await channel.send(
                f"{char_name}, your DMs are closed — enable them to receive private messages."
            )


async def _resolve_player(message, ctx):
    """Return (discord_name, character) or send an error and return None."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)
    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return None
    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return None
    discord_name = ctx.player_map.get_discord_name(user_id)
    return discord_name, character


@register("dm")
async def handle_dm(message, args: str, ctx) -> None:
    """Handle !dm <text> -- ask the DM a question without advancing the plot."""
    result = await _resolve_player(message, ctx)
    if result is None:
        return
    discord_name, character = result

    log.info("!dm from %s (%s): %r", discord_name, character, args[:50] if args else "")

    payload = ctx.message_buffer.format_for_claude(
        [],
        active_player=discord_name,
        active_character=character,
        command_text=args,
        advance_plot=False,
    )
    log.debug("Payload built (%d chars), no buffer included", len(payload))

    thinking_msg = await message.channel.send("*The DM is thinking...*")
    try:
        response = await ctx.claude_bridge.send(payload)
        routed = route_response(response)

        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

        await _dispatch_whispers(routed.whispers, ctx.player_map, ctx.client, message.channel)
    except TimeoutError:
        log.warning("Claude timed out for !dm from %s", discord_name)
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !dm from %s: %s", discord_name, e)
        await message.channel.send(f"DM error: {e}")
    finally:
        await thinking_msg.delete()


@register("process")
async def handle_process(message, args: str, ctx) -> None:
    """Handle !process <text> -- advance the plot based on player actions."""
    dm_player = ctx.config.get("dm_player", "").strip()
    if dm_player and message.author.display_name != dm_player:
        log.info("!process blocked for %s (only %s may advance the story)", message.author.display_name, dm_player)
        await message.channel.send(f"Only **{dm_player}** can advance the story with `!process`.")
        return

    result = await _resolve_player(message, ctx)
    if result is None:
        return
    discord_name, character = result

    delta = ctx.message_buffer.get_delta()
    log.info("!process from %s (%s): %d buffered messages, args=%r", discord_name, character, len(delta), args[:50] if args else "")

    payload = ctx.message_buffer.format_for_claude(
        delta,
        active_player=discord_name,
        active_character=character,
        command_text=args,
        advance_plot=True,
    )
    log.debug("Payload built (%d chars)", len(payload))

    thinking_msg = await message.channel.send("*The DM is thinking...*")
    try:
        response = await ctx.claude_bridge.send(payload)
        routed = route_response(response)

        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

        await _dispatch_whispers(routed.whispers, ctx.player_map, ctx.client, message.channel)
    except TimeoutError:
        log.warning("Claude timed out for !process from %s", discord_name)
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !process from %s: %s", discord_name, e)
        await message.channel.send(f"DM error: {e}")
    finally:
        await thinking_msg.delete()
        ctx.message_buffer.mark_sent()
        log.debug("Message buffer marked sent")
