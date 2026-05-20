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

If character dialogue falls back to regular bot messages with a `Missing
Permissions` warning, check the bot's effective permissions in the game category
and channels. Updating the app's install settings does not always update an
already-installed bot; re-authorize/reinvite it, and make sure category or
channel permission overwrites are not denying `Manage Webhooks`.

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

When a game finishes normally or is stopped with `/stop`, the bot posts a final
cleanup menu in the last story channel. Choosing **Delete game channels**
deletes the channels used by that game session; choosing **Keep channels**
leaves the transcript in place. If nobody answers, the cleanup prompt times out
and keeps the channels. Starting a new game cancels any unresolved cleanup
prompt from the previous session.

Each accepted `/start` gets a fresh run id. Discord channel topics include that
run id, so replaying a game creates a new set of channels instead of reusing
kept transcript channels from an earlier run.

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
