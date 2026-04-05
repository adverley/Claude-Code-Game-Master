"""!join command -- register a Discord user to a character."""

from discord_bot.commands import register


@register("join")
async def handle_join(message, args: str, ctx) -> None:
    """Handle !join <character_name> -- link Discord user to a character."""
    character_name = args.strip()
    if not character_name:
        await message.channel.send("Usage: `!join <character_name>` (e.g. `!join thorin`)")
        return

    user_id = str(message.author.id)
    discord_name = message.author.display_name
    ctx.player_map.join(user_id, discord_name, character_name)

    await message.channel.send(f"**{discord_name}** is now playing **{character_name}**.")
