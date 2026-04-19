"""!roll command -- dice rolling via lib/dice.py."""

import logging

from dice import roll_detailed

from discord_bot.commands import register

log = logging.getLogger("dm_bot.commands")


@register("roll")
async def handle_roll(message, args: str, ctx) -> None:
    """Handle !roll <notation> -- roll dice and post result."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"

    if not args.strip():
        log.info("!roll from %s (%s): empty notation", discord_name, character)
        await message.channel.send("Usage: `!roll <dice>` (e.g. `!roll 1d20+5`, `!roll 3d6`)")
        return

    log.info("!roll from %s (%s): %s", discord_name, character, args.strip())
    try:
        result = roll_detailed(args.strip())
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
        log.warning("!roll invalid notation from %s (%s): %s", discord_name, character, e)
        await message.channel.send(f"Invalid dice notation: {e}")
