from __future__ import annotations

import argparse
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from dialogbot.discord_io import DiscordDialogIO
from dialogbot.parser import ScriptLoadError, load_game
from dialogbot.runtime import GameManager


load_dotenv()
LOGGER = logging.getLogger(__name__)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


class DialogBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.manager = GameManager()

    async def setup_hook(self) -> None:
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logging.info("Synced guild commands for %s", guild_id)
        else:
            await self.tree.sync()
            logging.info("Synced global commands")


bot = DialogBot()


def format_script_load_error(exc: ScriptLoadError, max_chars: int = 1500) -> str:
    text = str(exc)
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n... truncated; run `python3 check.py` for full output."
    return f"Script load failed. Full errors were logged.\n```text\n{text}\n```"


def guild_only(interaction: discord.Interaction) -> bool:
    return interaction.guild is not None


@bot.tree.command(name="start", description="Start the dialog game in this server.")
@app_commands.check(guild_only)
async def start(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        game = load_game("game")
    except ScriptLoadError as exc:
        LOGGER.error("Script load failed during /start:\n%s", exc)
        await interaction.followup.send(format_script_load_error(exc))
        return

    assert interaction.guild is not None
    io = DiscordDialogIO(bot, interaction.guild)
    result = await bot.manager.start(interaction.guild.id, io, game)
    await interaction.followup.send(result)


@bot.tree.command(name="stop", description="Stop the active dialog game in this server.")
@app_commands.check(guild_only)
async def stop(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    assert interaction.guild is not None
    result = await bot.manager.stop(interaction.guild.id, "Stopped by slash command.")
    await interaction.followup.send(result)


@bot.tree.command(name="reload", description="Reload scripts and report parser errors.")
@app_commands.check(guild_only)
async def reload_scripts(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        game = load_game("game")
    except ScriptLoadError as exc:
        LOGGER.error("Script load failed during /reload:\n%s", exc)
        await interaction.followup.send(format_script_load_error(exc), ephemeral=True)
        return
    await interaction.followup.send(
        f"Loaded {len(game.labels)} labels, {len(game.characters)} characters, "
        f"and {len(game.defaults)} defaults.",
        ephemeral=True,
    )


@bot.tree.command(name="status", description="Show the active dialog game status.")
@app_commands.check(guild_only)
async def status(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(bot.manager.status(interaction.guild_id), ephemeral=True)


@start.error
@stop.error
@reload_scripts.error
@status.error
async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    message = "This command can only be used in a server." if isinstance(error, app_commands.CheckFailure) else str(error)
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Discord dialog bot.")
    parser.add_argument(
        "--dialog-min-delay",
        "--min-delay",
        type=float,
        help="Override DIALOG_MIN_DELAY for this bot process.",
    )
    parser.add_argument(
        "--dialog-max-delay",
        "--max-delay",
        type=float,
        help="Override DIALOG_MAX_DELAY for this bot process.",
    )
    parser.add_argument(
        "--message-timestamps",
        action="store_true",
        help="Append local send timestamps to Discord messages for timing debugging.",
    )
    args = parser.parse_args()
    if args.dialog_min_delay is not None:
        os.environ["DIALOG_MIN_DELAY"] = str(args.dialog_min_delay)
    if args.dialog_max_delay is not None:
        os.environ["DIALOG_MAX_DELAY"] = str(args.dialog_max_delay)
    if args.message_timestamps:
        os.environ["DIALOG_MESSAGE_TIMESTAMPS"] = "1"

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is required")
    bot.run(token)
