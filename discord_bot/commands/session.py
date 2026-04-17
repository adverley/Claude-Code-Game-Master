"""!session-start and !session-end commands."""

import asyncio
import logging
import shlex

from discord_bot.commands import register
from discord_bot.commands.dm import _dispatch_whispers
from discord_bot.response_router import route_response

log = logging.getLogger("dm_bot.commands")

DISCORD_MSG_LIMIT = 2000


@register("session-start")
async def handle_session_start(message, args: str, ctx) -> None:
    """Start a new Claude DM session."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"

    if ctx.claude_bridge.is_active:
        log.info("!session-start from %s (%s): rejected, session already active", discord_name, character)
        await message.channel.send("A session is already active. Use `!session-end` first.")
        return

    campaign = ctx.campaign_dir.name
    log.info("!session-start from %s (%s): starting campaign %r", discord_name, character, campaign)
    await message.channel.send(f"*Starting DM session for **{campaign}**...*")

    ctx.claude_bridge.start_session(campaign)
    players = ctx.player_map.get_all()

    try:
        response = await ctx.claude_bridge.send_init(campaign, players)
        routed = route_response(response)

        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])

        await _dispatch_whispers(routed.whispers, ctx.player_map, ctx.client, message.channel)
        log.info("!session-start from %s (%s): session started successfully", discord_name, character)
    except (TimeoutError, RuntimeError) as e:
        log.error("!session-start from %s (%s): failed: %s", discord_name, character, e)
        ctx.claude_bridge.end_session()
        await message.channel.send(f"Failed to start session: {e}")


@register("session-end")
async def handle_session_end(message, args: str, ctx) -> None:
    """End the current DM session."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"

    if not ctx.claude_bridge.is_active:
        log.info("!session-end from %s (%s): rejected, no active session", discord_name, character)
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    summary = args.strip() if args.strip() else "Session ended by player request."
    log.info("!session-end from %s (%s): ending session, summary=%r", discord_name, character, summary[:80])
    await message.channel.send("*Ending session...*")

    try:
        prompt = (
            f"The session is ending. Please wrap up the narrative with a closing scene. Summary: {summary}\n\n"
            f"Keep all DM-internal information (pending consequences, upcoming events, future plot) "
            f"inside [MENTAL MODEL]...[/MENTAL MODEL] tags — it will be filtered before reaching players."
        )
        response = await ctx.claude_bridge.send(prompt)
        routed = route_response(response)
        if routed.public:
            for i in range(0, len(routed.public), DISCORD_MSG_LIMIT):
                await message.channel.send(routed.public[i:i + DISCORD_MSG_LIMIT])
        await _dispatch_whispers(routed.whispers, ctx.player_map, ctx.client, message.channel)
    except (TimeoutError, RuntimeError) as e:
        log.error("!session-end from %s (%s): error: %s", discord_name, character, e)
        await message.channel.send(f"Error during session end: {e}")
    finally:
        # Always save the session, regardless of whether Claude responded
        try:
            project_dir = str(ctx.claude_bridge._project_dir)
            safe_summary = shlex.quote(summary)
            proc = await asyncio.create_subprocess_shell(
                f"bash tools/dm-session.sh end {safe_summary}",
                cwd=project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30.0)
        except Exception:
            pass  # Save failure is non-fatal; session still ends
        ctx.claude_bridge.end_session()
        await message.channel.send("*Session ended.*")
