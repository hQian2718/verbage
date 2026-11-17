# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from dialogbot.io import UserAction
from dialogbot.parser import load_game
from dialogbot.runtime import GameSession
from dialogbot.web_io import WebDialogIO

try:
    from aiohttp.test_utils import TestClient, TestServer

    from dialogbot import web_server
    from dialogbot.web_server import WebConfig, clean_name, clean_portrait, create_app
except ModuleNotFoundError:
    TestClient = None


SCRIPT = """
define n = Character("Narrator", color="#a48335")
default answer = ""
default who = ""

label setup:
    jump start

label start(channel="Room"):
    n "Welcome."
    input "Say something." into answer:
        case _:
            $ who = username()
    button "Go on":
    menu timeout 30 seconds:
        "Left":
            "You went left, $who."
        "Right":
            "You went right."
    channel link "Next room" to "Hall"
    jump hall

label hall(channel="Hall"):
    "The end."
"""

PLAYER = UserAction("u1", "Ada")


def write_game(root: Path, script: str = SCRIPT) -> Path:
    game_dir = root / "game"
    game_dir.mkdir()
    (game_dir / "main.script").write_text(script)
    return game_dir


def fast_session(io: WebDialogIO, game) -> GameSession:
    session = GameSession(io, game)
    session.min_delay = session.max_delay = session.typing_delay = 0
    return session


