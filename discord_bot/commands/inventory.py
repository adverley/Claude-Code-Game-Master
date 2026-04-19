"""!inventory command -- show player's inventory via inventory-system module."""

import logging

from discord_bot.commands import register
from discord_bot.commands._helpers import resolve_player
from inventory_manager import InventoryManager
from player_manager import PlayerManager

log = logging.getLogger("dm_bot.commands")


def _format_inventory(char: dict) -> str:
    """Format character inventory for Discord display."""
    name = char.get("name", "Character")
    gold = char.get("gold", 0)
    hp = char.get("hp", {})
    hp_str = f"{hp.get('current', 0)}/{hp.get('max', 0)}" if hp else "?"
    xp = char.get("xp", {})
    xp_str = f"{xp.get('current', 0)}/{xp.get('next_level', 0)}" if isinstance(xp, dict) else str(xp)
    level = char.get("level", 1)

    lines = [
        f"**{name}'s Inventory**",
        f"Gold: {gold}  |  HP: {hp_str}  |  XP: {xp_str}  |  Level: {level}",
    ]

    inventory = char.get("inventory", {})
    stackable = inventory.get("stackable", {})
    unique = inventory.get("unique", [])

    # Fall back to old equipment format if no inventory key
    if not inventory and "equipment" in char:
        equipment = char["equipment"]
        if isinstance(equipment, dict):
            has_items = False
            for category, items in equipment.items():
                if items:
                    has_items = True
                    lines.append(f"\n**{category.capitalize()}:**")
                    lines.extend(f"  • {item}" for item in items)
            if not has_items:
                lines.append("\n*No items*")
        elif isinstance(equipment, list) and equipment:
            lines.append("\n**Equipment:**")
            lines.extend(f"  {i}. {item}" for i, item in enumerate(equipment, 1))
        else:
            lines.append("\n*No items*")
        return "\n".join(lines)

    if stackable:
        lines.append("\n**Stackable:**")
        for item, qty in sorted(stackable.items()):
            lines.append(f"  {item} — x{qty}")

    if unique:
        lines.append("\n**Unique:**")
        for item in unique:
            lines.append(f"  • {item}")

    if not stackable and not unique:
        lines.append("\n*No items*")

    custom_stats = char.get("custom_stats", {})
    if custom_stats:
        lines.append("\n**Stats:**")
        for stat_name, stat_data in custom_stats.items():
            current = stat_data.get("current", 0)
            max_val = stat_data.get("max", 100)
            lines.append(f"  {stat_name.capitalize()}: {current}/{max_val}")

    return "\n".join(lines)


@register("inventory")
async def handle_inventory(message, args: str, ctx) -> None:
    """Handle !inventory -- show the requesting player's inventory."""
    player = await resolve_player(message, ctx)
    if player is None:
        return

    log.info("!inventory from %s (%s)", player.discord_name, player.character)
    try:
        mgr = PlayerManager("world-state", require_active_campaign=True)
        campaign_path = mgr.campaign_dir
        char_path = mgr._get_character_path(player.character)
        char_file = str(char_path.relative_to(campaign_path))

        inv = InventoryManager(campaign_path, character_file=char_file)
        await message.channel.send(_format_inventory(inv.character))
    except (RuntimeError, FileNotFoundError) as e:
        log.error("!inventory error for %s (%s): %s", player.discord_name, player.character, e)
        await message.channel.send(f"Error: {e}")
