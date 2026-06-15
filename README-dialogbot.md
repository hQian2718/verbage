# Dialog Bot MVP

This repo now includes a Python `discord.py` bot that loads every `*.script`
file in `game/` and starts at `main.setup`.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Create `.env` values:

```sh
DISCORD_TOKEN=...
GAME_CATEGORY_NAME=Dialog Game
GAME_CHANNEL_TOPIC=Dialog bot game channel
GAME_DEFAULT_CHANNEL=Game
```

Useful optional values:

```sh
DIALOG_MIN_DELAY=1.5
DIALOG_MAX_DELAY=6
DIALOG_TYPING_DELAY=0.5
DIALOG_MESSAGE_TIMESTAMPS=0
DISCORD_RETRY_ATTEMPTS=4
DISCORD_RETRY_BASE_DELAY=1
DEV_GUILD_ID=
```

The bot needs these Discord permissions:

- Send Messages
- Manage Channels
- Manage Webhooks
- Read Message History
- Manage Messages, for `clear channel`

Enable Message Content Intent in the Discord Developer Portal for `input()`.
Invite the bot with both the `bot` and `applications.commands` scopes. The
installed bot needs the permissions listed above in every server where it will
run.

If character dialogue falls back to regular bot messages with a `Missing
Permissions` warning, check the bot's effective permissions in the game category
and channels. Updating the app's install settings does not always update an
already-installed bot; re-authorize/reinvite it, and make sure category or
channel permission overwrites are not denying `Manage Webhooks`.

## Run

```sh
python bot.py
```

For fast Discord smoke tests, override reading delays for this process:

```sh
python bot.py --dialog-min-delay 0 --dialog-max-delay 0
```

Short aliases are also available:

```sh
python bot.py --min-delay 0 --max-delay 0
```

Dialogue pacing is a post-send reading delay. Each line computes its own delay
from `DIALOG_DELAY_PER_CHAR`, clamped by `DIALOG_MIN_DELAY` and
`DIALOG_MAX_DELAY`, so jumps/menus/buttons do not advance immediately after a
line appears. `DIALOG_TYPING_DELAY` only controls the short pre-send typing
indicator.

To debug real Discord timing, append the bot process's local send time to each
Discord message:

```sh
python bot.py --message-timestamps
```

This sets `DIALOG_MESSAGE_TIMESTAMPS=1` for the process. It stamps normal
messages, webhook character dialogue, prompts, and the otherwise-empty
button/menu/link messages.

Commands are registered globally by default, so the same running bot can be
installed in multiple Discord servers:

- `/start`
- `/stop`
- `/reload`
- `/status`

Global command updates can take time to appear in Discord. For fast smoke tests
in one development server, set `DEV_GUILD_ID` to that server id. When
`DEV_GUILD_ID` is set, command sync is limited to that one server for the
current bot process. Leave it blank or unset in production.

Game state is in memory for the MVP.

Each server gets its own active game session. A restart drops in-memory sessions
for all servers, but existing Discord channels and transcripts remain.

## Deploy on AWS Lightsail

Create an Ubuntu Lightsail instance, clone the repo, install dependencies, and
run the bot under `systemd`:

```sh
sudo apt update
sudo apt install -y git python3 python3-venv
sudo git clone <repo-url> /opt/dialog-bot
sudo chown -R ubuntu:ubuntu /opt/dialog-bot
cd /opt/dialog-bot
python3 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
nano .env
.venv/bin/python check.py
```

Copy `deploy/dialog-bot.service` to `/etc/systemd/system/dialog-bot.service`:

```sh
sudo cp deploy/dialog-bot.service /etc/systemd/system/dialog-bot.service
```

If the repo is not installed at `/opt/dialog-bot`, update `WorkingDirectory`,
`EnvironmentFile`, and `ExecStart` in the service file.

```sh
sudo systemctl daemon-reload
sudo systemctl enable dialog-bot
deploy/deploy.sh
journalctl -u dialog-bot -f
```

The bot only needs outbound network access to Discord; no public inbound
application port is required.

When a game finishes normally or is stopped with `/stop`, the bot posts a final
cleanup menu in the last story channel. Choosing **Delete game channels**
deletes the channels used by that game session; choosing **Keep channels**
leaves the transcript in place. If nobody answers, the cleanup prompt times out
and keeps the channels. Starting a new game cancels any unresolved cleanup
prompt from the previous session.

Each accepted `/start` gets a fresh run id. Discord channel topics include that
run id, so replaying a game creates a new set of channels instead of reusing
kept transcript channels from an earlier run.

Transient Discord 5xx responses are retried for channel/category creation and
outgoing sends. Permission errors and bad requests are not retried.

## Script Checking

Run the local checker before `/start` when editing scripts:

```sh
python3 check.py
python3 check.py game
```

Estimate straight-line timing for a label:

```sh
python3 estimate.py main.start
python3 estimate.py act_1.begin --game-dir game
```

The estimator uses the same timing environment variables as the runtime:
`DIALOG_DELAY_PER_CHAR`, `DIALOG_MIN_DELAY`, `DIALOG_MAX_DELAY`,
`DIALOG_TYPING_DELAY`, and `DIALOG_WAIT_SCALE`. It counts dialogue reading
delays and `wait` statements. When it reaches a branch, jump, `run`, menu,
button, input, or conditional, it prints a note instead of transitively
estimating that path.

The checker parses every `*.script` file, prints all parser/validation errors,
and exits nonzero when the scripts are invalid. The Discord `/start` and
`/reload` commands also log the full parser error server-side and send a short
summary back to Discord.

Characters may live in any `*.script` file. The loader first reads every
`define ... Character(...)` block across the whole game directory, then parses
defaults and labels, so `main.script` can safely reference characters from a
separate `characters.script`. Character `image=` is optional; when omitted, it
defaults to the character key, and missing image files simply mean no webhook
avatar is used.

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