async def until(predicate, timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


def kinds(io: WebDialogIO, channel: str) -> list[str]:
    return [item["kind"] for item in io.channels[channel].items]


class WebDialogIOTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_playthrough(self):
        with TemporaryDirectory() as raw_dir:
            game = load_game(write_game(Path(raw_dir)))
            io = WebDialogIO(images_dir=game.game_dir / "images")
            events = []
            io.listeners.add(events.append)
            session = fast_session(io, game)
            await session.start()

            room = lambda: io.channels.get("Room")
            await until(lambda: room() and room().input_waiters)
            # The default channel that `setup` passed through stays hidden.
            self.assertEqual([channel["name"] for channel in io.snapshot()], ["Room"])
            self.assertTrue(io.snapshot()[0]["awaiting_input"])
            io.post_message("Room", "hello", PLAYER)

            await until(lambda: io.buttons)
            button_id = next(iter(io.buttons))
            self.assertFalse(io.click_button(button_id + 100, PLAYER))
            self.assertTrue(io.click_button(button_id, PLAYER))

            await until(lambda: io.menus)
            menu_id = next(iter(io.menus))
            menu = io.snapshot()[0]["items"][-1]
            self.assertTrue(0 < menu["remaining"] <= 30)
            self.assertNotIn("deadline", menu)
            self.assertFalse(io.click_menu(menu_id, 7, PLAYER))
            self.assertTrue(io.click_menu(menu_id, 0, PLAYER))
            self.assertFalse(io.click_menu(menu_id, 1, PLAYER))

            await session.root_task
            self.assertEqual(session.variables["answer"], "hello")
            self.assertEqual(
                kinds(io, "Room"),
                ["dialogue", "prompt", "player", "button", "menu", "narration", "link"],
            )
            items = io.channels["Room"].items
            self.assertEqual(items[3]["clicked_by"], "Ada")
            self.assertFalse(items[4]["open"])
            self.assertEqual(items[4]["picks"], [{"index": 0, "player": "u1", "user": "Ada"}])
            self.assertEqual(items[5]["text"], "You went left, Ada.")
            self.assertEqual(kinds(io, "Hall"), ["narration"])
            self.assertFalse(io.snapshot()[0]["awaiting_input"])
            # Listeners saw every item that the snapshot holds.
            seen = {event["item"]["id"] for event in events if event["type"] == "item"}
            self.assertEqual(seen, {item["id"] for channel in io.channels.values() for item in channel.items})

    async def test_chat_without_pending_input_is_only_a_note(self):
        io = WebDialogIO()
        self.assertFalse(io.post_message("Nowhere", "hi", PLAYER))
        await io.ensure_channel("Room")
        self.assertFalse(io.post_message("Room", "hidden", PLAYER))
        await io.send_narration("Room", "A room.")
        self.assertTrue(io.post_message("Room", "note to self", PLAYER))
        waiter = asyncio.create_task(io.wait_for_input("Room"))
        await asyncio.sleep(0)
        self.assertFalse(waiter.done())
        io.post_message("Room", "answer", PLAYER)
        self.assertEqual((await waiter).text, "answer")

    async def test_button_timeout_and_cancelled_input(self):
        io = WebDialogIO()
        self.assertIsNone(await io.wait_for_button("Room", "Hurry", timeout_seconds=0.01))
        self.assertFalse(io.channels["Room"].items[0]["open"])
        self.assertEqual(io.buttons, {})

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(io.wait_for_input("Room"), timeout=0.01)
        self.assertEqual(io.channels["Room"].input_waiters, [])

    async def test_images_resolve_to_urls(self):
        with TemporaryDirectory() as raw_dir:
            images = Path(raw_dir) / "images"
            images.mkdir()
            io = WebDialogIO(images_dir=images)
            await io.send_image("Room", "bao shang", images / "bao shang.png", "Bao")
            await io.send_image("Room", "https://example.com/a.png", None)
            first, second = io.channels["Room"].items
            self.assertEqual(first["url"], "game-images/bao%20shang.png")
            self.assertEqual(second["url"], "https://example.com/a.png")

    async def test_clear_keeps_open_controls(self):
        io = WebDialogIO()
        await io.send_narration("Room", "old")
        waiting = asyncio.create_task(io.wait_for_button("Room", "Still here"))
        await asyncio.sleep(0)
        await io.clear_channel("Room")
        self.assertEqual(kinds(io, "Room"), ["button"])
        io.click_button(io.channels["Room"].items[0]["id"], PLAYER)
        self.assertEqual((await waiting).display_name, "Ada")


@unittest.skipIf(TestClient is None, "aiohttp is not installed")
class WebServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        fast = {"DIALOG_MIN_DELAY": "0", "DIALOG_MAX_DELAY": "0", "DIALOG_TYPING_DELAY": "0"}
        patcher = mock.patch.dict(os.environ, fast)
        patcher.start()
        self.addCleanup(patcher.stop)
        config = WebConfig(game_dir=write_game(Path(self.tmp.name)), title="Test Game")
        self.client = TestClient(TestServer(create_app(config)))
        await self.client.start_server()
        self.addAsyncCleanup(self.client.close)

    async def connect(self):
        ws = await self.client.ws_connect("/ws")
        self.addAsyncCleanup(ws.close)
        return ws

    async def read_until(self, ws, predicate):
        seen = []
        async with asyncio.timeout(5):
            while True:
                event = await ws.receive_json()
                seen.append(event)
                if predicate(event):
                    return seen

    async def enter(self, ws, **message):
        await ws.send_json(message)
        seen = await self.read_until(ws, lambda e: e["type"] in ("welcome", "error"))
        return seen[-1]

    async def test_pages_are_served(self):
        for path in ("/", "/static/app.js", "/static/painter.js", "/static/style.css", "/logo.png", "/favicon.png", "/healthz"):
            response = await self.client.get(path)
            self.assertEqual(response.status, 200, path)

    async def test_two_players_share_a_game(self):
        ada, bob = await self.connect(), await self.connect()
        await ada.send_json({"type": "hello", "room": None, "token": None})
        self.assertIsNone((await ada.receive_json())["room"])

        portrait = "3" * 1024
        room = (await self.enter(ada, type="create", name="  Ada  $x ", portrait=portrait))["room"]
        self.assertEqual(room["state"], "lobby")
        self.assertEqual(len(room["code"]), 4)
        self.assertEqual(room["players"][0]["name"], "Ada x")
        self.assertEqual(room["players"][0]["portrait"], portrait)

        missing = await self.enter(bob, type="join", room="ZZZZZ", name="Bob")
        self.assertEqual(missing["type"], "error")
        # Codes are case-insensitive, bad portraits are dropped, names are unique.
        joined = (await self.enter(bob, type="join", room=room["code"].lower(), name="Ada x", portrait="nope"))["room"]
        self.assertEqual([p["name"] for p in joined["players"]], ["Ada x", "Ada x 2"])
        self.assertIsNone(joined["players"][1]["portrait"])
        bob_id = joined["you"]
        await self.read_until(ada, lambda e: e["type"] == "players" and len(e["players"]) == 2)

        # Either player may start; both then see the same story.
        with self.assertLogs("dialogbot.web_server", "INFO") as logs:
            await bob.send_json({"type": "start"})
            await self.read_until(ada, lambda e: e["type"] == "status")
        self.assertTrue(any("event=game_started" in line and "players_online=2" in line for line in logs.output))
        health = await (await self.client.get("/healthz")).json()
        self.assertEqual((health["rooms"], health["games_running"], health["players_online"], health["connections"]), (1, 1, 2, 2))
        for ws in (ada, bob):
            await self.read_until(ws, lambda e: e["type"] == "awaiting" and e["value"])
        await bob.send_json({"type": "say", "channel": "Room", "text": "hi"})
        seen = await self.read_until(ada, lambda e: e["type"] == "item" and e["item"]["kind"] == "button")
        said = next(e["item"] for e in seen if e["type"] == "item" and e["item"]["kind"] == "player")
        self.assertEqual((said["player"], said["speaker"], said["text"]), (bob_id, "Ada x 2", "hi"))
        button_id = seen[-1]["item"]["id"]

        # Ada drops and comes back with her token: same seat, full transcript.
        await ada.close()
        await self.read_until(bob, lambda e: e["type"] == "players" and not e["players"][0]["online"])
        ada = await self.connect()
        back = (await self.enter(ada, type="hello", room=room["code"], token=room["token"]))["room"]
        self.assertEqual(back["you"], room["you"])
        self.assertEqual(back["state"], "running")
        self.assertEqual([i["kind"] for i in back["channels"][0]["items"]], ["dialogue", "prompt", "player", "button"])

        await ada.send_json({"type": "button", "id": button_id})
        seen = await self.read_until(bob, lambda e: e["type"] == "item" and e["item"]["kind"] == "menu")
        await bob.send_json({"type": "menu", "id": seen[-1]["item"]["id"], "index": 0})
        seen = await self.read_until(ada, lambda e: e == {"type": "status", "state": "ended"})
        # username() resolved to the player who typed the input.
        self.assertTrue(any(e["type"] == "item" and e["item"].get("text") == "You went left, Ada x 2." for e in seen))

        # Play again resets the transcript for everyone; stop names who ended it.
        await ada.send_json({"type": "start"})
        await self.read_until(bob, lambda e: e == {"type": "status", "state": "running", "reset": True})
        await self.read_until(bob, lambda e: e["type"] == "awaiting" and e["value"])
        await bob.send_json({"type": "stop"})
        seen = await self.read_until(ada, lambda e: e == {"type": "status", "state": "ended"})
        self.assertTrue(any(e["type"] == "item" and e["item"].get("text") == "Ada x 2 ended the game." for e in seen))

        # Leaving frees the seat; the last player out closes the room.
        self.assertIsNone((await self.enter(bob, type="leave"))["room"])
        await self.read_until(ada, lambda e: e["type"] == "players" and len(e["players"]) == 1)
        self.assertIsNone((await self.enter(ada, type="leave"))["room"])
        health = await (await self.client.get("/healthz")).json()
        self.assertEqual((health["ok"], health["rooms"], health["players"], health["games_running"]), (True, 0, 0, 0))

    async def test_player_count_is_given_to_the_script(self):
        (Path(self.tmp.name) / "game" / "main.script").write_text(
            'default num_players = 0\n\nlabel setup:\n    jump start\n\n'
            'label start(channel="Room"):\n    "Party of $num_players."\n'
        )
        ada, bob, gone = await self.connect(), await self.connect(), await self.connect()
        code = (await self.enter(ada, type="create", name="Ada"))["room"]["code"]
        await self.enter(bob, type="join", room=code, name="Bob")
        await self.enter(gone, type="join", room=code, name="Cy")
        await gone.close()
        await self.read_until(ada, lambda e: e["type"] == "players" and not e["players"][-1]["online"])
        await ada.send_json({"type": "start"})
        seen = await self.read_until(bob, lambda e: e["type"] == "item")
        self.assertEqual(seen[-1]["item"]["text"], "Party of 2.")

    async def test_room_and_seat_limits(self):
        with mock.patch.object(web_server, "MAX_ROOMS", 2), mock.patch.object(web_server, "MAX_PLAYERS_PER_ROOM", 2):
            first, second, third = await self.connect(), await self.connect(), await self.connect()
            code = (await self.enter(first, type="create", name="A"))["room"]["code"]
            self.assertIsNotNone((await self.enter(second, type="create", name="B"))["room"])
            self.assertEqual((await self.enter(third, type="create", name="C"))["type"], "error")

            # A full room turns newcomers away until a seat's browser is gone.
            self.assertIsNotNone((await self.enter(third, type="join", room=code, name="C"))["room"])
            fourth = await self.connect()
            self.assertEqual((await self.enter(fourth, type="join", room=code, name="D"))["type"], "error")
            await third.close()
            await self.read_until(first, lambda e: e["type"] == "players" and not e["players"][-1]["online"])
            self.assertEqual(
                [p["name"] for p in (await self.enter(fourth, type="join", room=code, name="D"))["room"]["players"]],
                ["A", "D"],
            )

            # With every room taken, an abandoned one is reclaimed for a new room.
            await second.close()
            fifth = await self.connect()
            async with asyncio.timeout(5):
                while (await self.enter(fifth, type="create", name="E"))["type"] == "error":
                    await asyncio.sleep(0.01)

    def test_clean_inputs(self):
        self.assertEqual(clean_name(None), "Player")
        self.assertEqual(clean_name("   "), "Player")
        self.assertEqual(len(clean_name("x" * 100)), 32)
        self.assertEqual(clean_portrait("0f" * 512), "0f" * 512)
        self.assertIsNone(clean_portrait("0g" * 512))
        self.assertIsNone(clean_portrait("0" * 1025))
        self.assertIsNone(clean_portrait(None))
