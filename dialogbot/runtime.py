from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

import discord
from discord.ext import commands

from .expressions import eval_condition, eval_expr_text, exec_statement
from .model import (
    Button,
    ClearChannel,
    Dialogue,
    ExprStatement,
    If,
    Jump,
    Label,
    LabelRef,
    Menu,
    Run,
    ScriptGame,
    Statement,
    TimeLimit,
    Wait,
)
from .parser import resolve_label


LOGGER = logging.getLogger(__name__)


class RuntimeErrorWithContext(Exception):
    pass


class JumpSignal(Exception):
    def __init__(self, target: LabelRef) -> None:
        self.target = target


@dataclass
class EventContext:
    session: "GameSession"
    event_id: str
    namespace: str
    channel_name: str | None = None
    channel: discord.TextChannel | None = None
    last_click_user: discord.User | discord.Member | None = None

    async def get_var(self, name: str) -> Any:
        async with self.session.var_lock:
            if name not in self.session.variables:
                raise RuntimeErrorWithContext(f"unknown variable {name}")
            return self.session.variables[name]

    async def set_var(self, name: str, value: Any) -> None:
        async with self.session.var_lock:
            if name not in self.session.variables:
                raise RuntimeErrorWithContext(f"unknown variable {name}")
            self.session.variables[name] = value

    async def wait_for_input(self) -> str:
        if not self.channel:
            raise RuntimeErrorWithContext("input() used before entering a channel")

        def check(message: discord.Message) -> bool:
            return message.channel.id == self.channel.id and not message.author.bot

        message = await self.session.bot.wait_for("message", check=check)
        return message.content

    def username(self) -> str:
        if not self.last_click_user:
            return ""
        return self.last_click_user.display_name


class GameManager:
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.sessions: dict[int, GameSession] = {}

    async def start(self, guild: discord.Guild, game: ScriptGame) -> str:
        existing = self.sessions.get(guild.id)
        if existing and not existing.done:
            return "A game is already running in this server. Use `/stop` first."
        session = GameSession(self.bot, guild, game)
        self.sessions[guild.id] = session
        await session.start()
        return "Starting the game."

    async def stop(self, guild_id: int, reason: str) -> str:
        session = self.sessions.get(guild_id)
        if not session or session.done:
            return "No game is running in this server."
        await session.stop(reason)
        return "Stopped the game."

    def status(self, guild_id: int | None) -> str:
        if not guild_id or guild_id not in self.sessions or self.sessions[guild_id].done:
            return "No game is running."
        session = self.sessions[guild_id]
        active = ", ".join(sorted(session.active_channels)) or "none"
        return f"Game running. Active channels: {active}. Variables: {len(session.variables)}."


