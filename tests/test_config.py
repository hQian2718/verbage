# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

import os
import unittest
from unittest.mock import patch

from dialogbot.config import GameConfig


class GameConfigTests(unittest.TestCase):
    def test_from_env_reads_runtime_timing_values(self):
        with patch.dict(
            os.environ,
            {
                "DIALOG_DELAY_PER_CHAR": "0.08",
                "DIALOG_MIN_DELAY": "2",
                "DIALOG_MAX_DELAY": "6",
                "DIALOG_TYPING_DELAY": "0.25",
                "DIALOG_WAIT_SCALE": "0.5",
                "DIALOG_CLEANUP_TIMEOUT": "9",
                "GAME_DEFAULT_CHANNEL": "Lobby",
            },
        ):
            config = GameConfig.from_env()

        self.assertEqual(0.08, config.delay_per_char)
        self.assertEqual(2, config.min_delay)
        self.assertEqual(6, config.max_delay)
        self.assertEqual(0.25, config.typing_delay)
        self.assertEqual(0.5, config.wait_scale)
        self.assertEqual(9, config.cleanup_prompt_timeout)
        self.assertEqual("Lobby", config.default_channel)
        self.assertEqual(2, config.reading_delay_for("short"))
        self.assertEqual(6, config.reading_delay_for("x" * 100))
        self.assertEqual(2.25, config.dialogue_seconds("short"))

    def test_from_env_uses_fallback_default_channel_for_blank_value(self):
        with patch.dict(os.environ, {"GAME_DEFAULT_CHANNEL": "   "}):
            config = GameConfig.from_env()

        self.assertEqual("Game", config.default_channel)


if __name__ == "__main__":
    unittest.main()
