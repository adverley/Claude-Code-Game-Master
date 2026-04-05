"""!inventory command -- show player's inventory via lib/player_manager.py."""

import sys
from pathlib import Path
from discord_bot.commands import register

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from player_manager import PlayerManager


@register("inventory")
async def handle_inventory(message, args: str, ctx) -> None:
    """Handle !inventory -- show the requesting player's equipment."""
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id)

    if character is None:
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return

    try:
        mgr = PlayerManager("world-state", require_active_campaign=True)
        char_data = mgr.get_player(character)
        if not char_data:
            await message.channel.send(f"Character '{character}' not found in campaign.")
            return

        equipment = char_data.get("equipment", [])
        name = char_data.get("name", character)

        if equipment:
            items = "\n".join(f"  {i}. {item}" for i, item in enumerate(equipment, 1))
            await message.channel.send(f"**{name}'s Inventory:**\n{items}")
        else:
            await message.channel.send(f"**{name}'s Inventory:** (empty)")
    except RuntimeError as e:
        await message.channel.send(f"Error: {e}")
