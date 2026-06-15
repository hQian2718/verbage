<!--
Copyright (C) 2026 Kuan Qian
SPDX-License-Identifier: GPL-3.0-only
-->

# Local Testing

The project can test parser and runtime behavior without Discord by using
`LocalDialogIO`.

Run the current suite:

```sh
python3 -m unittest discover -s tests
```

## What LocalDialogIO Does

`LocalDialogIO` implements the same `DialogIO` protocol as the Discord adapter.
It keeps an in-memory event list and writes one JSONL transcript per script
channel.

For channel `"Room"`, output goes to:

```text
room.jsonl
```

Each line is a JSON object such as:

```json
{"channel": "Room", "kind": "dialogue", "speaker": "Narrator", "text": "Welcome."}
```

## Supplying Inputs

Tests queue player actions before running the session.

Text input:

```python
io.queue_input("Room", "inspect the portrait")
```

If the script uses `input("prompt")`, the local adapter records an
`input_prompt` event before `input_wait`.

Button click:

```python
io.queue_button("Room", "Look", "Alice", "alice")
```

Menu click:

```python
io.queue_menu("Room", 0, "Bob", "bob")
```

The menu index is the original option index in the parsed menu, not necessarily
the visible-list position after conditions are filtered.

## Minimal Local Runtime Test

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from dialogbot.local_io import LocalDialogIO
from dialogbot.parser import load_game
from dialogbot.runtime import GameSession


async def run_script():
    with TemporaryDirectory() as raw_dir:
        root = Path(raw_dir)
        game_dir = root / "game"
        out_dir = root / "out"
        game_dir.mkdir()
        (game_dir / "main.script").write_text("""
default answer = ""

label setup:
    jump start

label start(channel="Room"):
    $ answer = input("What do you inspect?")
    if answer contains "portrait":
        "Found it."
""")

        game = load_game(game_dir)
        io = LocalDialogIO(out_dir)
        io.queue_input("Room", "look at portrait")

        session = GameSession(io, game)
        session.min_delay = 0
        session.max_delay = 0
        await session.run_root()

        assert session.variables["answer"] == "look at portrait"
```

## Testing Guidelines

- Use small inline scripts for focused runtime behavior.
- Set `session.min_delay = 0` and `session.max_delay = 0` to avoid waiting for
  typing delays.
- Assert on `session.variables` for state changes.
- Assert on `io.events` for transcript behavior.
- Use `LocalDialogIO(out_dir, message_timestamps=True)` when debugging pacing.
  Timestamped events include `sent_at` and `sent_at_monotonic`, so tests can
  assert gaps between local sends without parsing wall-clock text.
- Use `load_game("game")` in smoke tests to ensure the real sample game still
  parses.
- For end-to-end tests against the real game, set `session.wait_scale = 0` so
  script-level waits such as `wait 5` do not slow the suite down.
- Direct `GameSession` tests do not show the final cleanup prompt unless you
  construct the session with `cleanup_prompt_enabled=True`; queue a final menu
  click if you enable it.
- Set `session.cleanup_prompt_timeout` low in tests when you want to verify that
  the cleanup prompt defaults to keeping channels.

## Common Failure Modes

- A test hangs when a script waits for input/button/menu and no queued action is
  available.
- A menu click index points at an option that was omitted by a condition.
- A local script emits dialogue before any label has bound a channel.
- A script jumps into a label already active in the same channel, causing a
  channel conflict.