@dataclass
class GameSession:
    bot: commands.Bot
    guild: discord.Guild
    game: ScriptGame
    variables: dict[str, Any] = field(init=False)
    var_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_channels: dict[str, str] = field(default_factory=dict)
    channel_cache: dict[str, discord.TextChannel] = field(default_factory=dict)
    webhook_cache: dict[tuple[int, str], discord.Webhook] = field(default_factory=dict)
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    root_task: asyncio.Task[Any] | None = None
    timeout_task: asyncio.Task[Any] | None = None
    done: bool = False

    def __post_init__(self) -> None:
        self.variables = dict(self.game.defaults)
        self.category_name = os.getenv("GAME_CATEGORY_NAME", "Dialog Game")
        self.channel_topic = os.getenv("GAME_CHANNEL_TOPIC", "Dialog bot game channel")
        self.delay_per_char = float(os.getenv("DIALOG_DELAY_PER_CHAR", "0.03"))
        self.min_delay = float(os.getenv("DIALOG_MIN_DELAY", "1.5"))
        self.max_delay = float(os.getenv("DIALOG_MAX_DELAY", "6"))

    async def start(self) -> None:
        self.root_task = asyncio.create_task(self.run_root(), name=f"dialog-game-{self.guild.id}")
        self.tasks.add(self.root_task)
        self.root_task.add_done_callback(self.tasks.discard)

    async def stop(self, reason: str) -> None:
        self.done = True
        current = asyncio.current_task()
        if self.timeout_task:
            self.timeout_task.cancel()
        for task in list(self.tasks):
            if task is not current:
                task.cancel()
        for channel in set(self.channel_cache.values()):
            try:
                await channel.send(reason)
            except discord.HTTPException:
                LOGGER.exception("Failed to post stop notice in %s", channel)

    async def run_root(self) -> None:
        context = EventContext(self, secrets.token_hex(4), "main")
        try:
            await self.run_label(context, self.game.labels[("main", "setup")])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.fatal(context, exc)
        finally:
            self.done = True
            if self.timeout_task:
                self.timeout_task.cancel()

    async def fatal(self, context: EventContext, exc: Exception) -> None:
        error_id = secrets.token_hex(3)
        LOGGER.exception("Runtime error %s in guild %s", error_id, self.guild.id)
        message = f"The game hit a runtime error. Error id: `{error_id}`."
        channel = context.channel
        if channel:
            await channel.send(message)
        else:
            for cached in self.channel_cache.values():
                await cached.send(message)
        await self.stop("Game halted after a runtime error.")

    async def run_label(self, context: EventContext, label: Label) -> None:
        while True:
            context.namespace = label.namespace
            await self.bind_channel(context, label.channel)
            try:
                await self.execute_block(context, label.body)
                await self.release_channel(context)
                return
            except JumpSignal as jump:
                label = resolve_label(self.game, context.namespace, jump.target)

    async def bind_channel(self, context: EventContext, channel_name: str | None) -> None:
        if context.channel_name == channel_name:
            return
        await self.release_channel(context)
        if not channel_name:
            context.channel_name = None
            context.channel = None
            return
        async with self.active_lock:
            owner = self.active_channels.get(channel_name)
            if owner and owner != context.event_id:
                raise RuntimeErrorWithContext(f"channel {channel_name!r} is already running")
            self.active_channels[channel_name] = context.event_id
        context.channel_name = channel_name
        context.channel = await self.get_or_create_channel(channel_name)

    async def release_channel(self, context: EventContext) -> None:
        if not context.channel_name:
            return
        async with self.active_lock:
            if self.active_channels.get(context.channel_name) == context.event_id:
                del self.active_channels[context.channel_name]
        context.channel_name = None
        context.channel = None

    async def execute_block(self, context: EventContext, statements: list[Statement]) -> None:
        for statement in statements:
            await self.execute_statement(context, statement)

    async def execute_statement(self, context: EventContext, statement: Statement) -> None:
        if isinstance(statement, Dialogue):
            await self.send_dialogue(context, statement)
        elif isinstance(statement, Jump):
            raise JumpSignal(statement.target)
        elif isinstance(statement, Run):
            await self.run_children(context, statement)
        elif isinstance(statement, Menu):
            await self.show_menu(context, statement)
        elif isinstance(statement, Button):
            await self.show_button(context, statement)
        elif isinstance(statement, If):
            for branch in statement.branches:
                if branch.condition is None or await eval_condition(branch.condition, context):
                    await self.execute_block(context, branch.body)
                    break
        elif isinstance(statement, Wait):
            await asyncio.sleep(statement.seconds)
        elif isinstance(statement, ClearChannel):
            channel = await self.get_or_create_channel(statement.channel)
            await channel.purge(limit=1000)
        elif isinstance(statement, ExprStatement):
            await exec_statement(statement.expression, context)
        elif isinstance(statement, TimeLimit):
            self.set_time_limit(statement.seconds)
        else:
            raise RuntimeErrorWithContext(f"unsupported statement {type(statement).__name__}")

    async def run_children(self, context: EventContext, statement: Run) -> None:
        async def run_child(target: LabelRef) -> None:
            label = resolve_label(self.game, context.namespace, target)
            child = EventContext(self, secrets.token_hex(4), context.namespace)
            try:
                await self.run_label(child, label)
            finally:
                await self.release_channel(child)

        tasks = [asyncio.create_task(run_child(target)) for target in statement.targets]
        self.tasks.update(tasks)
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                self.tasks.discard(task)

    def set_time_limit(self, seconds: float) -> None:
        if self.timeout_task:
            self.timeout_task.cancel()
        self.timeout_task = asyncio.create_task(self.timeout_after(seconds))
        self.tasks.add(self.timeout_task)
        self.timeout_task.add_done_callback(self.tasks.discard)

    async def timeout_after(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        notice = "Time is up. The game has ended."
        channels = set(self.channel_cache.values())
        for channel in channels:
            await channel.send(notice)
        await self.stop(notice)

    async def send_dialogue(self, context: EventContext, statement: Dialogue) -> None:
        if not context.channel:
            raise RuntimeErrorWithContext("dialogue emitted before entering a channel")
        text = await self.interpolate(statement.text, context)
        delay = min(self.max_delay, max(self.min_delay, len(text) * self.delay_per_char))
        async with context.channel.typing():
            await asyncio.sleep(delay)
        if not statement.character:
            await context.channel.send(f"*{text}*")
            return
        character = self.game.characters[statement.character]
        webhook = await self.get_character_webhook(context.channel, character.key)
        await webhook.send(text, username=character.name, wait=True)

    async def interpolate(self, text: str, context: EventContext) -> str:
        async def replace_expr(match: re.Match[str]) -> str:
            return str(await eval_expr_text(match.group(1), context))

        result = ""
        last = 0
        for match in re.finditer(r"\$\(([^)]+)\)", text):
            result += text[last : match.start()]
            result += await replace_expr(match)
            last = match.end()
        result += text[last:]

        pieces: list[str] = []
        last = 0
        for match in re.finditer(r"\$([A-Za-z_]\w*)", result):
            pieces.append(result[last : match.start()])
            pieces.append(str(await context.get_var(match.group(1))))
            last = match.end()
        pieces.append(result[last:])
        return "".join(pieces)

    async def show_button(self, context: EventContext, statement: Button) -> None:
        if not context.channel:
            raise RuntimeErrorWithContext("button used before entering a channel")
        view = SingleButtonView(statement.text)
        message = await context.channel.send(view=view)
        await view.wait()
        if view.user is None:
            return
        context.last_click_user = view.user
        await disable_view(message, view)
        await self.execute_block(context, statement.body)

    async def show_menu(self, context: EventContext, statement: Menu) -> None:
        if not context.channel:
            raise RuntimeErrorWithContext("menu used before entering a channel")
        visible = []
        for index, option in enumerate(statement.options):
            if option.condition is None or await eval_condition(option.condition, context):
                visible.append((index, option))
        if not visible:
            raise RuntimeErrorWithContext("menu has no visible options")
        view = MenuView([(index, option.text) for index, option in visible])
        message = await context.channel.send(view=view)
        try:
            while True:
                index, user = await view.next_click()
                context.last_click_user = user
                option = statement.options[index]
                try:
                    await self.execute_block(context, option.body)
                except JumpSignal:
                    await disable_view(message, view)
                    raise
        finally:
            view.stop()

    async def get_or_create_channel(self, display_name: str) -> discord.TextChannel:
        cached = self.channel_cache.get(display_name)
        if cached:
            return cached

        category = discord.utils.get(self.guild.categories, name=self.category_name)
        if not category:
            category = await self.guild.create_category(self.category_name)

        topic = f"{self.channel_topic}: {display_name}"
        for channel in category.text_channels:
            if channel.topic == topic:
                self.channel_cache[display_name] = channel
                return channel

        channel = await self.guild.create_text_channel(
            slugify(display_name),
            category=category,
            topic=topic,
        )
        self.channel_cache[display_name] = channel
        return channel

    async def get_character_webhook(self, channel: discord.TextChannel, character_key: str) -> discord.Webhook:
        cache_key = (channel.id, character_key)
        if cache_key in self.webhook_cache:
            return self.webhook_cache[cache_key]
        character = self.game.characters[character_key]
        name = f"dialog-{character.key}"
        hooks = await channel.webhooks()
        for hook in hooks:
            if hook.name == name:
                self.webhook_cache[cache_key] = hook
                return hook
        avatar = character.image_path.read_bytes() if character.image_path else None
        webhook = await channel.create_webhook(name=name, avatar=avatar, reason="Dialog bot character")
        self.webhook_cache[cache_key] = webhook
        return webhook


class SingleButtonView(discord.ui.View):
    def __init__(self, label: str) -> None:
        super().__init__(timeout=None)
        self.user: discord.User | discord.Member | None = None
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
        button.callback = self.clicked
        self.add_item(button)

    async def clicked(self, interaction: discord.Interaction) -> None:
        self.user = interaction.user
        await interaction.response.defer()
        self.stop()


class MenuView(discord.ui.View):
    def __init__(self, options: list[tuple[int, str]]) -> None:
        super().__init__(timeout=None)
        self.queue: asyncio.Queue[tuple[int, discord.User | discord.Member]] = asyncio.Queue()
        self.clicked_users: set[int] = set()
        for index, text in options:
            button = discord.ui.Button(label=text, style=discord.ButtonStyle.secondary)
            button.callback = self.make_callback(index)
            self.add_item(button)

    def make_callback(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id in self.clicked_users:
                await interaction.response.send_message("You already chose an option for this menu.", ephemeral=True)
                return
            self.clicked_users.add(interaction.user.id)
            await interaction.response.defer()
            await self.queue.put((index, interaction.user))

        return callback

    async def next_click(self) -> tuple[int, discord.User | discord.Member]:
        return await self.queue.get()


async def disable_view(message: discord.Message, view: discord.ui.View) -> None:
    for item in view.children:
        if hasattr(item, "disabled"):
            item.disabled = True
    try:
        await message.edit(view=view)
    except discord.HTTPException:
        LOGGER.exception("Failed to disable view")
    view.stop()


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return slug or "dialog"
