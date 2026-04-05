"""!status command -- show player's character status."""

import sys
from pathlib import Path
from discord_bot.commands import register

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from player_manager import PlayerManager


@register("status")
async def handle_status(message, args: str, ctx) -> None:
    """Handle !status -- show the requesting player's character summary."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)

    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return

    try:
        mgr = PlayerManager("world-state", require_active_campaign=True)
        summary = mgr.show_player(character)
        if summary:
            await message.channel.send(f"**{summary}**")
        else:
            await message.channel.send(f"Character '{character}' not found.")
    except RuntimeError as e:
        await message.channel.send(f"Error: {e}")
