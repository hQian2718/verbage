# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

from .config import GameConfig
from .expressions import eval_condition, eval_expr_text, exec_statement
from .io import DialogIO, MenuChoice, UserAction
from .model import (
    Button,
    ChannelLink,
    ClearChannel,
    Continue,
    Dialogue,
    ExprStatement,
    If,
    InputBlock,
    Jump,
    Label,
    LabelRef,
    Menu,
    Run,
    ScriptGame,
    ShowImage,
    Statement,
    TimeLimit,
    Wait,
)
from .parser import resolve_label


LOGGER = logging.getLogger(__name__)


class RuntimeErrorWithContext(Exception):
    pass


class JumpSignal(Exception):
    # Jumps are control-flow, not failures. Raising through nested blocks lets
    # menus/buttons/ifs abort their current body exactly like a Ren'Py jump.
    def __init__(self, target: LabelRef) -> None:
        self.target = target


class ContinueSignal(Exception):
    # Continue is scoped to the nearest menu. It lets an option body finish the
    # menu and resume at the statement after the menu in the same label.
    pass


@dataclass
class EventContext:
    # One EventContext represents one running script event. Parent and child
    # events share session variables, but keep their own channel and clicker.
    session: "GameSession"
    event_id: str
    namespace: str
    channel_name: str | None = None
    last_click_user: UserAction | None = None
    pending_dialogue_delay: float | None = None

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

    async def wait_for_input(self, prompt: str | None = None) -> str:
        if not self.channel_name:
            raise RuntimeErrorWithContext("input() used before entering a channel")

        # input() consumes the next human-authored message in the current event
        # channel. The IO adapter decides where that message comes from.
        result = await self.session.io.wait_for_input(self.channel_name, prompt)
        self.last_click_user = result.user
        return result.text

    def username(self) -> str:
        if not self.last_click_user:
            return ""
        return self.last_click_user.display_name


class GameManager:
    def __init__(self, cleanup_prompt_enabled: bool = True) -> None:
        self.cleanup_prompt_enabled = cleanup_prompt_enabled
        self.sessions: dict[int, GameSession] = {}

    async def start(self, scope_id: int, io: DialogIO, game: ScriptGame) -> str:
        existing = self.sessions.get(scope_id)
        if existing and not existing.done:
            return "A game is already running in this server. Use `/stop` first."
        if existing:
            await existing.cancel_cleanup_prompt()
        session_id = secrets.token_hex(4)
        await io.prepare_session(session_id)
        session = GameSession(
            io,
            game,
            scope_name=f"{scope_id}:{session_id}",
            cleanup_prompt_enabled=self.cleanup_prompt_enabled,
        )
        self.sessions[scope_id] = session
        await session.start()
        return "Starting the game."

    async def stop(self, scope_id: int, reason: str) -> str:
        session = self.sessions.get(scope_id)
        if not session or session.done:
            return "No game is running in this server."
        await session.stop(reason, offer_cleanup=self.cleanup_prompt_enabled)
        return "Stopped the game. Cleanup prompt posted."

    def status(self, scope_id: int | None) -> str:
        if not scope_id or scope_id not in self.sessions or self.sessions[scope_id].done:
            return "No game is running."
        session = self.sessions[scope_id]
        active = ", ".join(sorted(session.active_channels)) or "none"
        return f"Game running. Active channels: {active}. Variables: {len(session.variables)}."


