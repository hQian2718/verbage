# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from .io import UserAction
from .model import ScriptGame
from .parser import ScriptLoadError, load_game
from .runtime import GameSession
from .web_io import WebDialogIO


LOGGER = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "web"
LOGO_PATH = REPO_ROOT / "assets" / "logo_transparent.png"
FAVICON_PATH = REPO_ROOT / "docs" / "assets" / "favicon-64.png"

# Hardcoded for now: every room holds one running game in this process.
MAX_ROOMS = 20
MAX_PLAYERS_PER_ROOM = 8
ROOM_CODE_LENGTH = 4
# No I or O, which read as 1 and 0 when a code is passed along by voice or hand.
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"

PLAYER_COUNT_VARIABLE = "num_players"

MAX_NAME_LENGTH = 32
MAX_TEXT_LENGTH = 500
# A portrait is PORTRAIT_SIZE x PORTRAIT_SIZE palette indexes, one hex digit
# each, matching the 32 x 32 grid of the character art. web/painter.js owns the
# 16-colour palette; the server only checks the shape.
PORTRAIT_SIZE = 32
PORTRAIT_PATTERN = re.compile(r"[0-9a-f]{%d}" % (PORTRAIT_SIZE * PORTRAIT_SIZE))
# Per-connection flood guard: at most RATE_LIMIT messages per RATE_WINDOW seconds.
RATE_LIMIT = 30
RATE_WINDOW = 10.0
OUTBOX_LIMIT = 5000
# How often a one-line load summary is logged while anyone is connected.
STATS_INTERVAL = 300.0
# Behind a reverse proxy the peer is always 127.0.0.1, so log the forwarded address.
ACCESS_LOG_FORMAT = '%{X-Forwarded-For}i %a "%r" %s %b %Tfs "%{User-Agent}i"'

HUB_KEY: web.AppKey["Hub"] = web.AppKey("hub")


@dataclass(frozen=True)
class WebConfig:
    game_dir: Path
    title: str = "Verbage"
    idle_timeout: float = 600.0


class Connection:
    """One browser websocket. Outgoing events are queued so they stay ordered."""

    def __init__(self, ws: web.WebSocketResponse) -> None:
        self.ws = ws
        self.outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=OUTBOX_LIMIT)
        self.room: Room | None = None
        self.player: Player | None = None
        self.recent: list[float] = []

    def send(self, event: dict[str, Any]) -> None:
        try:
            self.outbox.put_nowait(event)
        except asyncio.QueueFull:
            # The browser is not reading. Drop it; it can reconnect and resync.
            asyncio.ensure_future(self.ws.close())

    async def pump(self) -> None:
        while True:
            event = await self.outbox.get()
            await self.ws.send_str(json.dumps(event))

    def allow(self) -> bool:
        now = time.monotonic()
        self.recent = [stamp for stamp in self.recent if now - stamp < RATE_WINDOW]
        if len(self.recent) >= RATE_LIMIT:
            return False
        self.recent.append(now)
        return True


@dataclass(eq=False)
class Player:
    """A seat in a room. The token lets the same browser reclaim it later."""

    id: str
    token: str
    name: str
    portrait: str | None
    connections: set[Connection] = field(default_factory=set)

    @property
    def user(self) -> UserAction:
        return UserAction(self.id, self.name)

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "portrait": self.portrait, "online": bool(self.connections)}


@dataclass(eq=False)
class Room:
    """A group of players sharing one game. state is lobby, running, or ended."""

    code: str
    players: dict[str, Player] = field(default_factory=dict)
    state: str = "lobby"
    started_at: float | None = None
    io: WebDialogIO | None = None
    game: GameSession | None = None
    watcher: asyncio.Task[None] | None = None
    idle_since: float | None = field(default_factory=time.monotonic)

    def broadcast(self, event: dict[str, Any]) -> None:
        for player in self.players.values():
            for connection in player.connections:
                connection.send(event)

    def broadcast_players(self) -> None:
        self.broadcast({"type": "players", "players": [player.public() for player in self.players.values()]})

    def describe(self, player: Player) -> dict[str, Any]:
        return {
            "code": self.code,
            "you": player.id,
            "token": player.token,
            "state": self.state,
            "players": [other.public() for other in self.players.values()],
            "channels": self.io.snapshot() if self.io else [],
        }

    @property
    def connected(self) -> bool:
        return any(player.connections for player in self.players.values())


