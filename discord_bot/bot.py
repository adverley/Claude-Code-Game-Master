"""Discord bot entry point -- connects to Discord, tracks messages, dispatches commands."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from dataclasses import dataclass

import discord

from discord_bot.config import load_config
from discord_bot.message_buffer import MessageBuffer
from discord_bot.claude_bridge import ClaudeBridge
from discord_bot.player_map import PlayerMap
from discord_bot.commands import parse_command, COMMANDS
from discord_bot.private_chat import PrivateChatManager

PROJECT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

log = logging.getLogger("dm_bot")


def setup_logging(level: str = "INFO") -> None:
    """Configure logging. Level can be DEBUG, INFO, or WARNING."""
    numeric = getattr(logging, level.upper(), logging.INFO)

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(fmt)

    # Root logger for our code
    root = logging.getLogger("dm_bot")
    root.setLevel(numeric)
    root.addHandler(handler)

    # discord.py logs at INFO by default — suppress to WARNING unless DEBUG
    discord_level = logging.DEBUG if numeric == logging.DEBUG else logging.WARNING
    logging.getLogger("discord").setLevel(discord_level)


@dataclass
class BotContext:
    """Shared state passed to all command handlers."""
    config: dict
    message_buffer: MessageBuffer
    claude_bridge: ClaudeBridge
    player_map: PlayerMap
    channel_id: int
    client: discord.Client = None
    main_channel: discord.TextChannel = None
    private_chat_manager: PrivateChatManager = None


def on_message_handler(message, ctx: BotContext) -> str:
    """
    Synchronous message pre-processing. Returns:
    - "ignored" if the message should be skipped
    - "tracked" if it was a non-command message (added to buffer)
    - "command" if it's a command that needs async dispatch
    """
    if message.author.bot:
        log.debug("Ignoring bot message from %s", message.author.display_name)
        return "ignored"

    if message.channel.id != ctx.channel_id:
        log.debug("Ignoring message from wrong channel %s", message.channel.id)
        return "ignored"

    user_id = str(message.author.id)
    character = ctx.player_map.get_character(user_id) or "unregistered"
    discord_name = ctx.player_map.get_discord_name(user_id) or message.author.display_name

    parsed = parse_command(message.content)

    if parsed is not None:
        cmd_name, args = parsed
        log.info("Command from %s (%s): !%s %s", discord_name, character, cmd_name, args[:50] if args else "")
        log.debug("Full command args: %r", args)
        log.debug(
            "Buffer state: %d messages total, %d unsent",
            len(ctx.message_buffer.get_all()),
            len(ctx.message_buffer.get_delta()),
        )
        return "command"

    ctx.message_buffer.add(
        discord_name=discord_name,
        character_name=character,
        content=message.content,
    )
    log.debug("Tracked message from %s (%s): %r", discord_name, character, message.content)
    return "tracked"


async def dispatch_command(message, ctx: BotContext) -> None:
    """Parse and dispatch a command message."""
    parsed = parse_command(message.content)
    if parsed is None:
        return

    cmd_name, args = parsed
    handler = COMMANDS.get(cmd_name)
    if handler:
        log.debug("Dispatching !%s to handler %s", cmd_name, handler.__name__)
        await handler(message, args, ctx)
    else:
        log.warning("No handler found for command: %s", cmd_name)


def main():
    """Run the Discord bot."""
    parser = argparse.ArgumentParser(description="D&D DM Discord Bot")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--claude-debug", action="store_true", help="Pass --debug to Claude CLI subprocess")
    parser.add_argument("--model", default="", metavar="MODEL",
                        help="Claude model to use (e.g. sonnet, opus, haiku). Overrides config.json.")
    args = parser.parse_args()

    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(log_level)
    log.info("Starting DM bot (log level: %s)", log_level)

    config = load_config(CONFIG_PATH)
    log.info("Config loaded — campaign: %s, channel: %s", config["campaign"], config["channel_id"])

    # CLI --model overrides config.json
    model = args.model.strip() or config.get("model", "")
    if args.model.strip():
        log.info("Model override from CLI: %s", model)

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    campaign_dir = PROJECT_DIR / "world-state" / "campaigns" / config["campaign"]
    player_map_path = campaign_dir / "player-map.json"

    ctx = BotContext(
        config=config,
        message_buffer=MessageBuffer(max_size=config["message_buffer_size"]),
        claude_bridge=ClaudeBridge(project_dir=str(PROJECT_DIR), model=model, claude_debug=args.claude_debug),
        player_map=PlayerMap(player_map_path),
        channel_id=int(config["channel_id"]),
        client=client,
        private_chat_manager=PrivateChatManager(),
    )

    @client.event
    async def on_ready():
        model_label = model or "Claude Code default"
        log.info("Bot connected as %s", client.user)
        log.info("Listening in channel: %s", ctx.channel_id)
        log.info("Campaign: %s", config["campaign"])
        log.info("Model: %s", model_label)
        log.info("Buffer size: %s messages", config["message_buffer_size"])
        ctx.main_channel = client.get_channel(ctx.channel_id)
        if ctx.main_channel is None:
            log.warning("Could not find main channel %s — public notifications will be skipped", ctx.channel_id)

    @client.event
    async def on_message(message):
        if message.author.bot:
            return
        # DMs — no guild means direct message
        if message.guild is None:
            await ctx.private_chat_manager.handle_dm_message(message, ctx)
            return
        # Channel messages — existing logic
        result = on_message_handler(message, ctx)
        if result == "command":
            await dispatch_command(message, ctx)

    client.run(config["bot_token"])


if __name__ == "__main__":
    main()
