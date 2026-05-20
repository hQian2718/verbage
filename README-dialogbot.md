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