class Hub:
    def __init__(self, config: WebConfig) -> None:
        self.config = config
        # Loading here makes a broken script fail at startup, not on first play.
        self.script: ScriptGame = load_game(config.game_dir)
        self.rooms: dict[str, Room] = {}
        self.reaper: asyncio.Task[None] | None = None
        self.reporter: asyncio.Task[None] | None = None
        self.started_at = time.monotonic()
        self.connections = 0
        LOGGER.info(
            "event=scripts_loaded game_dir=%s labels=%s characters=%s",
            config.game_dir, len(self.script.labels), len(self.script.characters),
        )

    # ---- lifecycle ---------------------------------------------------------

    async def startup(self, app: web.Application) -> None:
        self.reaper = asyncio.create_task(self.reap_idle_rooms(), name="web-room-reaper")
        self.reporter = asyncio.create_task(self.report_stats(), name="web-stats")
        LOGGER.info("event=startup max_rooms=%s max_players_per_room=%s idle_timeout=%s", MAX_ROOMS, MAX_PLAYERS_PER_ROOM, self.config.idle_timeout)

    async def shutdown(self, app: web.Application) -> None:
        LOGGER.info("event=shutdown %s", self.stats_line())
        for task in (self.reaper, self.reporter):
            if task:
                task.cancel()
        for room in list(self.rooms.values()):
            await self.discard(room, "shutdown")

    def stats(self) -> dict[str, Any]:
        players = [player for room in self.rooms.values() for player in room.players.values()]
        return {
            "uptime_seconds": round(time.monotonic() - self.started_at),
            "rooms": len(self.rooms),
            "max_rooms": MAX_ROOMS,
            "games_running": sum(1 for room in self.rooms.values() if room.state == "running"),
            "players": len(players),
            "players_online": sum(1 for player in players if player.connections),
            "connections": self.connections,
        }

    def stats_line(self) -> str:
        return " ".join(f"{key}={value}" for key, value in self.stats().items())

    async def report_stats(self) -> None:
        # A steady heartbeat for dashboards and alerts; silent while nobody is here.
        while True:
            await asyncio.sleep(STATS_INTERVAL)
            if self.rooms or self.connections:
                LOGGER.info("event=stats %s", self.stats_line())

    async def reap_idle_rooms(self) -> None:
        while True:
            await asyncio.sleep(min(30.0, max(1.0, self.config.idle_timeout / 2)))
            now = time.monotonic()
            for room in list(self.rooms.values()):
                if room.idle_since is not None and now - room.idle_since > self.config.idle_timeout:
                    await self.discard(room, "idle")

    def fresh_script(self) -> ScriptGame:
        # Re-read scripts for every new game, like /start does on Discord, but
        # keep serving the last good copy if an edit on disk is broken.
        try:
            self.script = load_game(self.config.game_dir)
        except ScriptLoadError:
            LOGGER.exception("event=script_reload_failed game_dir=%s; using the last good scripts", self.config.game_dir)
        return self.script

    # ---- rooms -------------------------------------------------------------

    async def create_room(self) -> Room | None:
        if len(self.rooms) >= MAX_ROOMS:
            # Reclaim the room that has sat empty the longest, if there is one.
            empty = [room for room in self.rooms.values() if room.idle_since is not None]
            if not empty:
                LOGGER.warning("event=rooms_full rooms=%s", len(self.rooms))
                return None
            await self.discard(min(empty, key=lambda room: room.idle_since or 0.0), "reclaimed")
        while True:
            code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))
            if code not in self.rooms:
                break
        room = Room(code)
        self.rooms[code] = room
        LOGGER.info("event=room_created room=%s rooms=%s", code, len(self.rooms))
        return room

    def seat(self, room: Room, name: str, portrait: str | None) -> Player | None:
        if len(room.players) >= MAX_PLAYERS_PER_ROOM:
            # Seats held by browsers that went away are given up first.
            absent = next((player for player in room.players.values() if not player.connections), None)
            if absent is None:
                LOGGER.warning("event=room_full room=%s players=%s", room.code, len(room.players))
                return None
            del room.players[absent.id]
            LOGGER.info("event=seat_reclaimed room=%s player=%r", room.code, absent.name)
        taken = {player.name for player in room.players.values()}
        unique, suffix = name, 2
        while unique in taken:
            unique = f"{name} {suffix}"
            suffix += 1
        player = Player(secrets.token_hex(8), secrets.token_urlsafe(24), unique, portrait)
        room.players[player.id] = player
        return player

    async def start_game(self, room: Room) -> None:
        if room.state == "running":
            return
        io = WebDialogIO(images_dir=self.fresh_script().game_dir / "images")
        io.listeners.add(room.broadcast)
        await io.prepare_session(room.code)
        game = GameSession(io, self.script, scope_name=f"web:{room.code}")
        # Scripts that declare num_players get the head count instead of having
        # to ask for it. Seats whose browser is gone are not counted.
        if PLAYER_COUNT_VARIABLE in game.variables:
            game.variables[PLAYER_COUNT_VARIABLE] = max(1, sum(1 for p in room.players.values() if p.connections))
        room.io, room.game, room.state = io, game, "running"
        room.started_at = time.monotonic()
        # reset tells browsers to drop the transcript of any earlier game.
        room.broadcast({"type": "status", "state": "running", "reset": True})
        await game.start()
        room.watcher = asyncio.create_task(self.watch(room, game), name=f"web-watch-{room.code}")
        LOGGER.info(
            "event=game_started room=%s players_online=%s",
            room.code, sum(1 for p in room.players.values() if p.connections),
        )

    async def watch(self, room: Room, game: GameSession) -> None:
        assert game.root_task is not None
        await asyncio.wait({game.root_task})
        duration = time.monotonic() - (room.started_at or time.monotonic())
        LOGGER.info("event=game_ended room=%s seconds=%.0f", room.code, duration)
        if room.game is game:
            room.state = "ended"
            room.broadcast({"type": "status", "state": "ended"})

    async def stop_game(self, room: Room, reason: str) -> None:
        if room.game and not room.game.done:
            await room.game.stop(reason)

    async def discard(self, room: Room, reason: str) -> None:
        if self.rooms.pop(room.code, None) is not None:
            LOGGER.info("event=room_closed room=%s reason=%s state=%s rooms=%s", room.code, reason, room.state, len(self.rooms))
        await self.stop_game(room, "Room closed.")
        if room.watcher:
            room.watcher.cancel()
        for player in list(room.players.values()):
            for connection in list(player.connections):
                self.detach(connection)
                self.send_landing(connection, "That room has closed.")

    def send_landing(self, connection: Connection, notice: str | None = None) -> None:
        connection.send({"type": "welcome", "title": self.config.title, "room": None, "notice": notice})

    def attach(self, connection: Connection, room: Room, player: Player) -> None:
        self.detach(connection)
        connection.room, connection.player = room, player
        # The snapshot is queued and the connection added with no await in
        # between, so the browser sees every later event exactly once.
        connection.send({"type": "welcome", "title": self.config.title, "room": room.describe(player)})
        player.connections.add(connection)
        room.idle_since = None
        room.broadcast_players()

    def detach(self, connection: Connection) -> None:
        room, player = connection.room, connection.player
        if room is None or player is None:
            return
        connection.room = connection.player = None
        player.connections.discard(connection)
        if not player.connections and player.id in room.players:
            LOGGER.info("event=player_away room=%s player=%r", room.code, player.name)
        if not room.connected:
            room.idle_since = time.monotonic()
        room.broadcast_players()

    async def leave(self, connection: Connection) -> None:
        room, player = connection.room, connection.player
        if room is None or player is None:
            return
        room.players.pop(player.id, None)
        LOGGER.info("event=player_left room=%s player=%r players=%s", room.code, player.name, len(room.players))
        for other in list(player.connections):
            self.detach(other)
            self.send_landing(other)
        if room.players:
            room.broadcast_players()
        else:
            await self.discard(room, "empty")

    # ---- protocol ------------------------------------------------------------

    async def handle(self, connection: Connection, message: dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "hello":
            room = self.find_room(message.get("room"))
            token = message.get("token")
            player = None
            if room and isinstance(token, str):
                player = next((p for p in room.players.values() if secrets.compare_digest(p.token, token)), None)
            if room and player:
                LOGGER.info("event=player_resumed room=%s player=%r state=%s", room.code, player.name, room.state)
                self.attach(connection, room, player)
            else:
                self.detach(connection)
                self.send_landing(connection)
            return
        if kind in ("create", "join"):
            await self.enter(connection, message, create=kind == "create")
            return

        room, player = connection.room, connection.player
        if room is None or player is None:
            return
        if kind == "leave":
            await self.leave(connection)
        elif kind == "start":
            await self.start_game(room)
        elif room.state != "running" or room.io is None:
            return
        elif kind == "stop":
            LOGGER.info("event=game_stopped room=%s player=%r", room.code, player.name)
            await self.stop_game(room, f"{player.name} ended the game.")
        elif kind == "say":
            channel, text = message.get("channel"), message.get("text")
            if isinstance(channel, str) and isinstance(text, str) and text.strip():
                room.io.post_message(channel, text.strip()[:MAX_TEXT_LENGTH], player.user)
        elif kind == "button":
            if isinstance(message.get("id"), int):
                room.io.click_button(message["id"], player.user)
        elif kind == "menu":
            if isinstance(message.get("id"), int) and isinstance(message.get("index"), int):
                room.io.click_menu(message["id"], message["index"], player.user)

    async def enter(self, connection: Connection, message: dict[str, Any], create: bool) -> None:
        if connection.room:
            await self.leave(connection)
        if create:
            room = await self.create_room()
            if room is None:
                connection.send({"type": "error", "message": f"All {MAX_ROOMS} rooms are in use right now. Please try again in a few minutes."})
                return
        else:
            room = self.find_room(message.get("room"))
            if room is None:
                connection.send({"type": "error", "message": "There is no room with that code."})
                return
        player = self.seat(room, clean_name(message.get("name")), clean_portrait(message.get("portrait")))
        if player is None:
            connection.send({"type": "error", "message": f"That room is full ({MAX_PLAYERS_PER_ROOM} players)."})
            return
        LOGGER.info(
            "event=player_joined room=%s player=%r portrait=%s players=%s state=%s",
            room.code, player.name, player.portrait is not None, len(room.players), room.state,
        )
        self.attach(connection, room, player)

    def find_room(self, raw: Any) -> Room | None:
        return self.rooms.get(raw.strip().upper()) if isinstance(raw, str) else None


def clean_name(raw: Any) -> str:
    if not isinstance(raw, str):
        return "Player"
    # "$" is dropped because script text interpolates $names after $(username()).
    name = " ".join(raw.replace("$", "").split())[:MAX_NAME_LENGTH].strip()
    return name or "Player"


def clean_portrait(raw: Any) -> str | None:
    return raw if isinstance(raw, str) and PORTRAIT_PATTERN.fullmatch(raw) else None


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    hub = request.app[HUB_KEY]
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=8192)
    await ws.prepare(request)
    connection = Connection(ws)
    pump = asyncio.create_task(connection.pump())
    hub.connections += 1
    try:
        async for frame in ws:
            if frame.type != WSMsgType.TEXT or not connection.allow():
                continue
            try:
                message = json.loads(frame.data)
            except ValueError:
                continue
            if isinstance(message, dict):
                try:
                    await hub.handle(connection, message)
                except Exception:
                    # One bad message must not take the player's connection down.
                    LOGGER.exception("event=handler_error type=%r room=%s", message.get("type"), connection.room.code if connection.room else None)
    finally:
        hub.connections -= 1
        hub.detach(connection)
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await pump
    return ws


