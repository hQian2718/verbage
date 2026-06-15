import asyncio
import contextlib
import time
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from dialogbot.config import GameConfig
from dialogbot.expressions import eval_condition, validate_condition
from dialogbot.local_io import LocalDialogIO
from dialogbot.parser import ScriptLoadError, load_game
from dialogbot.runtime import GameManager, GameSession

try:
    from dialogbot.discord_io import DiscordDialogIO
except ModuleNotFoundError:
    DiscordDialogIO = None


class FakeContext:
    def __init__(self, text="") -> None:
        self.text = text
        self.variables = {"answer": text}

    async def get_var(self, name):
        return self.variables[name]

    async def set_var(self, name, value):
        self.variables[name] = value

    async def wait_for_input(self, prompt=None):
        return self.text

    def username(self):
        return "tester"


class NoSleepTypingLocalIO(LocalDialogIO):
    async def typing_pause(self, channel_name: str, seconds: float) -> None:
        await self.record(channel_name, "typing", f"{seconds:.3f}s")


class ScriptTests(unittest.IsolatedAsyncioTestCase):
    def test_sample_scripts_load(self):
        game = load_game("game")
        self.assertIn(("main", "setup"), game.labels)
        self.assertIn(("main", "ask_all_ready"), game.labels)
        self.assertIn(("act_1", "begin"), game.labels)
        self.assertIn(("act_1", "quiz_1"), game.labels)

    async def test_contains_sugar_with_input(self):
        expression = 'input() contains "portrait" or "winnie" or "investigate"'
        validate_condition(expression, {})
        self.assertTrue(await eval_condition(expression, FakeContext("look at portrait")))
        self.assertTrue(await eval_condition(expression, FakeContext("WINNIE")))
        self.assertFalse(await eval_condition(expression, FakeContext("wash hands")))

        prompted = 'input("What do you inspect?") contains "portrait"'
        validate_condition(prompted, {})
        self.assertTrue(await eval_condition(prompted, FakeContext("portrait")))

    async def test_contains_sugar_with_variable(self):
        expression = 'answer contains "dead" or "beef"'
        validate_condition(expression, {"answer": ""})
        self.assertTrue(await eval_condition(expression, FakeContext("dead beef")))
        self.assertFalse(await eval_condition(expression, FakeContext("nothing")))

    async def test_discord_channel_topics_are_session_scoped(self):
        if DiscordDialogIO is None:
            self.skipTest("discord.py is not installed")
        io = DiscordDialogIO(object(), object())
        io.channel_topic_base = "Dialog"

        self.assertEqual("Dialog: Room", io.channel_topic("Room"))
        await io.prepare_session("run-one")
        self.assertEqual("Dialog [run-one]: Room", io.channel_topic("Room"))
        await io.prepare_session("run-two")
        self.assertEqual("Dialog [run-two]: Room", io.channel_topic("Room"))

    def test_character_image_defaults_to_key(self):
        script = '''
define n = Character(
    "Narrator",
    color="#0d5c16",
)

label setup:
    jump start

label start(channel="Room"):
    n "Welcome."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)

            self.assertEqual("n", game.characters["n"].image)
            self.assertIsNone(game.characters["n"].image_path)

    def test_invalid_label_error_skips_body_cascade(self):
        script = '''
define n = Character(
    "Narrator",
    color="#0d5c16",
)

label setup:
    jump start

label start(Channel="Room"):
    n "This body should not produce top-level errors."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            with self.assertRaises(ScriptLoadError) as raised:
                load_game(game_dir)

            message = str(raised.exception)
            self.assertIn("use lowercase channel=", message)
            self.assertNotIn("top-level statement must not be indented", message)
            self.assertNotIn("unknown character n", message)

    async def test_label_without_channel_uses_config_default_channel(self):
        script = '''
define n = Character(
    "Narrator",
    color="#0d5c16",
)

label setup:
    jump start

label start:
    n "Welcome."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = NoSleepTypingLocalIO(root / "out")
            session = GameSession(
                io,
                game,
                config=GameConfig(
                    delay_per_char=0,
                    min_delay=0,
                    max_delay=0,
                    typing_delay=0,
                    wait_scale=1,
                    cleanup_prompt_timeout=120,
                    default_channel="Lobby",
                ),
            )

            await session.run_root()

        events = [(event["channel"], event["kind"], event["text"]) for event in io.events]
        self.assertIn(("Lobby", "channel", "created"), events)
        self.assertIn(("Lobby", "dialogue", "Welcome."), events)

    def test_file_parse_errors_keep_valid_definitions(self):
        script = '''
