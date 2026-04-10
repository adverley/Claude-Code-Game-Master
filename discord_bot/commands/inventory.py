"""!inventory command -- show player's inventory via inventory-system module."""

import logging
import sys
from pathlib import Path
from discord_bot.commands import register

log = logging.getLogger("dm_bot.commands")

# Add inventory-system module to path
_MODULE_LIB = Path(__file__).resolve().parents[2] / ".claude" / "modules" / "inventory-system" / "lib"
sys.path.insert(0, str(_MODULE_LIB))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))

from inventory_manager import InventoryManager
from player_manager import PlayerManager


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

        # equipment can be a dict {weapons, armor, items} or a flat list
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

    # Stackable items
    if stackable:
        lines.append("\n**Stackable:**")
        for item, qty in sorted(stackable.items()):
            lines.append(f"  {item} — x{qty}")

    # Unique items
    if unique:
        lines.append("\n**Unique:**")
        for item in unique:
            lines.append(f"  • {item}")

    if not stackable and not unique:
        lines.append("\n*No items*")

    # Custom stats
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
    user_id = str(message.author.id)
    discord_name = message.author.display_name
    character = ctx.player_map.get_character(user_id)

    if character is None:
        log.info("!inventory from %s (unregistered, user_id=%s): rejected", discord_name, user_id)
        await message.channel.send("You're not registered. Use `!join <character_name>` first.")
        return

    log.info("!inventory from %s (%s)", discord_name, character)
    try:
        mgr = PlayerManager("world-state", require_active_campaign=True)
        campaign_path = mgr.campaign_dir

        # Resolve character file (supports both single character.json and legacy characters/ dir)
        char_path = mgr._get_character_path(character)
        char_file = str(char_path.relative_to(campaign_path))

        inv = InventoryManager(campaign_path, character_file=char_file)
        await message.channel.send(_format_inventory(inv.character))
    except (RuntimeError, FileNotFoundError) as e:
        log.error("!inventory error for %s (%s): %s", discord_name, character, e)
        await message.channel.send(f"Error: {e}")
