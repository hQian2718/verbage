from __future__ import annotations

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


def guild_only(interaction: discord.Interaction) -> bool:
    return interaction.guild is not None


@bot.tree.command(name="start", description="Start the dialog game in this server.")
@app_commands.check(guild_only)
async def start(interaction: discord.Interaction) -> None:
    await interaction.response.defer(thinking=True)
    try:
        game = load_game("game")
    except ScriptLoadError as exc:
        await interaction.followup.send(f"Script load failed:\n```text\n{exc}\n```")
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
        await interaction.followup.send(f"Script load failed:\n```text\n{exc}\n```", ephemeral=True)
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
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit("DISCORD_TOKEN is required")
    bot.run(token)