define n = Character(
    "Narrator",
    color="#0d5c16",
)

define bad = Character(
    "Broken",
    color=123,
)

label setup:
    jump start

label start(channel="Room"):
    n "This character should still be known."
    bad "This character should still fail."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            with self.assertRaises(ScriptLoadError) as raised:
                load_game(game_dir)

            message = str(raised.exception)
            self.assertIn("Character name, color, and image must be strings", message)
            self.assertIn("unknown character bad", message)
            self.assertNotIn("unknown character n", message)

    def test_characters_load_before_labels_across_files(self):
        main_script = '''
label setup:
    jump start

label start(channel="Room"):
    n "Welcome."
'''
        character_script = '''
define n = Character(
    "Narrator",
    color="#0d5c16",
)
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(main_script)
            (game_dir / "zz_characters.script").write_text(character_script)

            game = load_game(game_dir)

            self.assertIn("n", game.characters)
            self.assertIn(("main", "start"), game.labels)

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
    channel link "Go outside" to "Outside"
    button "Look":
        $ clicker = username()
    n "$clicker looked."
    $ answer = input("What do you inspect?")
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
                ("channel_link", "Go outside", "Outside"),
                [(event["kind"], event["text"], event.get("target")) for event in io.events],
            )
            self.assertIn(
                ("input_prompt", "What do you inspect?"),
                [(event["kind"], event["text"]) for event in io.events],
            )
            self.assertIn(
                ("narration", "Found it."),
                [(event["kind"], event["text"]) for event in io.events],
            )

    async def test_dialogue_before_jump_waits_after_message(self):
        script = '''
default arrived = False

label setup:
    jump start

label start(channel="Room"):
    "Read this before jumping."
    jump done

label done(channel="Room"):
    $ arrived = True
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = NoSleepTypingLocalIO(output_dir)
            session = GameSession(io, game)
            session.min_delay = 0.02
            session.max_delay = 0.02

            started = time.monotonic()
            await session.run_root()
            elapsed = time.monotonic() - started

            self.assertTrue(session.variables["arrived"])
            self.assertGreaterEqual(elapsed, 0.02)

    async def test_empty_dialogue_is_silent(self):
        script = '''
define n = Character(
    "Narrator",
    color="#0d5c16",
)

label setup:
    jump start

label start(channel="Room"):
    n ""
    n "After."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = NoSleepTypingLocalIO(output_dir)
            session = GameSession(
                io,
                game,
                config=GameConfig(
                    delay_per_char=0,
                    min_delay=0,
                    max_delay=0,
                    typing_delay=0,
                    wait_scale=1,
                    cleanup_prompt_timeout=120,
                ),
            )

            await session.run_root()

            dialogue = [(event["kind"], event["text"]) for event in io.events if event["kind"] == "dialogue"]
            self.assertEqual([("dialogue", "After.")], dialogue)

    async def test_show_image_url_records_local_event(self):
        script = '''
default room_name = "Entrance"

label setup:
    jump start

label start(channel="Room"):
    show image "https://example.com/door.png":
        caption "The $room_name door."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = LocalDialogIO(output_dir)
            session = GameSession(io, game)

            await session.run_root()

            image_events = [event for event in io.events if event["kind"] == "image"]
            self.assertEqual(1, len(image_events))
            self.assertEqual("The Entrance door.", image_events[0]["text"])
            self.assertEqual("https://example.com/door.png", image_events[0]["source"])
            self.assertIsNone(image_events[0]["path"])

    async def test_show_image_local_asset_records_resolved_path(self):
        script = '''
label setup:
    jump start

label start(channel="Room"):
    show image "door":
        caption "The locked door."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            images_dir = game_dir / "images"
            output_dir = root / "out"
            images_dir.mkdir(parents=True)
            (images_dir / "door.png").write_bytes(b"fake image bytes")
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = LocalDialogIO(output_dir)
            session = GameSession(io, game)

            await session.run_root()

            image_events = [event for event in io.events if event["kind"] == "image"]
            self.assertEqual(1, len(image_events))
            self.assertEqual("door", image_events[0]["source"])
            self.assertEqual(str(images_dir / "door.png"), image_events[0]["path"])

    def test_show_image_missing_local_asset_is_load_error(self):
        script = '''
