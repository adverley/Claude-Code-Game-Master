"""!help command -- show available commands."""

from discord_bot.commands import register

HELP_TEXT = """**D&D Discord Bot Commands:**

**Gameplay:**
`!dm <question>` -- Ask the DM a question (no plot advancement)
`!process <action>` -- Tell the DM what you do (advances the story)
`!roll <dice>` -- Roll dice (e.g. `!roll 1d20+5`, `!roll 3d6`)

**Character:**
`!inventory` -- Show your character's equipment
`!status` -- Show your character summary (HP, level, gold)
`!join <character>` -- Link your Discord account to a character

**World:**
`!overview` -- Show current world state (locations, NPCs, quests)

**Session:**
`!session-start` -- Start a new DM session
`!session-end [summary]` -- End the current session

`!help` -- Show this message
"""


@register("help")
async def handle_help(message, args: str, ctx) -> None:
    """Handle !help -- list available commands."""
    await message.channel.send(HELP_TEXT)
