"""!help command -- show available commands."""

import logging
from discord_bot.commands import register

log = logging.getLogger("dm_bot.commands")

HELP_TEXT = """**D&D Discord Bot Commands:**

**Gameplay:**
`!dm <question>` -- Ask the DM a question (no plot advancement)
`!process <action>` -- Tell the DM what you do (advances the story)
`!private <question>` -- Ask the DM something privately (response via DM)
`!roll <dice>` -- Roll dice (e.g. `!roll 1d20+5`, `!roll 3d6`)

**Private Conversations:**
DM the bot directly to start a private conversation with the DM.
`!done` -- End the private conversation and publish observable results.

**Character:**
`!inventory` -- Show your character's equipment
`!status` -- Show your character summary (HP, level, gold)
`!join <character>` -- Link your Discord account to a character

**World:**
`!overview` -- Show current world state (locations, NPCs, quests)
`!characters` -- Show all characters and who has claimed them
`!summary` -- Get a brief recap of the story so far (+ your character's perspective)

**Session:**
`!session-start` -- Start a new DM session
`!session-end [summary]` -- End the current session

`!help` -- Show this message
"""


@register("help")
async def handle_help(message, args: str, ctx) -> None:
    """Handle !help -- list available commands."""
    discord_name = message.author.display_name
    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    log.info("!help from %s (%s)", discord_name, character)
    await message.channel.send(HELP_TEXT)