label setup:
    show image "missing"
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            with self.assertRaises(ScriptLoadError) as raised:
                load_game(game_dir)

            self.assertIn("image 'missing' not found", str(raised.exception))

    async def test_each_dialogue_line_gets_own_reading_delay(self):
        script = '''
default arrived = False

label setup:
    jump start

label start(channel="Room"):
    "short"
    "a much longer line"
    $ arrived = True
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = NoSleepTypingLocalIO(output_dir)
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 1
            session.delay_per_char = 0.001
            session.typing_delay = 0

            started = time.monotonic()
            await session.run_root()
            elapsed = time.monotonic() - started

            self.assertTrue(session.variables["arrived"])
            self.assertGreaterEqual(elapsed, 0.022)

    async def test_local_timestamps_show_per_line_reading_gaps(self):
        script = '''
label setup:
    jump start

label start(channel="Room"):
    "12345"
    "1234567890"
    "done"
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = NoSleepTypingLocalIO(output_dir, message_timestamps=True)
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 1
            session.delay_per_char = 0.003
            session.typing_delay = 0

            await session.run_root()

            narration_events = [event for event in io.events if event["kind"] == "narration"]
            self.assertEqual(3, len(narration_events))
            self.assertIn("`sent ", narration_events[0]["text"])
            first_gap = narration_events[1]["sent_at_monotonic"] - narration_events[0]["sent_at_monotonic"]
            second_gap = narration_events[2]["sent_at_monotonic"] - narration_events[1]["sent_at_monotonic"]
            self.assertGreaterEqual(first_gap, 5 * session.delay_per_char)
            self.assertGreaterEqual(second_gap, 10 * session.delay_per_char)

    async def test_persistent_menu_clicks_are_adapter_driven(self):
        script = '''
default picker = ""

label setup:
    jump start

label start(channel="Room"):
    persistent menu:
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

    async def test_menu_resumes_after_option_without_continue(self):
        script = '''
default picker = ""
default after_menu = False

label setup:
    jump start

label start(channel="Room"):
    menu:
        "Choose":
            $ picker = username()
    $ after_menu = True
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
            self.assertTrue(session.variables["after_menu"])
            self.assertEqual(
                ["menu", "menu_click", "menu_close"],
                [event["kind"] for event in io.events if event["kind"].startswith("menu")],
            )
            self.assertIn(
                ("narration", "Done."),
                [(event["kind"], event["text"]) for event in io.events],
            )

    async def test_menu_option_text_interpolates_variables(self):
        script = '''
default dish = "Vegetarian Goose"
default npc_name = "Jia Li"
default picked = False

label setup:
    jump start

label start(channel="Room"):
    menu:
        "Serve $dish":
            $ picked = True
        "Talk to $(npc_name)":
            $ picked = True
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
            session = GameSession(io, game)

            await session.run_root()

            self.assertTrue(session.variables["picked"])
            self.assertIn(
                ("menu", "0:Serve Vegetarian Goose | 1:Talk to Jia Li"),
                [(event["kind"], event["text"]) for event in io.events],
            )

    def test_menu_option_text_validates_interpolation(self):
        script = '''
label setup:
    menu:
        "Serve $missing":
            "Done."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            with self.assertRaises(ScriptLoadError) as raised:
                load_game(game_dir)

            self.assertIn("unknown variable missing", str(raised.exception))

    async def test_persistent_menu_keeps_waiting_after_option_without_continue(self):
        script = '''
default clicks = 0

label setup:
    jump start

label start(channel="Room"):
    persistent menu:
        "Choose":
            $ clicks += 1
            if clicks == 2:
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
            io.queue_menu("Room", 0, "Bob", "bob")
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 0

            await session.run_root()

            self.assertEqual(2, session.variables["clicks"])
            self.assertEqual(
                ["menu", "menu_click", "menu_click", "menu_close"],
                [event["kind"] for event in io.events if event["kind"].startswith("menu")],
            )

    async def test_menu_with_no_visible_options_logs_and_continues(self):
        script = '''
default door_locked = False
default after_menu = False

label setup:
    jump start

