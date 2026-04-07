"""!overview command -- show campaign world state summary."""

import subprocess
import sys
from pathlib import Path
from discord_bot.commands import register

import logging
log = logging.getLogger("dm_bot.commands")

PROJECT_DIR = Path(__file__).resolve().parents[2]
DISCORD_MSG_LIMIT = 2000


@register("overview")
async def handle_overview(message, args: str, ctx) -> None:
    """Handle !overview -- show current world state summary."""
    try:
        result = subprocess.run(
            ["bash", "tools/dm-overview.sh", "summary"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_DIR),
        )
        output = result.stdout.strip()
        if result.returncode != 0 or not output:
            error = result.stderr.strip() or "No overview available."
            log.warning("dm-overview.sh failed: %s", error)
            await message.channel.send(f"Could not load overview: {error}")
            return

        log.info("Overview fetched (%d chars)", len(output))
        # Wrap in code block and split if needed
        wrapped = f"```\n{output}\n```"
        for i in range(0, len(wrapped), DISCORD_MSG_LIMIT):
            await message.channel.send(wrapped[i:i + DISCORD_MSG_LIMIT])
    except Exception as e:
        log.error("Overview error: %s", e)
        await message.channel.send(f"Error fetching overview: {e}")
