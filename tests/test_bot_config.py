# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

import os
import unittest
from unittest.mock import patch

from dialogbot.config import get_optional_int_env


class BotConfigTests(unittest.TestCase):
    def test_get_optional_int_env_ignores_blank_values(self):
        with patch.dict(os.environ, {"DEV_GUILD_ID": "   "}):
            self.assertIsNone(get_optional_int_env("DEV_GUILD_ID"))

    def test_get_optional_int_env_parses_discord_id(self):
        with patch.dict(os.environ, {"DEV_GUILD_ID": "123456789"}):
            self.assertEqual(123456789, get_optional_int_env("DEV_GUILD_ID"))

    def test_get_optional_int_env_rejects_non_integer(self):
        with patch.dict(os.environ, {"DEV_GUILD_ID": "not-a-server-id"}):
            with self.assertRaisesRegex(RuntimeError, "DEV_GUILD_ID"):
                get_optional_int_env("DEV_GUILD_ID")


if __name__ == "__main__":
    unittest.main()
