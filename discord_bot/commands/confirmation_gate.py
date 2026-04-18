"""Shared emoji-reaction confirmation gate used by gated Discord commands."""

import asyncio
from datetime import datetime, timedelta, timezone

_CONFIRM = "✅"
_DENY = "❌"
_ACTIVITY_WINDOW = timedelta(minutes=15)


def get_active_candidates(ctx, exclude_user_id: str) -> set[str]:
    """Return registered players active in the last 15 min, excluding the requester."""
    cutoff = datetime.now(timezone.utc) - _ACTIVITY_WINDOW
    active_ids = ctx.activity_tracker.active_since(cutoff)
    registered = set(ctx.player_map.get_all().keys())
    return (active_ids & registered) - {exclude_user_id}


async def run_confirmation_gate(
    message,
    ctx,
    confirm_text: str,
    candidates: set[str],
    timeout_sec: float,
    *,
    require_all: bool = True,
    action_name: str = "action",
) -> bool:
    """Post confirm_text, collect ✅/❌ emoji votes from candidates.

    Returns True to proceed, False to abort.
    - require_all=True: all candidates must confirm; timeout = non-responders lose vote (proceed).
    - require_all=False: strict majority (>50%) required; timeout without majority = abort.
    """
    confirm_msg = await message.channel.send(confirm_text)
    try:
        await confirm_msg.add_reaction(_CONFIRM)
        await confirm_msg.add_reaction(_DENY)
    except Exception:
        pass  # Missing permissions; players can still react manually

    confirmed: set[str] = set()
    deadline = asyncio.get_running_loop().time() + timeout_sec

    def is_valid_vote(reaction, user):
        return (
            reaction.message.id == confirm_msg.id
            and str(user.id) in candidates
            and str(reaction.emoji) in (_CONFIRM, _DENY)
        )

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            reaction, user = await asyncio.wait_for(
                ctx.client.wait_for("reaction_add", check=is_valid_vote),
                timeout=remaining,
            )
            uid = str(user.id)
            if str(reaction.emoji) == _DENY:
                denier = ctx.player_map.get_discord_name(uid) or user.display_name
                await message.channel.send(
                    f"{_DENY} **{denier}** denied the {action_name}. Aborted."
                )
                return False
            confirmed.add(uid)
            passed = confirmed >= candidates if require_all else len(confirmed) > len(candidates) / 2
            if passed:
                return True
        except asyncio.TimeoutError:
            break

    # Timed out: evaluate whether the threshold was met
    if require_all:
        return True  # Non-responders lose their vote; proceed
    if len(confirmed) <= len(candidates) / 2:
        await message.channel.send(
            f"Timed out without majority confirmation. {action_name.capitalize()} aborted."
        )
        return False
    return True
