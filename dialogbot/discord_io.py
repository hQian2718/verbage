# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TypeVar

import discord
from discord.ext import commands

from .io import MenuChoice, MenuHandle, TextInput, UserAction
from .model import Character


LOGGER = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class DiscordMenuHandle:
    channel_name: str
    message: discord.Message
    view: "MenuView"


class DiscordDialogIO:
    def __init__(self, bot: commands.Bot, guild: discord.Guild) -> None:
        self.bot = bot
        self.guild = guild
        self.category_name = os.getenv("GAME_CATEGORY_NAME", "Dialog Game")
        self.channel_topic_base = os.getenv("GAME_CHANNEL_TOPIC", "Dialog bot game channel")
        self.session_id: str | None = None
        self.channel_cache: dict[str, discord.TextChannel] = {}
        self.webhook_cache: dict[tuple[int, str], discord.Webhook] = {}
        self.webhook_fallback_channels: set[int] = set()
        self.retry_attempts = max(1, int(os.getenv("DISCORD_RETRY_ATTEMPTS", "4")))
        self.retry_base_delay = float(os.getenv("DISCORD_RETRY_BASE_DELAY", "1"))
        self.message_timestamps_enabled = parse_bool_env("DIALOG_MESSAGE_TIMESTAMPS")

    async def prepare_session(self, session_id: str) -> None:
        self.session_id = session_id
        self.channel_cache.clear()
        self.webhook_cache.clear()
        self.webhook_fallback_channels.clear()

    async def ensure_channel(self, channel_name: str) -> None:
        await self.get_or_create_channel(channel_name)

    async def typing_pause(self, channel_name: str, seconds: float) -> None:
        channel = await self.get_or_create_channel(channel_name)
        async with channel.typing():
            await asyncio.sleep(seconds)

    async def send_notice(self, channel_name: str, text: str) -> None:
        channel = await self.get_or_create_channel(channel_name)
        await self.retry_discord_call(f"send notice to #{channel.name}", lambda: channel.send(self.with_timestamp(text)))

    async def send_narration(self, channel_name: str, text: str) -> None:
        channel = await self.get_or_create_channel(channel_name)
        await self.retry_discord_call(
            f"send narration to #{channel.name}",
            lambda: channel.send(self.with_timestamp(f"*{text}*")),
        )

    async def send_character_dialogue(self, channel_name: str, character: Character, text: str) -> None:
        channel = await self.get_or_create_channel(channel_name)
        try:
            webhook = await self.get_character_webhook(channel, character)
        except (discord.Forbidden, discord.NotFound):
            await self.warn_webhook_fallback(channel)
            await self.send_character_fallback(channel, character, text)
            return
        try:
            await self.retry_discord_call(
                f"send webhook dialogue to #{channel.name}",
                lambda: webhook.send(self.with_timestamp(text), username=character.name, wait=True),
            )
        except discord.NotFound:
            self.webhook_cache.pop((channel.id, character.key), None)
            await self.send_character_fallback(channel, character, text)
        except discord.Forbidden:
            await self.warn_webhook_fallback(channel)
            await self.send_character_fallback(channel, character, text)
        except discord.HTTPException:
            LOGGER.exception("Webhook send failed in #%s (%s)", channel.name, channel.id)
            await self.send_character_fallback(channel, character, text)

    async def send_image(self, channel_name: str, source: str, image_path: Path | None, caption: str | None = None) -> None:
        channel = await self.get_or_create_channel(channel_name)
        if image_path:
            content = self.with_timestamp(caption) if caption else self.timestamp_only()
            await self.retry_discord_call(
                f"send image {image_path.name!r} to #{channel.name}",
                lambda: channel.send(content=content, file=discord.File(image_path)),
            )
            return

        content = f"{caption}\n{source}" if caption else source
        await self.retry_discord_call(
            f"send image URL to #{channel.name}",
            lambda: channel.send(self.with_timestamp(content)),
        )

    async def send_channel_link(self, channel_name: str, label: str, target_channel_name: str) -> None:
        channel = await self.get_or_create_channel(channel_name)
        target = await self.get_or_create_channel(target_channel_name)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=label, url=target.jump_url))
        await self.retry_discord_call(
            f"send channel link to #{channel.name}",
            lambda: channel.send(self.timestamp_only(), view=view),
        )

    async def wait_for_input(self, channel_name: str, prompt: str | None = None) -> TextInput:
        channel = await self.get_or_create_channel(channel_name)
        if prompt:
            await self.retry_discord_call(
                f"send input prompt to #{channel.name}",
                lambda: channel.send(self.with_timestamp(prompt)),
            )

        def check(message: discord.Message) -> bool:
            return message.channel.id == channel.id and not message.author.bot

        message = await self.bot.wait_for("message", check=check)
        return TextInput(message.content, UserAction(str(message.author.id), message.author.display_name))

    async def wait_for_button(
        self,
        channel_name: str,
        label: str,
        timeout_seconds: float | None = None,
    ) -> UserAction | None:
        channel = await self.get_or_create_channel(channel_name)
        view = SingleButtonView(label, timeout_seconds)
        message = await self.retry_discord_call(
            f"send button to #{channel.name}",
            lambda: channel.send(self.timestamp_only(), view=view),
        )
        await view.wait()
        await disable_view(message, view)
        if view.user is None:
            return None
        return UserAction(str(view.user.id), view.user.display_name)

    async def open_menu(self, channel_name: str, choices: list[MenuChoice]) -> MenuHandle:
        channel = await self.get_or_create_channel(channel_name)
        view = MenuView(choices)
        message = await self.retry_discord_call(
            f"send menu to #{channel.name}",
            lambda: channel.send(self.timestamp_only(), view=view),
        )
        return DiscordMenuHandle(channel_name, message, view)

    async def wait_for_menu_click(self, handle: MenuHandle) -> tuple[int, UserAction]:
        assert isinstance(handle, DiscordMenuHandle)
        index, user = await handle.view.next_click()
        return index, UserAction(str(user.id), user.display_name)

    async def close_menu(self, handle: MenuHandle) -> None:
        assert isinstance(handle, DiscordMenuHandle)
        await disable_view(handle.message, handle.view)

    async def clear_channel(self, channel_name: str) -> None:
        channel = await self.get_or_create_channel(channel_name)
        try:
            await channel.purge(limit=1000)
        except discord.Forbidden:
            LOGGER.exception("Missing permissions to clear #%s (%s)", channel.name, channel.id)
            await self.retry_discord_call(
                f"send clear-channel permission warning to #{channel.name}",
                lambda: channel.send(self.with_timestamp("I do not have permission to clear this game channel.")),
            )
        except discord.HTTPException:
            LOGGER.exception("Failed to clear #%s (%s)", channel.name, channel.id)
            await self.retry_discord_call(
                f"send clear-channel failure warning to #{channel.name}",
                lambda: channel.send(self.with_timestamp("I could not clear this game channel.")),
            )

    async def delete_channels(self, channel_names: list[str]) -> None:
        for channel_name in channel_names:
            channel = self.find_existing_channel(channel_name)
            if not channel:
                continue
            try:
                await channel.delete(reason="Dialog game cleanup requested")
            except discord.NotFound:
                pass
            except discord.Forbidden:
                LOGGER.exception("Missing permissions to delete #%s (%s)", channel.name, channel.id)
                await self.retry_discord_call(
                    f"send delete permission warning to #{channel.name}",
                    lambda: channel.send(self.with_timestamp("I do not have permission to delete this game channel.")),
                )
            else:
                self.channel_cache.pop(channel_name, None)
                self.webhook_fallback_channels.discard(channel.id)
                for cache_key in list(self.webhook_cache):
                    if cache_key[0] == channel.id:
                        del self.webhook_cache[cache_key]

    def find_existing_channel(self, display_name: str) -> discord.TextChannel | None:
        cached = self.channel_cache.get(display_name)
        if cached:
            return cached
        category = discord.utils.get(self.guild.categories, name=self.category_name)
        if not category:
            return None
        topic = self.channel_topic(display_name)
        for channel in category.text_channels:
            if channel.topic == topic:
                self.channel_cache[display_name] = channel
                return channel
        return None

    async def get_or_create_channel(self, display_name: str) -> discord.TextChannel:
        cached = self.channel_cache.get(display_name)
        if cached:
            return cached

        category = discord.utils.get(self.guild.categories, name=self.category_name)
        if not category:
            category = await self.retry_discord_call(
                f"create category {self.category_name!r}",
                lambda: self.guild.create_category(self.category_name),
            )

        topic = self.channel_topic(display_name)
        # Topic is the stable lookup key, so renaming a channel in Discord does
        # not break this session. The session id keeps replay transcripts from
        # being reused when players choose to keep old game channels.
        for channel in category.text_channels:
            if channel.topic == topic:
                self.channel_cache[display_name] = channel
                return channel

        channel = await self.retry_discord_call(
            f"create text channel {display_name!r}",
            lambda: self.guild.create_text_channel(
                slugify(display_name),
                category=category,
                topic=topic,
            ),
        )
        self.channel_cache[display_name] = channel
        return channel

    def channel_topic(self, display_name: str) -> str:
        if self.session_id:
            return f"{self.channel_topic_base} [{self.session_id}]: {display_name}"
        return f"{self.channel_topic_base}: {display_name}"

    async def get_character_webhook(self, channel: discord.TextChannel, character: Character) -> discord.Webhook:
        cache_key = (channel.id, character.key)
        if cache_key in self.webhook_cache:
            return self.webhook_cache[cache_key]
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

    async def warn_webhook_fallback(self, channel: discord.TextChannel) -> None:
        if channel.id in self.webhook_fallback_channels:
            return
        self.webhook_fallback_channels.add(channel.id)
        LOGGER.warning(
            "Missing Manage Webhooks in #%s (%s); falling back to bot-authored character messages.",
            channel.name,
            channel.id,
        )
        await self.retry_discord_call(
            f"send webhook fallback warning to #{channel.name}",
            lambda: channel.send(
                self.with_timestamp(
                    "I cannot use character webhooks in this channel because Discord returned "
                    "`Missing Permissions` for webhook access. Falling back to regular bot messages."
                )
            ),
        )

    async def send_character_fallback(
        self,
        channel: discord.TextChannel,
        character: Character,
        text: str,
    ) -> None:
        await self.retry_discord_call(
            f"send fallback dialogue to #{channel.name}",
            lambda: channel.send(self.with_timestamp(f"**{character.name}:** {text}")),
        )

    def with_timestamp(self, content: str) -> str:
        if not self.message_timestamps_enabled:
            return content
        return f"{content}\n{self.timestamp_line()}"

    def timestamp_only(self) -> str | None:
        if not self.message_timestamps_enabled:
            return None
        return self.timestamp_line()

    def timestamp_line(self) -> str:
        sent_at = datetime.now().astimezone().isoformat(timespec="milliseconds")
        return f"`sent {sent_at}`"

    async def retry_discord_call(self, description: str, operation: Callable[[], Awaitable[T]]) -> T:
        for attempt in range(1, self.retry_attempts + 1):
            try:
                return await operation()
            except discord.HTTPException as exc:
                if not is_retryable_discord_error(exc) or attempt == self.retry_attempts:
                    raise
                delay = self.retry_base_delay * (2 ** (attempt - 1))
                LOGGER.warning(
                    "Transient Discord error during %s; retrying in %.1fs (%s/%s): %s",
                    description,
                    delay,
                    attempt,
                    self.retry_attempts,
                    exc,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable retry state")


class SingleButtonView(discord.ui.View):
    def __init__(self, label: str, timeout_seconds: float | None = None) -> None:
        super().__init__(timeout=timeout_seconds)
        self.user: discord.User | discord.Member | None = None
        button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
        button.callback = self.clicked
        self.add_item(button)

    async def clicked(self, interaction: discord.Interaction) -> None:
        self.user = interaction.user
        await interaction.response.defer()
        self.stop()


class MenuView(discord.ui.View):
    def __init__(self, choices: list[MenuChoice]) -> None:
        super().__init__(timeout=None)
        self.queue: asyncio.Queue[tuple[int, discord.User | discord.Member]] = asyncio.Queue()
        self.clicked_users: set[int] = set()
        for choice in choices:
            button = discord.ui.Button(label=choice.text, style=discord.ButtonStyle.secondary)
            button.callback = self.make_callback(choice.index)
            self.add_item(button)

    def make_callback(self, index: int):
        async def callback(interaction: discord.Interaction) -> None:
            # Each user gets one vote per menu showing, but the menu can keep
            # accepting other users until script execution jumps away.
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


def is_retryable_discord_error(exc: discord.HTTPException) -> bool:
    status = getattr(exc, "status", None)
    return isinstance(exc, discord.DiscordServerError) or (status is not None and 500 <= status < 600)


def parse_bool_env(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes", "on"}
