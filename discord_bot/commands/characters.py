"""!characters command -- show character roster with availability."""

import json
import logging
from pathlib import Path

from discord_bot.commands import register

log = logging.getLogger("dm_bot.commands")

DISCORD_MSG_LIMIT = 2000
STAT_ORDER = ["str", "dex", "con", "int", "wis", "cha"]
STAT_LABELS = {"str": "STR", "dex": "DEX", "con": "CON", "int": "INT", "wis": "WIS", "cha": "CHA"}


@register("characters")
async def handle_characters(message, args: str, ctx) -> None:
    """Handle !characters -- show character roster and who has claimed each one."""
    discord_name = message.author.display_name
    log.info("!characters from %s", discord_name)

    campaign_dir = ctx.campaign_dir
    if campaign_dir is None or not campaign_dir.is_dir():
        await message.channel.send("No active campaign found. Ask the DM to start one.")
        return

    overview_path = campaign_dir / "campaign-overview.json"
    if not overview_path.exists():
        await message.channel.send("No campaign overview found.")
        return

    overview = json.loads(overview_path.read_text(encoding="utf-8"))
    party = overview.get("party", [])
    campaign_name = overview.get("campaign_name") or campaign_dir.name

    # Build map: character_name_lower → discord_name
    taken: dict[str, str] = {}
    for entry in ctx.player_map.get_all().values():
        char = entry.get("character", "").lower()
        if char:
            taken[char] = entry.get("discord_name", "?")

    lines = [f"**Character Roster — {campaign_name}**"]

    for char_id in party:
        char_path = campaign_dir / "characters" / f"{char_id}.json"
        if not char_path.exists():
            lines.append(f"\n**{char_id}**\n[data unavailable]")
            continue

        char = json.loads(char_path.read_text(encoding="utf-8"))
        name = char.get("name", char_id)
        race = char.get("race", "?")
        cls = char.get("class", "?")
        level = char.get("level", "?")
        hp = char.get("hp", {})
        hp_str = f"HP {hp.get('current', '?')}/{hp.get('max', '?')}"
        ac = char.get("ac", "?")
        stats = char.get("stats", {})
        stat_str = " ".join(
            f"{STAT_LABELS[s]} {stats[s]}" for s in STAT_ORDER if s in stats
        )
        traits = char.get("traits", "")

        owner = taken.get(char_id.lower()) or taken.get(name.lower())
        status_line = f"❌ TAKEN by {owner}" if owner else "✅ AVAILABLE"

        block = [
            f"\n**{name}** · {race} {cls} · Level {level}",
            status_line,
            f"{hp_str} · AC {ac}" + (f" · {stat_str}" if stat_str else ""),
        ]
        if traits:
            block.append(f'*"{traits}"*')
        lines.append("\n".join(block))

    output = "\n".join(lines)
    for i in range(0, len(output), DISCORD_MSG_LIMIT):
        await message.channel.send(output[i:i + DISCORD_MSG_LIMIT])
