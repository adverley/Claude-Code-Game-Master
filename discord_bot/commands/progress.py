"""!progress and !pace commands -- gated plot advancement with player confirmation."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from discord_bot.commands import register
from discord_bot.activity_tracker import Pace
from discord_bot.commands.dm import _advance_plot

log = logging.getLogger("dm_bot.commands")

_CONFIRM = "✅"
_DENY = "❌"
_ACTIVITY_WINDOW = timedelta(minutes=15)


@register("pace")
async def handle_pace(message, args: str, ctx) -> None:
    """Handle !pace [active|async] -- set or display the confirmation timeout mode."""
    mode = args.strip().lower()
    if mode == "active":
        ctx.pace = Pace.ACTIVE
        await message.channel.send("Pace set to **active** (2-minute confirmation timeout).")
    elif mode == "async":
        ctx.pace = Pace.ASYNC
        await message.channel.send("Pace set to **async** (60-minute confirmation timeout).")
    else:
        timeout_min = ctx.pace.value // 60
        await message.channel.send(
            f"Current pace: **{ctx.pace.name.lower()}** ({timeout_min}-minute timeout). "
            f"Use `!pace active` or `!pace async`."
        )


@register("progress")
async def handle_progress(message, args: str, ctx) -> None:
    """Handle !progress <text> -- advance plot after active players confirm with emoji."""
    dm_player = ctx.config.get("dm_player", "").strip()
    if dm_player and message.author.display_name != dm_player:
        log.info("!progress blocked for %s", message.author.display_name)
        await message.channel.send(f"Only **{dm_player}** can advance the story with `!progress`.")
        return

    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)
    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return
    if not ctx.claude_bridge.is_active:
        await message.channel.send("No active session. Use `!session-start` first.")
        return
    if ctx.progress_pending:
        await message.channel.send("A progress confirmation is already pending.")
        return

    cutoff = datetime.now(timezone.utc) - _ACTIVITY_WINDOW
    active_ids = ctx.activity_tracker.active_since(cutoff)
    registered = set(ctx.player_map.get_all().keys())
    candidates = (active_ids & registered) - {user_id}

    if not candidates:
        await _advance_plot(message, args, ctx)
        return

    mentions = " ".join(f"<@{uid}>" for uid in candidates)
    timeout_sec = ctx.pace.value
    timeout_min = timeout_sec // 60
    confirm_text = (
        f"**{message.author.display_name}** wants to advance the plot:\n"
        f"> {args or '(no description)'}\n\n"
        f"{mentions} — react {_CONFIRM} to confirm or {_DENY} to deny. "
        f"Timeout in {timeout_min} minute{'s' if timeout_min != 1 else ''}."
    )

    ctx.progress_pending = True
    try:
        confirm_msg = await message.channel.send(confirm_text)
        try:
            await confirm_msg.add_reaction(_CONFIRM)
            await confirm_msg.add_reaction(_DENY)
        except Exception:
            pass  # Missing reaction permissions; players can still react manually

        confirmed: set[str] = set()
        deadline = asyncio.get_running_loop().time() + timeout_sec

        def check(reaction, user):
            return (
                reaction.message.id == confirm_msg.id
                and str(user.id) in candidates
                and str(reaction.emoji) in (_CONFIRM, _DENY)
            )

        aborted = False
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                reaction, user = await asyncio.wait_for(
                    ctx.client.wait_for("reaction_add", check=check),
                    timeout=remaining,
                )
                uid = str(user.id)
                if str(reaction.emoji) == _DENY:
                    denier = ctx.player_map.get_discord_name(uid) or user.display_name
                    await message.channel.send(
                        f"{_DENY} **{denier}** denied the progress. Plot advancement aborted."
                    )
                    aborted = True
                    break
                confirmed.add(uid)
                if confirmed >= candidates:
                    break
            except asyncio.TimeoutError:
                break
    finally:
        ctx.progress_pending = False

    if not aborted:
        await _advance_plot(message, args, ctx)
