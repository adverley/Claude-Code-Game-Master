"""!dm and !process commands -- send prompts to Claude via the bridge."""

import logging
from discord_bot.commands import register

DISCORD_MSG_LIMIT = 2000
log = logging.getLogger("dm_bot.commands")


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


async def _send_and_reply(message, payload: str, mode: str, discord_name: str):
    """Send payload to Claude and post the response to Discord."""
    thinking_msg = await message.channel.send("*The DM is thinking...*")
    log.info("Sent thinking indicator; waiting for Claude [mode=%s, player=%s]", mode, discord_name)

    try:
        response = await message.ctx.claude_bridge.send(payload) if False else await _bridge_send(message, payload)
        await thinking_msg.delete()
        for i in range(0, len(response), DISCORD_MSG_LIMIT):
            await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
        return True
    except TimeoutError:
        log.warning("Claude timed out for !%s from %s", mode, discord_name)
        await thinking_msg.delete()
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
        return False
    except RuntimeError as e:
        log.error("Claude error for !%s from %s: %s", mode, discord_name, e)
        await thinking_msg.delete()
        await message.channel.send(f"DM error: {e}")
        return False


async def _bridge_send(message, payload):
    """Placeholder -- replaced at call site."""
    raise NotImplementedError


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
        await thinking_msg.delete()
        for i in range(0, len(response), DISCORD_MSG_LIMIT):
            await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
    except TimeoutError:
        log.warning("Claude timed out for !dm from %s", discord_name)
        await thinking_msg.delete()
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !dm from %s: %s", discord_name, e)
        await thinking_msg.delete()
        await message.channel.send(f"DM error: {e}")


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
        await thinking_msg.delete()
        for i in range(0, len(response), DISCORD_MSG_LIMIT):
            await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
    except TimeoutError:
        log.warning("Claude timed out for !process from %s", discord_name)
        await thinking_msg.delete()
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        log.error("Claude error for !process from %s: %s", discord_name, e)
        await thinking_msg.delete()
        await message.channel.send(f"DM error: {e}")
    finally:
        ctx.message_buffer.mark_sent()
        log.debug("Message buffer marked sent")
