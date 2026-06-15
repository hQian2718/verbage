from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any

from .io import MenuChoice, MenuHandle, UserAction
from .model import Character


@dataclass
class LocalMenuHandle:
    channel_name: str
    choices: list[MenuChoice]


class LocalDialogIO:
    """Local adapter for tests and non-Discord smoke runs.

    Outputs are kept in memory and appended to one transcript file per channel.
    Inputs are supplied by tests through queue_* methods.
    """

    def __init__(self, output_dir: str | Path, message_timestamps: bool = False) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.message_timestamps = message_timestamps
        self.events: list[dict[str, Any]] = []
        self.input_queues: dict[str, asyncio.Queue[str]] = {}
        self.button_queues: dict[tuple[str, str], asyncio.Queue[UserAction]] = {}
        self.menu_queues: dict[str, asyncio.Queue[tuple[int, UserAction]]] = {}
        self.session_id: str | None = None

    async def prepare_session(self, session_id: str) -> None:
        self.session_id = session_id

    def queue_input(self, channel_name: str, text: str) -> None:
        self.input_queues.setdefault(channel_name, asyncio.Queue()).put_nowait(text)

    def queue_button(self, channel_name: str, label: str, display_name: str, user_id: str = "local-user") -> None:
        key = (channel_name, label)
        self.button_queues.setdefault(key, asyncio.Queue()).put_nowait(UserAction(user_id, display_name))

    def queue_menu(self, channel_name: str, index: int, display_name: str, user_id: str = "local-user") -> None:
        self.menu_queues.setdefault(channel_name, asyncio.Queue()).put_nowait((index, UserAction(user_id, display_name)))

    async def ensure_channel(self, channel_name: str) -> None:
        self.channel_path(channel_name).touch(exist_ok=True)
        await self.record(channel_name, "channel", "created")

    async def typing_pause(self, channel_name: str, seconds: float) -> None:
        await self.record(channel_name, "typing", f"{seconds:.3f}s")
        if seconds:
            await asyncio.sleep(seconds)

    async def send_notice(self, channel_name: str, text: str) -> None:
        await self.record(channel_name, "notice", text)

    async def send_narration(self, channel_name: str, text: str) -> None:
        await self.record(channel_name, "narration", text)

    async def send_character_dialogue(self, channel_name: str, character: Character, text: str) -> None:
        await self.record(channel_name, "dialogue", text, speaker=character.name, character=character.key)

    async def send_image(self, channel_name: str, source: str, image_path: Path | None, caption: str | None = None) -> None:
        await self.record(channel_name, "image", caption or "", source=source, path=str(image_path) if image_path else None)

    async def send_channel_link(self, channel_name: str, label: str, target_channel_name: str) -> None:
        await self.ensure_channel(target_channel_name)
        await self.record(channel_name, "channel_link", label, target=target_channel_name)

    async def wait_for_input(self, channel_name: str, prompt: str | None = None) -> str:
        if prompt:
            await self.record(channel_name, "input_prompt", prompt)
        await self.record(channel_name, "input_wait", "")
        text = await self.input_queues.setdefault(channel_name, asyncio.Queue()).get()
        await self.record(channel_name, "input", text)
        return text

    async def wait_for_button(
        self,
        channel_name: str,
        label: str,
        timeout_seconds: float | None = None,
    ) -> UserAction | None:
        await self.record(channel_name, "button", label)
        queue = self.button_queues.setdefault((channel_name, label), asyncio.Queue())
        try:
            if timeout_seconds is None:
                action = await queue.get()
            else:
                action = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            await self.record(channel_name, "button_timeout", label)
            return None
        await self.record(channel_name, "button_click", label, user=action.display_name)
        return action

    async def open_menu(self, channel_name: str, choices: list[MenuChoice]) -> MenuHandle:
        text = " | ".join(f"{choice.index}:{choice.text}" for choice in choices)
        await self.record(channel_name, "menu", text)
        return LocalMenuHandle(channel_name, choices)

    async def wait_for_menu_click(self, handle: MenuHandle) -> tuple[int, UserAction]:
        assert isinstance(handle, LocalMenuHandle)
        index, action = await self.menu_queues.setdefault(handle.channel_name, asyncio.Queue()).get()
        await self.record(handle.channel_name, "menu_click", str(index), user=action.display_name)
        return index, action

    async def close_menu(self, handle: MenuHandle) -> None:
        assert isinstance(handle, LocalMenuHandle)
        await self.record(handle.channel_name, "menu_close", "")

    async def clear_channel(self, channel_name: str) -> None:
        self.channel_path(channel_name).write_text("")
        await self.record(channel_name, "clear", "")

    async def delete_channels(self, channel_names: list[str]) -> None:
        for channel_name in channel_names:
            await self.record(channel_name, "delete", "")
            try:
                self.channel_path(channel_name).unlink()
            except FileNotFoundError:
                pass

    async def record(self, channel_name: str, kind: str, text: str, **extra: Any) -> None:
        event = {"channel": channel_name, "kind": kind, "text": text, **extra}
        if self.message_timestamps and kind in TIMESTAMPED_KINDS:
            event["sent_at"] = datetime.now().astimezone().isoformat(timespec="milliseconds")
            event["sent_at_monotonic"] = monotonic()
            event["text"] = f"{text}\n`sent {event['sent_at']}`" if text else f"`sent {event['sent_at']}`"
        self.events.append(event)
        line = json.dumps(event, sort_keys=True)
        with self.channel_path(channel_name).open("a") as handle:
            handle.write(line + "\n")

    def channel_path(self, channel_name: str) -> Path:
        return self.output_dir / f"{slugify(channel_name)}.jsonl"


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return slug or "dialog"


TIMESTAMPED_KINDS = {
    "notice",
    "narration",
    "dialogue",
    "image",
    "channel_link",
    "input_prompt",
    "button",
    "menu",
}
