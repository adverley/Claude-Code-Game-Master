"""!status command -- show player's character status."""

import logging
import sys
from pathlib import Path
from discord_bot.commands import register

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from player_manager import PlayerManager

log = logging.getLogger("dm_bot.commands")


@register("status")
async def handle_status(message, args: str, ctx) -> None:
    """Handle !status -- show the requesting player's character summary."""
    user_id = str(message.author.id)
    discord_name = message.author.display_name
    character = ctx.player_map.get_character(user_id)

    if character is None:
        log.info("!status from %s (unregistered, user_id=%s): rejected", discord_name, user_id)
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return

    log.info("!status from %s (%s)", discord_name, character)
    try:
        mgr = PlayerManager("world-state", require_active_campaign=True)
        summary = mgr.show_player(character)
        if summary:
            await message.channel.send(f"**{summary}**")
        else:
            log.warning("!status from %s (%s): character not found", discord_name, character)
            await message.channel.send(f"Character '{character}' not found.")
    except RuntimeError as e:
        log.error("!status error for %s (%s): %s", discord_name, character, e)
        await message.channel.send(f"Error: {e}")
