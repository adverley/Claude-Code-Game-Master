"""!join command -- register a Discord user to a character."""

import json
import logging
import sys
from pathlib import Path

from discord_bot.commands import register
from discord_bot.player_map import PlayerMap

log = logging.getLogger("dm_bot.commands")

# Add multi-character module to path
_MODULE_LIB = Path(__file__).resolve().parents[2] / ".claude" / "modules" / "multi-character" / "lib"
sys.path.insert(0, str(_MODULE_LIB))

from multi_character import find_character_file


def _character_status(campaign_dir, character_name: str) -> str:
    """Return 'dead', 'alive', or 'unknown' for a character."""
    if campaign_dir is None:
        return "unknown"
    try:
        char_path = find_character_file(campaign_dir, character_name)
        with open(char_path, "r", encoding="utf-8") as f:
            char_data = json.load(f)
        conditions = [c.lower() for c in char_data.get("conditions", [])]
        return "dead" if "dead" in conditions else "alive"
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return "unknown"


@register("join")
async def handle_join(message, args: str, ctx) -> None:
    """Handle !join <character_name> -- link Discord user to a character."""
    user_id = str(message.author.id)
    discord_name = message.author.display_name
    character_name = args.strip()

    if not character_name:
        log.info("!join from %s (user_id=%s): empty character name", discord_name, user_id)
        await message.channel.send("Usage: `!join <character_name>` (e.g. `!join thorin`)")
        return

    # Check if player already has a character
    existing = ctx.player_map.get_character(user_id)
    if existing is not None:
        # Same character (normalized) — allow idempotent re-join
        if PlayerMap._normalize(existing) != PlayerMap._normalize(character_name):
            # Different character — only allow if current character is dead
            status = _character_status(ctx.campaign_dir, existing)
            if status == "alive":
                log.info(
                    "!join from %s: REJECTED switch from %r to %r (character alive)",
                    discord_name, existing, character_name,
                )
                await message.channel.send(
                    f"You are already playing **{existing}**. "
                    f"You cannot switch characters unless your current character is dead."
                )
                return
            log.info(
                "!join from %s: allowing switch from %r (%s) to %r",
                discord_name, existing, status, character_name,
            )

    log.info("!join from %s (user_id=%s): registering as %r", discord_name, user_id, character_name)
    ctx.player_map.join(user_id, discord_name, character_name)

    await message.channel.send(f"**{discord_name}** is now playing **{character_name}**.")
