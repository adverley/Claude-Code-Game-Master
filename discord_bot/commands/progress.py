"""!progress and !pace commands -- gated plot advancement with player confirmation."""

import logging
from discord_bot.commands import register
from discord_bot.activity_tracker import Pace

log = logging.getLogger("dm_bot.commands")


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
