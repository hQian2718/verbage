<!--
Copyright (C) 2026 Kuan Qian
SPDX-License-Identifier: GPL-3.0-only
-->

# Architecture

This project has two layers:

- A script engine that parses and executes the `.script` language.
- IO adapters that connect the engine to Discord or to local test doubles.

The script engine should not import `discord.py`. If runtime behavior needs a
new Discord capability, add an operation to `DialogIO` first, implement it in
both adapters, then call the protocol from the runtime.

## Module Map

- `bot.py`
  - Discord process entrypoint.
  - Owns bot startup, slash command registration, and `.env` loading.
  - Creates a `DiscordDialogIO` per guild run and passes it to `GameManager`.

- `dialogbot/model.py`
  - Dataclasses for the parsed game model.
  - Includes `ScriptGame`, `Label`, character data, and statement AST nodes.
  - This module should remain dependency-light and safe to import in tests.

- `dialogbot/parser.py`
  - Loads all `game/*.script` files.
  - Converts indentation-based script text into the model dataclasses.
  - Performs load-time validation such as missing labels, unknown characters,
    undeclared variables, and unsafe expressions.

- `dialogbot/expressions.py`
  - Restricted expression evaluator.
  - Uses Python `ast` for the Python-like subset.
  - Handles script-only syntax such as `contains` before parsing with Python.

- `dialogbot/runtime.py`
  - Executes parsed statements.
  - Owns game sessions, variables, channel locks, fork-join `run`, `jump`
    control flow, timeout handling, and interpolation.
  - Talks only to the `DialogIO` protocol.

- `dialogbot/io.py`
  - Protocol boundary between the runtime and external IO.
  - Defines `DialogIO`, `UserAction`, `MenuChoice`, and `MenuHandle`.

- `dialogbot/discord_io.py`
  - Discord implementation of `DialogIO`.
  - Owns channel/category creation, webhooks, Discord buttons, Discord menus,
    message waits, typing indicators, and channel purging.

- `dialogbot/local_io.py`
  - Local implementation of `DialogIO`.
  - Writes JSONL transcripts and accepts queued inputs/clicks.
  - Used by unit tests and useful for future local harnesses.

- `tests/test_scripts.py`
  - Parser, expression, and local-runtime smoke tests.

## Control Flow

`GameManager` stores one active `GameSession` per scope id. In Discord, the
scope id is the guild id.

`GameSession.start()` creates a root task that enters `main.setup`. Labels with
no explicit `channel=` run in `GameConfig.default_channel`, which comes from
`GAME_DEFAULT_CHANNEL`.

Each running script path has an `EventContext`. A context tracks:

- Current namespace for bare label resolution.
- Current script channel name.
- Last interaction user for `username()` from a button, menu option, or text
  input.

All events in a session share one variable dictionary protected by an
`asyncio.Lock`.

## Adapter Boundary

The runtime sees channels as script channel names such as `"Entrance"` or
`"Kitchen"`. It never sees Discord channel ids, webhook ids, messages, views, or
members.

The adapter is responsible for translating runtime requests:

- `ensure_channel("Kitchen")`
- `send_character_dialogue("Kitchen", character, text)`
- `send_channel_link("Kitchen", "Return to Great Hall", "Great Hall")`
- `wait_for_button("Kitchen", "Look around")`
- `wait_for_input("Restroom", "What do you inspect?")`
- `clear_channel("Banquet Hall")`

This split makes the script language testable without a live bot and keeps
Discord API details from leaking into the interpreter.

## Adding A New Backend

Implement `DialogIO` from `dialogbot/io.py`.

Minimum behavior:

- Create or identify named channels.
- Emit narration, character dialogue, and notices.
- Wait for text input.
- Wait for button clicks.
- Open, wait on, and close menus.
- Clear a named channel.

Use `LocalDialogIO` as the simplest reference implementation.
