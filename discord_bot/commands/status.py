"""!status command -- show player's character status."""

import logging

from discord_bot.commands import register
from discord_bot.commands._helpers import resolve_player
from player_manager import PlayerManager

log = logging.getLogger("dm_bot.commands")


@register("status")
async def handle_status(message, args: str, ctx) -> None:
    """Handle !status -- show the requesting player's character summary."""
    player = await resolve_player(message, ctx)
    if player is None:
        return

    log.info("!status from %s (%s)", player.discord_name, player.character)
    try:
        mgr = PlayerManager("world-state", require_active_campaign=True)
        summary = mgr.show_player(player.character)
        if summary:
            await message.channel.send(f"**{summary}**")
        else:
            log.warning("!status from %s (%s): character not found", player.discord_name, player.character)
            await message.channel.send(f"Character '{player.character}' not found.")
    except RuntimeError as e:
        log.error("!status error for %s (%s): %s", player.discord_name, player.character, e)
        await message.channel.send(f"Error: {e}")
