"""!session-start and !session-end commands."""

from discord_bot.commands import register

DISCORD_MSG_LIMIT = 2000


@register("session-start")
async def handle_session_start(message, args: str, ctx) -> None:
    """Start a new Claude DM session."""
    if ctx.claude_bridge.is_active:
        await message.channel.send("A session is already active. Use `!session-end` first.")
        return

    campaign = ctx.config["campaign"]
    await message.channel.send(f"*Starting DM session for **{campaign}**...*")

    ctx.claude_bridge.start_session(campaign)
    players = ctx.player_map.get_all()

    try:
        response = await ctx.claude_bridge.send_init(campaign, players)
        for i in range(0, len(response), DISCORD_MSG_LIMIT):
            await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
    except (TimeoutError, RuntimeError) as e:
        ctx.claude_bridge.end_session()
        await message.channel.send(f"Failed to start session: {e}")


@register("session-end")
async def handle_session_end(message, args: str, ctx) -> None:
    """End the current DM session."""
    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    summary = args.strip() if args.strip() else "Session ended by player request."
    await message.channel.send("*Ending session...*")

    try:
        prompt = f"The session is ending. Summary: {summary}\nPlease wrap up the narrative and run: bash tools/dm-session.sh end \"{summary}\""
        response = await ctx.claude_bridge.send(prompt)
        for i in range(0, len(response), DISCORD_MSG_LIMIT):
            await message.channel.send(response[i:i + DISCORD_MSG_LIMIT])
    except (TimeoutError, RuntimeError) as e:
        await message.channel.send(f"Error during session end: {e}")
    finally:
        ctx.claude_bridge.end_session()
        await message.channel.send("*Session ended.*")
