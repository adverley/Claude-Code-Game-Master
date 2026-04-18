"""!session-start and !session-end commands."""

import asyncio
import logging
import shlex

from discord_bot.commands import register
from discord_bot.commands.confirmation_gate import _CONFIRM, _DENY, get_active_candidates, run_confirmation_gate
from discord_bot.commands.dm import DISCORD_MSG_LIMIT, _dispatch_whispers
from discord_bot.response_router import route_response

log = logging.getLogger("dm_bot.commands")

_SESSION_END_TIMEOUT = 300


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


async def _end_session(message, summary: str, ctx) -> None:
    """Run the session-end narrative and save. Called after gate passes."""
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
        log.error("_end_session error: %s", e)
        await message.channel.send(f"Error during session end: {e}")
    finally:
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


@register("session-end")
async def handle_session_end(message, args: str, ctx) -> None:
    """End the current DM session, with majority-vote confirmation gate."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"

    if not ctx.claude_bridge.is_active:
        log.info("!session-end from %s (%s): rejected, no active session", discord_name, character)
        await message.channel.send("No active session. Use `!session-start` first.")
        return

    if ctx.session_end_pending:
        log.info("!session-end from %s (%s): rejected, already pending", discord_name, character)
        await message.channel.send("A session-end confirmation is already pending.")
        return

    summary = args.strip() if args.strip() else "Session ended by player request."
    log.info("!session-end from %s (%s): requested, summary=%r", discord_name, character, summary[:80])

    candidates = get_active_candidates(ctx, user_id)

    if not candidates:
        await _end_session(message, summary, ctx)
        return

    mentions = " ".join(f"<@{uid}>" for uid in candidates)
    confirm_text = (
        f"**{discord_name}** wants to end the session.\n"
        f'Summary: "{summary}"\n\n'
        f"{mentions} — react {_CONFIRM} to confirm or {_DENY} to deny. "
        f"Timeout in 5 minutes."
    )

    ctx.session_end_pending = True
    try:
        confirmed = await run_confirmation_gate(
            message, ctx, confirm_text, candidates, _SESSION_END_TIMEOUT,
            require_all=False, action_name="session end",
        )
    finally:
        ctx.session_end_pending = False

    if confirmed:
        await _end_session(message, summary, ctx)
