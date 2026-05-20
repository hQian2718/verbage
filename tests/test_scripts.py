import asyncio
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from dialogbot.expressions import eval_condition, validate_condition
from dialogbot.local_io import LocalDialogIO
from dialogbot.parser import load_game
from dialogbot.runtime import GameSession


class FakeContext:
    def __init__(self, text="") -> None:
        self.text = text
        self.variables = {"answer": text}

    async def get_var(self, name):
        return self.variables[name]

    async def set_var(self, name, value):
        self.variables[name] = value

    async def wait_for_input(self):
        return self.text

    def username(self):
        return "tester"


class ScriptTests(unittest.IsolatedAsyncioTestCase):
    def test_sample_scripts_load(self):
        game = load_game("game")
        self.assertIn(("main", "setup"), game.labels)
        self.assertIn(("interior", "restroom_2"), game.labels)

    async def test_contains_sugar_with_input(self):
        expression = 'input() contains "portrait" or "winnie" or "investigate"'
        validate_condition(expression, {})
        self.assertTrue(await eval_condition(expression, FakeContext("look at portrait")))
        self.assertTrue(await eval_condition(expression, FakeContext("WINNIE")))
        self.assertFalse(await eval_condition(expression, FakeContext("wash hands")))

    async def test_contains_sugar_with_variable(self):
        expression = 'answer contains "dead" or "beef"'
        validate_condition(expression, {"answer": ""})
        self.assertTrue(await eval_condition(expression, FakeContext("dead beef")))
        self.assertFalse(await eval_condition(expression, FakeContext("nothing")))

    async def test_runtime_can_run_against_local_io(self):
        script = '''
define n = Character(
    "Narrator",
    color="#0d5c16",
    image="narrator",
)

default clicker = ""
default answer = ""

label setup:
    jump start

label start(channel="Room"):
    n "Welcome."
    button "Look":
        $ clicker = username()
    n "$clicker looked."
    $ answer = input()
    if answer contains "portrait" or "winnie":
        "Found it."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = LocalDialogIO(output_dir)
            io.queue_button("Room", "Look", "Alice", "alice")
            io.queue_input("Room", "inspect the portrait")
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 0

            await session.run_root()

            self.assertEqual(session.variables["clicker"], "Alice")
            self.assertEqual(session.variables["answer"], "inspect the portrait")
            self.assertTrue((output_dir / "room.jsonl").exists())
            self.assertIn(
                ("narration", "Found it."),
                [(event["kind"], event["text"]) for event in io.events],
            )

    async def test_menu_clicks_are_adapter_driven(self):
        script = '''
default picker = ""

label setup:
    jump start

label start(channel="Room"):
    menu:
        "Choose":
            $ picker = username()
            jump done

label done(channel="Room"):
    "Done."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = LocalDialogIO(output_dir)
            io.queue_menu("Room", 0, "Bob", "bob")
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 0

            await session.run_root()

            self.assertEqual(session.variables["picker"], "Bob")
            self.assertEqual(
                ["menu", "menu_click", "menu_close"],
                [event["kind"] for event in io.events if event["kind"].startswith("menu")],
            )

    async def test_normal_completion_can_delete_game_channels(self):
        script = '''
label setup:
    jump done

label done(channel="Room"):
    "Done."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = LocalDialogIO(output_dir)
            io.queue_menu("Room", 0, "Alice", "alice")
            session = GameSession(io, game, cleanup_prompt_enabled=True)
            session.min_delay = 0
            session.max_delay = 0

            await session.run_root()

            event_kinds = [event["kind"] for event in io.events]
            self.assertIn("delete", event_kinds)
            self.assertFalse((output_dir / "room.jsonl").exists())

    async def test_real_game_end_to_end_opens_secret_door(self):
        with TemporaryDirectory() as raw_dir:
            output_dir = Path("./output") / "out"
            game = load_game("game")
            io = LocalDialogIO(output_dir)

            io.queue_menu("Entrance", 1, "Alice", "alice")
            io.queue_input("Entrance", "dead beef")
            io.queue_menu("Entrance", 0, "Alice", "alice")
            io.queue_menu("Entrance", 0, "Bob", "bob")

            io.queue_button("Kitchen", "Look around", "Carol", "carol")
            io.queue_button("Restroom", "Look around", "Alice", "alice")
            io.queue_button("Banquet Hall", "Look around", "Bob", "bob")

            io.queue_input("Restroom", "I investigate the Winnie portrait.")
            io.queue_button("Restroom", "press it", "Alice", "alice")
            io.queue_button("Banquet Hall", "Inspect the door", "Bob", "bob")

            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 0
            session.wait_scale = 0

            await asyncio.wait_for(session.run_root(), timeout=2)

            self.assertTrue(session.done)
            self.assertFalse(session.variables["door_locked"])
            self.assertEqual(session.variables["code_entered"], "dead beef")
            self.assertEqual(session.variables["enter_count"], session.variables["num_players"])
            self.assertEqual(session.variables["kitchen_investigator"], "Carol")
            self.assertFalse(session.variables["secret_door_locked"])

            events = [(event["channel"], event["kind"], event["text"]) for event in io.events]
            self.assertIn(("Banquet Hall", "narration", "YOU WIN!"), events)
            self.assertIn(("Great Hall", "dialogue", "End of the game."), events)
            self.assertTrue((output_dir / "entrance.jsonl").exists())
            self.assertTrue((output_dir / "banquet-hall.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
