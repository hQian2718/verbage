import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dialogbot.config import GameConfig
from estimate import estimate_label
from dialogbot.parser import load_game


class EstimateTests(unittest.TestCase):
    def test_estimates_dialogue_and_wait_with_runtime_config(self):
        script = '''
label setup:
    jump start

label start(channel="Room"):
    "12345"
    wait 2
    "1234567890"
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            config = GameConfig(
                delay_per_char=0.1,
                min_delay=0,
                max_delay=10,
                typing_delay=0.25,
                wait_scale=0.5,
                cleanup_prompt_timeout=120,
            )
            estimate = estimate_label(game.labels[("main", "start")], config)

            self.assertAlmostEqual(3.0, estimate.seconds)
            self.assertEqual(["dialogue", "wait", "dialogue"], [step.kind for step in estimate.steps])
            self.assertEqual([], estimate.notes)

    def test_stops_at_branch_and_adds_note(self):
        script = '''
label setup:
    jump start

label start(channel="Room"):
    "Before."
    menu:
        "Choice":
            "Inside."
    "After."
'''
        with TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            game_dir = root / "game"
            game_dir.mkdir()
            (game_dir / "main.script").write_text(script)

            game = load_game(game_dir)
            config = GameConfig(
                delay_per_char=0.1,
                min_delay=0,
                max_delay=10,
                typing_delay=0,
                wait_scale=1,
                cleanup_prompt_timeout=120,
            )
            estimate = estimate_label(game.labels[("main", "start")], config)

            self.assertAlmostEqual(0.7, estimate.seconds)
            self.assertEqual(1, len(estimate.steps))
            self.assertIn("menu branches", estimate.notes[0])


if __name__ == "__main__":
    unittest.main()
