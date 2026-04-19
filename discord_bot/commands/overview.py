"""!overview command -- show campaign world state summary."""

import logging
import subprocess

from discord_bot.commands import register
from discord_bot.discord_utils import send_chunked

log = logging.getLogger("dm_bot.commands")


@register("overview")
async def handle_overview(message, args: str, ctx) -> None:
    """Handle !overview -- show current world state summary."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    log.info("!overview from %s (%s)", discord_name, character)

    try:
        result = subprocess.run(
            ["bash", "tools/dm-overview.sh", "summary"],
            capture_output=True,
            text=True,
            cwd=str(ctx.claude_bridge.project_dir),
        )
        output = result.stdout.strip()
        if result.returncode != 0 or not output:
            error = result.stderr.strip() or "No overview available."
            log.warning("!overview from %s (%s): dm-overview.sh failed: %s", discord_name, character, error)
            await message.channel.send(f"Could not load overview: {error}")
            return

        log.info("!overview from %s (%s): fetched (%d chars)", discord_name, character, len(output))
        await send_chunked(message.channel, f"```\n{output}\n```")
    except Exception as e:
        log.error("!overview from %s (%s): error: %s", discord_name, character, e)
        await message.channel.send(f"Error fetching overview: {e}")