@dataclass
class GameSession:
    # MVP state is intentionally in memory. A restart drops tasks, variables,
    # channel locks, and adapter caches while leaving external channels intact.
    io: DialogIO
    game: ScriptGame
    scope_name: str = "local"
    variables: dict[str, Any] = field(init=False)
    var_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_channels: dict[str, str] = field(default_factory=dict)
    known_channels: set[str] = field(default_factory=set)
    last_channel_name: str | None = None
    config: GameConfig = field(default_factory=GameConfig.from_env)
    cleanup_prompt_enabled: bool = False
    tasks: set[asyncio.Task[Any]] = field(default_factory=set)
    root_task: asyncio.Task[Any] | None = None
    timeout_task: asyncio.Task[Any] | None = None
    cleanup_task: asyncio.Task[Any] | None = None
    done: bool = False

    def __post_init__(self) -> None:
        self.variables = dict(self.game.defaults)
        self.delay_per_char = self.config.delay_per_char
        self.min_delay = self.config.min_delay
        self.max_delay = self.config.max_delay
        self.typing_delay = self.config.typing_delay
        self.wait_scale = self.config.wait_scale
        self.cleanup_prompt_timeout = self.config.cleanup_prompt_timeout

    async def start(self) -> None:
        self.root_task = asyncio.create_task(self.run_root(), name=f"dialog-game-{self.scope_name}")
        self.tasks.add(self.root_task)
        self.root_task.add_done_callback(self.tasks.discard)

    async def stop(self, reason: str, offer_cleanup: bool = False) -> None:
        self.done = True
        current = asyncio.current_task()
        if self.timeout_task:
            self.timeout_task.cancel()
        # Do not cancel the task currently executing stop(); timeout/fatal paths
        # call this method from inside a tracked task.
        for task in list(self.tasks):
            if task is not current:
                task.cancel()
        for channel_name in set(self.known_channels):
            try:
                await self.io.send_notice(channel_name, reason)
            except Exception:
                LOGGER.exception("Failed to post stop notice in %s", channel_name)
        if offer_cleanup:
            self.start_cleanup_prompt()

    async def run_root(self) -> None:
        context = EventContext(self, secrets.token_hex(4), "main")
        try:
            await self.run_label(context, self.game.labels[("main", "setup")])
            # The playable story is over as soon as the root label returns.
            # Cleanup is intentionally backgrounded so /start can create the
            # next session while the old delete/keep prompt is still visible.
            self.done = True
            if self.cleanup_prompt_enabled:
                self.start_cleanup_prompt()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.fatal(context, exc)
        finally:
            self.done = True
            if self.timeout_task:
                self.timeout_task.cancel()

    async def cancel_cleanup_prompt(self) -> None:
        if not self.cleanup_task or self.cleanup_task.done():
            return
        self.cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.cleanup_task

    def start_cleanup_prompt(self) -> asyncio.Task[Any] | None:
        if not self.cleanup_prompt_enabled or not self.known_channels:
            return None
        if self.cleanup_task and not self.cleanup_task.done():
            return self.cleanup_task
        self.cleanup_task = asyncio.create_task(
            self.offer_channel_cleanup(),
            name=f"dialog-cleanup-{self.scope_name}",
        )
        self.cleanup_task.add_done_callback(self.log_cleanup_exception)
        return self.cleanup_task

    def log_cleanup_exception(self, task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            LOGGER.exception("Cleanup prompt failed in scope %s", self.scope_name)

    async def fatal(self, context: EventContext, exc: Exception) -> None:
        error_id = secrets.token_hex(3)
        LOGGER.exception("Runtime error %s in scope %s", error_id, self.scope_name)
        message = f"The game hit a runtime error. Error id: `{error_id}`."
        if context.channel_name:
            await self.io.send_notice(context.channel_name, message)
        else:
            for channel_name in set(self.known_channels):
                await self.io.send_notice(channel_name, message)
        await self.stop("Game halted after a runtime error.")

    async def run_label(self, context: EventContext, label: Label) -> None:
        while True:
            context.namespace = label.namespace
            await self.bind_channel(context, self.channel_for_label(label))
            try:
                await self.execute_block(context, label.body)
                await self.flush_pending_dialogue_delay(context)
                await self.release_channel(context)
                return
            except JumpSignal as jump:
                # jump never returns to the old label; it rebinds this same event
                # to the target label and continues from the top of that body.
                label = resolve_label(self.game, context.namespace, jump.target)

    def channel_for_label(self, label: Label) -> str:
        return label.channel or self.config.default_channel.strip() or "Game"

    async def bind_channel(self, context: EventContext, channel_name: str | None) -> None:
        if context.channel_name == channel_name:
            return
        await self.release_channel(context)
        if not channel_name:
            context.channel_name = None
            return
        async with self.active_lock:
            # The language guarantees only one running label per channel. This
            # catches accidental run/jump combinations that would interleave text.
            owner = self.active_channels.get(channel_name)
            if owner and owner != context.event_id:
                raise RuntimeErrorWithContext(f"channel {channel_name!r} is already running")
            self.active_channels[channel_name] = context.event_id
        self.known_channels.add(channel_name)
        await self.io.ensure_channel(channel_name)
        context.channel_name = channel_name
        self.last_channel_name = channel_name

    async def release_channel(self, context: EventContext) -> None:
        if not context.channel_name:
            return
        async with self.active_lock:
            if self.active_channels.get(context.channel_name) == context.event_id:
                del self.active_channels[context.channel_name]
        context.channel_name = None

    async def execute_block(self, context: EventContext, statements: list[Statement]) -> None:
        for statement in statements:
            await self.apply_pending_dialogue_delay(context, statement)
            await self.execute_statement(context, statement)

    async def apply_pending_dialogue_delay(self, context: EventContext, next_statement: Statement) -> None:
        if context.pending_dialogue_delay is None:
            return
        await self.flush_pending_dialogue_delay(context)

    async def flush_pending_dialogue_delay(self, context: EventContext) -> None:
        if context.pending_dialogue_delay is None:
            return
        delay = context.pending_dialogue_delay
        context.pending_dialogue_delay = None
        if delay:
            await asyncio.sleep(delay)

    async def execute_statement(self, context: EventContext, statement: Statement) -> None:
        if isinstance(statement, Dialogue):
            await self.send_dialogue(context, statement)
        elif isinstance(statement, ShowImage):
            await self.send_image(context, statement)
        elif isinstance(statement, Jump):
            raise JumpSignal(statement.target)
        elif isinstance(statement, Continue):
            raise ContinueSignal()
        elif isinstance(statement, Run):
            await self.run_children(context, statement)
        elif isinstance(statement, Menu):
            await self.show_menu(context, statement)
        elif isinstance(statement, Button):
            await self.show_button(context, statement)
        elif isinstance(statement, InputBlock):
            await self.show_input(context, statement)
        elif isinstance(statement, If):
            for branch in statement.branches:
                if branch.condition is None or await eval_condition(branch.condition, context):
                    await self.execute_block(context, branch.body)
                    break
        elif isinstance(statement, Wait):
            await asyncio.sleep(statement.seconds * self.wait_scale)
        elif isinstance(statement, ClearChannel):
            self.known_channels.add(statement.channel)
            await self.io.ensure_channel(statement.channel)
            await self.io.clear_channel(statement.channel)
        elif isinstance(statement, ChannelLink):
            await self.send_channel_link(context, statement)
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

        # run is fork-join: all child labels execute concurrently, and the parent
        # resumes only after every child has finished.
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
        for channel_name in set(self.known_channels):
            await self.io.send_notice(channel_name, notice)
        await self.stop(notice)

    async def send_dialogue(self, context: EventContext, statement: Dialogue) -> None:
        if not context.channel_name:
            raise RuntimeErrorWithContext("dialogue emitted before entering a channel")
        text = await self.interpolate(statement.text, context)
        delay = min(self.max_delay, max(self.min_delay, len(text) * self.delay_per_char))
        if not text.strip():
            context.pending_dialogue_delay = delay
            return
        await self.io.typing_pause(context.channel_name, self.typing_delay)
        if not statement.character:
            await self.io.send_narration(context.channel_name, text)
            context.pending_dialogue_delay = delay
            return
        character = self.game.characters[statement.character]
        await self.io.send_character_dialogue(context.channel_name, character, text)
        context.pending_dialogue_delay = delay

    async def send_image(self, context: EventContext, statement: ShowImage) -> None:
        if not context.channel_name:
            raise RuntimeErrorWithContext("image emitted before entering a channel")
        caption = await self.interpolate(statement.caption, context) if statement.caption else None
        await self.io.send_image(context.channel_name, statement.source_text, statement.image_path, caption)

    async def send_channel_link(self, context: EventContext, statement: ChannelLink) -> None:
        if not context.channel_name:
            raise RuntimeErrorWithContext("channel link emitted before entering a channel")
        self.known_channels.add(statement.channel)
        await self.io.ensure_channel(statement.channel)
        await self.io.send_channel_link(context.channel_name, statement.text, statement.channel)

    async def interpolate(self, text: str, context: EventContext) -> str:
        async def replace_expr(match: re.Match[str]) -> str:
            return str(await eval_expr_text(match.group(1), context))

        # Evaluate explicit $(...) forms before shorthand $identifier so a
        # variable name inside an expression is not substituted too early.
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
        if not context.channel_name:
            raise RuntimeErrorWithContext("button used before entering a channel")
        timeout_seconds = None
        if statement.timeout_seconds is not None:
            timeout_seconds = statement.timeout_seconds * self.wait_scale
        action = await self.io.wait_for_button(context.channel_name, statement.text, timeout_seconds)
        if action is None:
            return
        context.last_click_user = action
        await self.execute_block(context, statement.body)

    async def show_menu(self, context: EventContext, statement: Menu) -> None:
        if not context.channel_name:
            raise RuntimeErrorWithContext("menu used before entering a channel")
        visible = []
        for index, option in enumerate(statement.options):
            if option.condition is None or await eval_condition(option.condition, context):
                visible.append(MenuChoice(index, await self.interpolate(option.text, context)))
        if not visible:
            LOGGER.debug(
                "Skipping menu with no visible options at %s in channel %s",
                statement.source.format(),
                context.channel_name,
            )
            return
        handle = await self.io.open_menu(context.channel_name, visible)
        try:
            while True:
                try:
                    if statement.timeout_seconds is None:
                        index, action = await self.io.wait_for_menu_click(handle)
                    else:
                        index, action = await asyncio.wait_for(
                            self.io.wait_for_menu_click(handle),
                            timeout=statement.timeout_seconds * self.wait_scale,
                        )
                except asyncio.TimeoutError:
                    if statement.timeout_body:
                        await self.execute_block(context, statement.timeout_body)
                    return
                context.last_click_user = action
                option = statement.options[index]
                try:
                    await self.execute_block(context, option.body)
                    await self.flush_pending_dialogue_delay(context)
                except JumpSignal:
                    raise
                except ContinueSignal:
                    await self.flush_pending_dialogue_delay(context)
                    return
                if not statement.persistent:
                    return
        finally:
            await self.io.close_menu(handle)

    async def show_input(self, context: EventContext, statement: InputBlock) -> None:
        if not context.channel_name:
            raise RuntimeErrorWithContext("input block used before entering a channel")
        try:
            if statement.timeout_seconds is None:
                result = await self.io.wait_for_input(context.channel_name, statement.prompt)
            else:
                result = await asyncio.wait_for(
                    self.io.wait_for_input(context.channel_name, statement.prompt),
                    timeout=statement.timeout_seconds * self.wait_scale,
                )
        except asyncio.TimeoutError:
            timeout_case = next((case for case in statement.cases if case.kind == "timeout"), None)
            if timeout_case:
                await self.execute_block(context, timeout_case.body)
            return

        context.last_click_user = result.user
        value = result.text
        await context.set_var(statement.variable, value)
        default_case = None
        for case in statement.cases:
            if case.kind == "timeout":
                continue
            if case.kind == "default":
                default_case = case
                continue
            if case.kind == "contains" and case.expression:
                if await eval_condition(f"{statement.variable} contains {case.expression}", context):
                    await self.execute_block(context, case.body)
                    return
            elif case.kind == "equals" and case.expression:
                if value == await eval_expr_text(case.expression, context):
                    await self.execute_block(context, case.body)
                    return
        if default_case:
            await self.execute_block(context, default_case.body)

    async def offer_channel_cleanup(self) -> None:
        if not self.known_channels:
            return
        prompt_channel = self.last_channel_name or sorted(self.known_channels)[0]
        await self.io.send_notice(prompt_channel, "Game complete. Delete all game channels?")
        handle = await self.io.open_menu(
            prompt_channel,
            [
                MenuChoice(0, "Delete game channels"),
                MenuChoice(1, "Keep channels"),
            ],
        )
        try:
            index, _action = await asyncio.wait_for(
                self.io.wait_for_menu_click(handle),
                timeout=self.cleanup_prompt_timeout,
            )
        except asyncio.TimeoutError:
            index = 1
        finally:
            await self.io.close_menu(handle)

        if index == 0:
            await self.io.delete_channels(sorted(self.known_channels))
        else:
            await self.io.send_notice(prompt_channel, "Keeping game channels.")
