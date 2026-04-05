"""!dm command -- sends narrative prompt to Claude via the bridge."""

from discord_bot.commands import register

DISCORD_MSG_LIMIT = 2000


@register("dm")
async def handle_dm(message, args: str, ctx) -> None:
    """Handle !dm <text> -- pipe message context + command to Claude."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)

    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return

    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    discord_name = ctx.player_map.get_discord_name(user_id)
    delta = ctx.message_buffer.get_delta()
    formatted = ctx.message_buffer.format_for_claude(
        delta,
        active_player=discord_name,
        active_character=character,
        command_text=args,
    )

    # Send "thinking" indicator
    thinking_msg = await message.channel.send("*The DM is thinking...*")

    try:
        response = await ctx.claude_bridge.send(formatted)
        await thinking_msg.delete()
        # Split long responses to respect Discord's 2000 char limit
        for i in range(0, len(response), DISCORD_MSG_LIMIT):
            await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
    except TimeoutError:
        await thinking_msg.delete()
        await message.channel.send("The DM took too long to respond. Try again or `!session-start` to restart.")
    except RuntimeError as e:
        await thinking_msg.delete()
        await message.channel.send(f"DM error: {e}")
    finally:
        ctx.message_buffer.mark_sent()