async def index_handler(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def logo_handler(request: web.Request) -> web.FileResponse:
    return web.FileResponse(LOGO_PATH)


async def favicon_handler(request: web.Request) -> web.FileResponse:
    return web.FileResponse(FAVICON_PATH)


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, **request.app[HUB_KEY].stats()})


async def add_headers(request: web.Request, response: web.StreamResponse) -> None:
    # Always revalidate so a deploy shows up without a hard refresh.
    response.headers.setdefault("Cache-Control", "no-cache")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https: http:; connect-src 'self' ws: wss:; "
        "frame-ancestors 'none'; base-uri 'none'",
    )


def create_app(config: WebConfig) -> web.Application:
    app = web.Application()
    hub = Hub(config)
    app[HUB_KEY] = hub
    app.on_startup.append(hub.startup)
    app.on_shutdown.append(hub.shutdown)
    app.on_response_prepare.append(add_headers)

    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", websocket_handler)
    app.router.add_get("/healthz", health_handler)
    app.router.add_get("/logo.png", logo_handler)
    app.router.add_get("/favicon.png", favicon_handler)
    app.router.add_static("/static/", STATIC_DIR)
    images_dir = hub.script.game_dir / "images"
    if images_dir.is_dir():
        app.router.add_static("/game-images/", images_dir)
    return app
