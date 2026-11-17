# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .io import MenuChoice, MenuHandle, TextInput, UserAction
from .model import Character


Listener = Callable[[dict[str, Any]], None]

# Oldest transcript items are dropped past this point so one long-running
# session cannot grow without bound.
MAX_ITEMS_PER_CHANNEL = 2000


@dataclass
class WebMenuHandle:
    channel_name: str
    item: dict[str, Any]
    queue: asyncio.Queue[tuple[int, UserAction]] = field(default_factory=asyncio.Queue)
    clicked_users: set[str] = field(default_factory=set)


@dataclass
class WebChannel:
    name: str
    # The runtime binds channels before anything happens in them (the entry
    # label claims the default channel just to jump away). Browsers only learn
    # about a channel once it has content, a link pointing at it, or a prompt.
    visible: bool = False
    items: list[dict[str, Any]] = field(default_factory=list)
    input_waiters: list[asyncio.Future[TextInput]] = field(default_factory=list)


class WebDialogIO:
    """DialogIO adapter that keeps a browser-renderable transcript in memory.

    Every change is pushed to listeners as a small JSON-safe event, and
    snapshot() returns the whole state so a browser can attach or reconnect at
    any time. Player actions arrive through post_message(), click_button(), and
    click_menu(). This module knows nothing about HTTP or websockets.
    """

    def __init__(self, images_dir: Path | None = None, image_url_prefix: str = "game-images/") -> None:
        self.images_dir = images_dir
        self.image_url_prefix = image_url_prefix
        self.session_id: str | None = None
        self.channels: dict[str, WebChannel] = {}
        self.listeners: set[Listener] = set()
        self.buttons: dict[int, asyncio.Future[UserAction]] = {}
        self.menus: dict[int, WebMenuHandle] = {}
        self.next_item_id = itertools.count(1)

    # ---- browser-facing state -------------------------------------------

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "name": channel.name,
                "awaiting_input": bool(channel.input_waiters),
                "items": [self.public_item(item) for item in channel.items],
            }
            for channel in self.channels.values()
            if channel.visible
        ]

    def public_item(self, item: dict[str, Any]) -> dict[str, Any]:
        # Deadlines are stored on the event loop clock; browsers get the
        # seconds remaining at the moment of serialization instead.
        public = {key: value for key, value in item.items() if key != "deadline"}
        deadline = item.get("deadline")
        if deadline is not None and item.get("open"):
            public["remaining"] = max(0.0, deadline - asyncio.get_running_loop().time())
        return public

    def emit(self, event: dict[str, Any]) -> None:
        for listener in list(self.listeners):
            listener(event)

    # ---- player actions --------------------------------------------------

    def post_message(self, channel_name: str, text: str, user: UserAction) -> bool:
        """Record a player message; it answers a pending input() if there is one."""
        channel = self.channels.get(channel_name)
        if channel is None or not channel.visible:
            return False
        self.add_item(channel, {"kind": "player", "player": user.user_id, "speaker": user.display_name, "text": text})
        while channel.input_waiters:
            waiter = channel.input_waiters.pop(0)
            if not waiter.done():
                waiter.set_result(TextInput(text, user))
                break
        self.emit_awaiting(channel)
        return True

    def click_button(self, item_id: int, user: UserAction) -> bool:
        future = self.buttons.get(item_id)
        if future is None or future.done():
            return False
        future.set_result(user)
        return True

    def click_menu(self, item_id: int, index: int, user: UserAction) -> bool:
        handle = self.menus.get(item_id)
        if handle is None or not handle.item["open"]:
            return False
        if all(choice["index"] != index for choice in handle.item["choices"]):
            return False
        # Same rule as the Discord adapter: one click per user per menu showing.
        if user.user_id in handle.clicked_users:
            return False
        handle.clicked_users.add(user.user_id)
        picks = handle.item["picks"] + [{"index": index, "player": user.user_id, "user": user.display_name}]
        self.update_item(handle.channel_name, handle.item, picks=picks)
        handle.queue.put_nowait((index, user))
        return True

    # ---- DialogIO ----------------------------------------------------------

    async def prepare_session(self, session_id: str) -> None:
        self.session_id = session_id

    async def ensure_channel(self, channel_name: str) -> None:
        self.get_channel(channel_name)

    async def typing_pause(self, channel_name: str, seconds: float) -> None:
        if seconds > 0:
            self.reveal(self.get_channel(channel_name))
            self.emit({"type": "typing", "channel": channel_name, "seconds": seconds})
            await asyncio.sleep(seconds)

    async def send_notice(self, channel_name: str, text: str) -> None:
        self.add_item(self.get_channel(channel_name), {"kind": "notice", "text": text})

    async def send_narration(self, channel_name: str, text: str) -> None:
        self.add_item(self.get_channel(channel_name), {"kind": "narration", "text": text})

    async def send_character_dialogue(self, channel_name: str, character: Character, text: str) -> None:
        self.add_item(
            self.get_channel(channel_name),
            {
                "kind": "dialogue",
                "speaker": character.name,
                "character": character.key,
                "color": character.color,
                "avatar": self.image_url(character.image_path),
                "text": text,
            },
        )

    async def send_image(self, channel_name: str, source: str, image_path: Path | None, caption: str | None = None) -> None:
        url = self.image_url(image_path) if image_path else source
        self.add_item(self.get_channel(channel_name), {"kind": "image", "url": url, "caption": caption})

    async def send_channel_link(self, channel_name: str, label: str, target_channel_name: str) -> None:
        self.reveal(self.get_channel(target_channel_name))
        self.add_item(self.get_channel(channel_name), {"kind": "link", "text": label, "target": target_channel_name})

    async def wait_for_input(self, channel_name: str, prompt: str | None = None) -> TextInput:
        channel = self.get_channel(channel_name)
        if prompt:
            self.add_item(channel, {"kind": "prompt", "text": prompt})
        waiter: asyncio.Future[TextInput] = asyncio.get_running_loop().create_future()
        channel.input_waiters.append(waiter)
        self.reveal(channel)
        self.emit_awaiting(channel)
        try:
            return await waiter
        finally:
            # Also runs when the runtime cancels the wait (timeout or stop).
            if waiter in channel.input_waiters:
                channel.input_waiters.remove(waiter)
            self.emit_awaiting(channel)

    async def wait_for_button(
        self,
        channel_name: str,
        label: str,
        timeout_seconds: float | None = None,
    ) -> UserAction | None:
        channel = self.get_channel(channel_name)
        loop = asyncio.get_running_loop()
        item: dict[str, Any] = {"kind": "button", "text": label, "open": True, "clicked_by": None}
        if timeout_seconds is not None:
            item["deadline"] = loop.time() + timeout_seconds
        self.add_item(channel, item)
        future: asyncio.Future[UserAction] = loop.create_future()
        self.buttons[item["id"]] = future
        action: UserAction | None = None
        try:
            action = await asyncio.wait_for(future, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            pass
        finally:
            del self.buttons[item["id"]]
            self.update_item(channel_name, item, open=False, clicked_by=action.display_name if action else None)
        return action

    async def open_menu(
        self,
        channel_name: str,
        choices: list[MenuChoice],
        timeout_seconds: float | None = None,
    ) -> MenuHandle:
        channel = self.get_channel(channel_name)
        item: dict[str, Any] = {
            "kind": "menu",
            "choices": [{"index": choice.index, "text": choice.text} for choice in choices],
            "open": True,
            "picks": [],
        }
        if timeout_seconds is not None:
            item["deadline"] = asyncio.get_running_loop().time() + timeout_seconds
        self.add_item(channel, item)
        handle = WebMenuHandle(channel_name, item)
        self.menus[item["id"]] = handle
        return handle

    async def wait_for_menu_click(self, handle: MenuHandle) -> tuple[int, UserAction]:
        assert isinstance(handle, WebMenuHandle)
        return await handle.queue.get()

    async def close_menu(self, handle: MenuHandle) -> None:
        assert isinstance(handle, WebMenuHandle)
        self.menus.pop(handle.item["id"], None)
        self.update_item(handle.channel_name, handle.item, open=False)

    async def clear_channel(self, channel_name: str) -> None:
        channel = self.get_channel(channel_name)
        # Open buttons and menus stay answerable: their script is still waiting.
        channel.items = [item for item in channel.items if item.get("open")]
        if not channel.visible:
            return
        self.emit({"type": "clear", "channel": channel_name})
        for item in channel.items:
            self.emit({"type": "item", "channel": channel_name, "item": self.public_item(item)})

    async def delete_channels(self, channel_names: list[str]) -> None:
        for channel_name in channel_names:
            channel = self.channels.pop(channel_name, None)
            if channel is not None and channel.visible:
                self.emit({"type": "remove_channel", "channel": channel_name})

    # ---- helpers -----------------------------------------------------------

    def get_channel(self, channel_name: str) -> WebChannel:
        channel = self.channels.get(channel_name)
        if channel is None:
            channel = WebChannel(channel_name)
            self.channels[channel_name] = channel
        return channel

    def reveal(self, channel: WebChannel) -> None:
        if not channel.visible:
            channel.visible = True
            self.emit({"type": "channel", "channel": channel.name})

    def add_item(self, channel: WebChannel, item: dict[str, Any]) -> None:
        self.reveal(channel)
        item["id"] = next(self.next_item_id)
        channel.items.append(item)
        if len(channel.items) > MAX_ITEMS_PER_CHANNEL:
            del channel.items[: len(channel.items) - MAX_ITEMS_PER_CHANNEL]
        self.emit({"type": "item", "channel": channel.name, "item": self.public_item(item)})

    def update_item(self, channel_name: str, item: dict[str, Any], **patch: Any) -> None:
        item.update(patch)
        self.emit({"type": "update", "channel": channel_name, "id": item["id"], "patch": patch})

    def emit_awaiting(self, channel: WebChannel) -> None:
        self.emit({"type": "awaiting", "channel": channel.name, "value": bool(channel.input_waiters)})

    def image_url(self, image_path: Path | None) -> str | None:
        if image_path is None or self.images_dir is None:
            return None
        try:
            relative = image_path.relative_to(self.images_dir)
        except ValueError:
            return None
        return self.image_url_prefix + quote(relative.as_posix())
