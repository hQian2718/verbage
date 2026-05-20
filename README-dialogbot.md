# Dialog Bot MVP

This repo now includes a Python `discord.py` bot that loads every `*.script`
file in `game/` and starts at `main.setup`.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` values:

```sh
DISCORD_TOKEN=...
GUILD_ID=...
GAME_CATEGORY_NAME=Dialog Game
GAME_CHANNEL_TOPIC=Dialog bot game channel
```

The bot needs these Discord permissions:

- Send Messages
- Manage Channels
- Manage Webhooks
- Read Message History
- Manage Messages, for `clear channel`

Enable Message Content Intent in the Discord Developer Portal for `input()`.

## Run

```sh
python bot.py
```

Commands are guild-scoped when `GUILD_ID` is set:

- `/start`
- `/stop`
- `/reload`
- `/status`

Game state is in memory for the MVP.

## Local Testing Surface

The script runtime is isolated from Discord behind `DialogIO` in
`dialogbot/io.py`.

- `dialogbot/discord_io.py` adapts the runtime to Discord channels, webhooks,
  buttons, menus, and message waits.
- `dialogbot/local_io.py` is a local adapter for tests. It writes JSONL
  transcripts per channel and accepts queued button/menu/input events.

Run local tests with:

```sh
python3 -m unittest discover -s tests
```

## Maintainer Docs

- [Architecture](docs/architecture.md) explains the module layout and adapter
  boundary.
- [Runtime Semantics](docs/runtime-semantics.md) explains labels, jumps, run,
  menus, buttons, variables, and expression evaluation from the implementer's
  point of view.
- [Local Testing](docs/local-testing.md) explains how to test scripts and
  runtime behavior without Discord.
