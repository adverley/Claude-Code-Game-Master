"""!roll command -- dice rolling via lib/dice.py."""

import sys
from pathlib import Path
from discord_bot.commands import register

# Add lib/ to path for dice import
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from dice import roll_detailed, DiceRoller

_roller = DiceRoller()


@register("roll")
async def handle_roll(message, args: str, ctx) -> None:
    """Handle !roll <notation> -- roll dice and post result."""
    if not args.strip():
        await message.channel.send("Usage: `!roll <dice>` (e.g. `!roll 1d20+5`, `!roll 3d6`)")
        return

    try:
        result = roll_detailed(args.strip())
        # Format without terminal color codes
        rolls_str = ", ".join(str(r) for r in result["rolls"])
        text = f"**{message.author.display_name}** rolls `{result['notation']}`: [{rolls_str}]"

        if result.get("modifier", 0) != 0:
            text += f" {result['modifier']:+d}"

        text += f" = **{result['total']}**"

        if result.get("natural_20"):
            text += " :crossed_swords: **CRITICAL HIT!**"
        elif result.get("natural_1"):
            text += " :skull: **CRITICAL MISS!**"

        await message.channel.send(text)
    except ValueError as e:
        await message.channel.send(f"Invalid dice notation: {e}")