label start(channel="Room"):
    menu:
        "Enter a code" if door_locked:
            "Hidden."
    $ after_menu = True
    "After."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = LocalDialogIO(output_dir)
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 0

            with self.assertLogs("dialogbot.runtime", level="DEBUG") as logs:
                await session.run_root()

            self.assertTrue(session.variables["after_menu"])
            self.assertNotIn("menu", [event["kind"] for event in io.events])
            self.assertIn(("narration", "After."), [(event["kind"], event["text"]) for event in io.events])
            self.assertIn("Skipping menu with no visible options", "\n".join(logs.output))

    def test_continue_outside_menu_is_invalid(self):
        script = '''
label setup:
    continue
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            with self.assertRaises(ScriptLoadError) as raised:
                load_game(game_dir)

            self.assertIn("continue can only be used inside a menu option", str(raised.exception))

    async def test_button_timeout_continues_after_button(self):
        script = '''
default clicked = False
default after_button = False

label setup:
    jump start

label start(channel="Room"):
    button "Wait" timeout 0.001:
        $ clicked = True
    $ after_button = True
    "After."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = LocalDialogIO(output_dir)
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 0

            await session.run_root()

            self.assertFalse(session.variables["clicked"])
            self.assertTrue(session.variables["after_button"])
            self.assertIn("button_timeout", [event["kind"] for event in io.events])
            self.assertIn(
                ("narration", "After."),
                [(event["kind"], event["text"]) for event in io.events],
            )

    async def test_button_click_before_timeout_runs_body(self):
        script = '''
default clicked = False
default clicker = ""

label setup:
    jump start

label start(channel="Room"):
    button "Wait" timeout 10:
        $ clicked = True
        $ clicker = username()
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = LocalDialogIO(output_dir)
            io.queue_button("Room", "Wait", "Alice", "alice")
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 0

            await session.run_root()

            self.assertTrue(session.variables["clicked"])
            self.assertEqual("Alice", session.variables["clicker"])
            event_kinds = [event["kind"] for event in io.events]
            self.assertIn("button_click", event_kinds)
            self.assertNotIn("button_timeout", event_kinds)

    async def test_timed_menu_runs_timeout_branch(self):
        script = '''
default timed_out = False

label setup:
    jump start

label start(channel="Room"):
    menu timeout 0.001:
        "Choose":
            jump done

        timeout:
            $ timed_out = True
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
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 0

            await session.run_root()

            self.assertTrue(session.variables["timed_out"])

    async def test_input_block_cases_store_and_match_text(self):
        script = '''
default answer = ""
default matched = False

label setup:
    jump start

label start(channel="Room"):
    input "What do you inspect?" into answer:
        case contains "portrait" or "winnie":
            $ matched = True
            jump done

        case _:
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
            io.queue_input("Room", "the portrait")
            session = GameSession(io, game)
            session.min_delay = 0
            session.max_delay = 0

            await session.run_root()

            self.assertEqual(session.variables["answer"], "the portrait")
            self.assertTrue(session.variables["matched"])

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
            self.assertIsNotNone(session.cleanup_task)
            await session.cleanup_task

            event_kinds = [event["kind"] for event in io.events]
            self.assertIn("delete", event_kinds)
            self.assertFalse((output_dir / "room.jsonl").exists())

    async def test_completion_cleanup_prompt_times_out_to_keep_channels(self):
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
            session = GameSession(io, game, cleanup_prompt_enabled=True)
            session.min_delay = 0
            session.max_delay = 0
            session.cleanup_prompt_timeout = 0.001

            await session.run_root()
            self.assertIsNotNone(session.cleanup_task)
            await session.cleanup_task

            event_kinds = [event["kind"] for event in io.events]
            self.assertNotIn("delete", event_kinds)
            self.assertIn(
                ("notice", "Keeping game channels."),
                [(event["kind"], event["text"]) for event in io.events],
            )
            self.assertTrue((output_dir / "room.jsonl").exists())

    async def test_manager_stop_posts_cleanup_prompt(self):
        script = '''
label setup:
    jump start

label start(channel="Room"):
    button "Wait"
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            output_dir = root / "out"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            io = LocalDialogIO(output_dir)
            manager = GameManager(cleanup_prompt_enabled=True)
            await manager.start(123, io, game)
            session = manager.sessions[123]

            for _ in range(100):
                if "Room" in session.known_channels:
                    break
                await asyncio.sleep(0.001)
            self.assertIn("Room", session.known_channels)

            io.queue_menu("Room", 0, "Alice", "alice")
            result = await manager.stop(123, "Stopped by test.")
            if session.root_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await session.root_task
            self.assertIsNotNone(session.cleanup_task)
            await session.cleanup_task

            self.assertEqual("Stopped the game. Cleanup prompt posted.", result)
            event_kinds = [event["kind"] for event in io.events]
            self.assertIn("button", event_kinds)
            self.assertIn("menu", event_kinds)
            self.assertIn("delete", event_kinds)
            self.assertFalse((output_dir / "room.jsonl").exists())

    async def test_manager_can_start_after_stop_with_pending_cleanup(self):
        script = '''
label setup:
    jump start

label start(channel="Room"):
    button "Wait"
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            first_output_dir = root / "out-first"
            second_output_dir = root / "out-second"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            manager = GameManager(cleanup_prompt_enabled=True)
            first_io = LocalDialogIO(first_output_dir)
            await manager.start(123, first_io, game)
            first_session = manager.sessions[123]
            self.assertIsNotNone(first_io.session_id)

            for _ in range(100):
                if "Room" in first_session.known_channels:
                    break
                await asyncio.sleep(0.001)
            self.assertIn("Room", first_session.known_channels)

            await manager.stop(123, "Stopped by test.")
            if first_session.root_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await first_session.root_task
            self.assertIsNotNone(first_session.cleanup_task)
            self.assertFalse(first_session.cleanup_task.done())

            second_io = LocalDialogIO(second_output_dir)
            result = await manager.start(123, second_io, game)
            second_session = manager.sessions[123]

            self.assertEqual("Starting the game.", result)
            self.assertIsNotNone(second_io.session_id)
            self.assertNotEqual(first_io.session_id, second_io.session_id)
            self.assertIsNot(first_session, second_session)
            self.assertTrue(first_session.cleanup_task.done())
            self.assertTrue(first_session.cleanup_task.cancelled())

            await second_session.stop("Test cleanup.", offer_cleanup=False)
            if second_session.root_task:
                with contextlib.suppress(asyncio.CancelledError):
                    await second_session.root_task

    async def test_manager_can_start_after_completion_with_pending_cleanup(self):
        script = '''
default finished = False

label setup:
    jump done

label done(channel="Room"):
    $ finished = True
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            first_output_dir = root / "out-first"
            second_output_dir = root / "out-second"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            manager = GameManager(cleanup_prompt_enabled=True)
            first_io = LocalDialogIO(first_output_dir)
            await manager.start(123, first_io, game)
            first_session = manager.sessions[123]
            self.assertIsNotNone(first_io.session_id)
            first_session.min_delay = 0
            first_session.max_delay = 0

            for _ in range(100):
                if first_session.done and first_session.cleanup_task:
                    break
                await asyncio.sleep(0.001)
            self.assertTrue(first_session.done)
            self.assertIsNotNone(first_session.cleanup_task)
            self.assertFalse(first_session.cleanup_task.done())

            second_io = LocalDialogIO(second_output_dir)
            result = await manager.start(123, second_io, game)
            second_session = manager.sessions[123]

            self.assertEqual("Starting the game.", result)
            self.assertIsNotNone(second_io.session_id)
            self.assertNotEqual(first_io.session_id, second_io.session_id)
            self.assertIsNot(first_session, second_session)
            self.assertTrue(first_session.cleanup_task.done())
            self.assertTrue(first_session.cleanup_task.cancelled())

            if second_session.root_task:
                await second_session.root_task
            self.assertIsNotNone(second_session.cleanup_task)
            await second_session.cancel_cleanup_prompt()

    async def test_real_game_end_to_end_opens_secret_door(self):
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            # The secret-door scenario is the bundled example game, not the
            # active game in ./game/.
            game_dir = Path("game_example")
            output_dir = root / "out"
            game = load_game(game_dir)
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
            session.typing_delay = 0
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
            self.assertEqual(
                3,
                len([event for event in io.events if event["kind"] == "channel_link" and event.get("target") == "Great Hall"]),
            )
            self.assertTrue((output_dir / "entrance.jsonl").exists())
            self.assertTrue((output_dir / "banquet-hall.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
