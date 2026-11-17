<!--
Copyright (C) 2026 Kuan Qian
SPDX-License-Identifier: GPL-3.0-only
-->

# Web Frontend

`web.py` serves the game to browsers, so people can play without Discord. It
runs the same scripts through the same runtime; only the IO adapter differs.

Players gather in rooms. On the landing page a player enters a name, may paint
a 32 x 32 pixel portrait (the same grid as the character art), and then creates
a room or joins one with its 4-letter code or invite link. Everyone in a room
shares one game: the same channels, the same menus, and a chat that all of them
can type in. One person can also play alone in a room of their own.

Script channels appear as a list, with an unread count per channel and a dot on
channels where the story is waiting for the player.

## Running Locally

```sh
pip install -e .
python web.py
```

Open <http://127.0.0.1:8080>. No Discord token is needed.

For a fast smoke test, shorten the reading delays:

```sh
python web.py --min-delay 0 --max-delay 0
```

Options and their environment variables:

| Flag | Variable | Default | Meaning |
| --- | --- | --- | --- |
| `--host` | `WEB_HOST` | `127.0.0.1` | Interface to bind. |
| `--port` | `WEB_PORT` | `8080` | Port to bind. |
| `--game-dir` | `WEB_GAME_DIR` | `game_web` | Script directory. |
| | `WEB_TITLE` | `Verbage` | Name shown on the page. |
| | `WEB_SESSION_IDLE_TIMEOUT` | `600` | Seconds a room survives with no browser attached. |

Two limits are hardcoded in `dialogbot/web_server.py` for now: `MAX_ROOMS = 20`
and `MAX_PLAYERS_PER_ROOM = 8`. When every room is taken, creating a room
reclaims the one that has had no browser attached the longest, and fails if
there is none.

To let other devices on your network join, bind every interface and share the
machine's address, for example `http://192.168.1.20:8080`:

```sh
python web.py --host 0.0.0.0
```

The `DIALOG_*` pacing variables and `GAME_DEFAULT_CHANNEL` apply as they do for
the Discord bot.

## How It Behaves

- Scripts are checked at startup; the server refuses to start on a load error.
  They are re-read whenever a game starts, and if an edit on disk is broken the
  server keeps using the last good copy and logs the error.
- Anyone in a room can start the game, end it, or start another one after it
  ends. People who join later drop into the game in progress.
- A browser remembers its seat in local storage. Reloading the page, or losing
  the connection, returns the player to the same seat with the full transcript.
  A player whose browser is gone is shown as away, and gives up the seat only
  if the room is full and someone else joins.
- Players can type in any channel at any time. A message answers `input` only
  if the script is waiting for one in that channel; otherwise it is chat.
- As on Discord, each player gets one click per menu showing, and `username()`
  is the player who last clicked or typed.
- A channel is listed once it has content, a link pointing at it, or a prompt.
- The web server reads `game_web/`, a copy of `game/` adapted for the browser,
  so the Discord bot's `GAME_DIR` is untouched. If a script declares
  `default num_players`, the server sets it to the number of connected players
  in the room when a game starts; `game_web` relies on that instead of asking.
- Timed menus and buttons show a bar that drains until the timeout.
- Names and portraits are kept in the browser. A portrait is sent as 1024 hex
  digits, one index into a fixed 16-colour palette per cell; the server checks
  only that shape.
- All rooms live in the memory of one process. Restarting the service ends
  every game in progress, and you cannot run several worker processes.

## Deploying to a VPS

This assumes the checkout from [deployment.md](deployment.md) at
`/opt/dialog-bot` with its `.venv`. The web service does not need
`DISCORD_TOKEN`, and it can run with or without the Discord bot service.

Install the service, changing `User=` to your VM user:

```sh
sudo cp deploy/verbage-web.service /etc/systemd/system/verbage-web.service
sudo nano /etc/systemd/system/verbage-web.service
sudo systemctl daemon-reload
sudo systemctl enable --now verbage-web
journalctl -u verbage-web -f
```

The service listens on `127.0.0.1:8080` only. Put a reverse proxy in front of
it for HTTPS. The proxy must pass websocket upgrades for `/ws`.

Caddy obtains certificates by itself and proxies websockets with no extra
configuration:

```caddy
play.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

nginx needs the upgrade headers:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 300s;
}
```

The page uses relative URLs, so it can also be served under a path such as
`https://example.com/play/`, as long as the proxy strips the prefix and the
address ends with a slash.

To redeploy both services with the deploy script:

```sh
SERVICE_NAME="dialog-bot verbage-web" deploy/deploy.sh
```

## Monitoring

`GET /healthz` returns `{"ok": true}` plus the current load: `uptime_seconds`,
`rooms`, `max_rooms`, `games_running`, `players`, `players_online`, and
`connections`.

The service logs to stderr, which `systemd` keeps in the journal:

```sh
journalctl -u verbage-web -f
journalctl -u verbage-web --since today | grep event=game_
```

Application lines carry an `event=` field followed by `key=value` pairs:

- `startup`, `shutdown`, `scripts_loaded`, `script_reload_failed`
- `room_created`, `room_closed` (with `reason=` empty, idle, reclaimed, or
  shutdown), `rooms_full`, `room_full`
- `player_joined`, `player_resumed`, `player_away`, `player_left`,
  `seat_reclaimed`
- `game_started`, `game_stopped` (a player ended it), `game_ended` (with
  `seconds=`)
- `stats`, the same numbers as `/healthz`, every five minutes while anyone is
  connected
- `handler_error`, with a traceback, if a browser message fails

Script runtime errors are logged by `dialogbot.runtime` with a traceback and
the error id shown to players. Chat text and menu choices are not logged.
HTTP requests are logged by `aiohttp.access`, with the proxy's
`X-Forwarded-For` address first. Set `LOG_LEVEL=WARNING` to keep only problems.

## Protocol

The browser and server exchange JSON over one websocket at `/ws`.

Browser to server:

- `{"type": "hello", "room": <code or null>, "token": <seat token or null>}`
  reclaims a seat if the room and token are still known.
- `{"type": "create", "name": "Ada", "portrait": <1024 hex digits or null>}`
- `{"type": "join", "room": "ABCD", "name": "Ada", "portrait": ...}`
- `{"type": "start"}` starts a game in the room, from the lobby or after one
  has ended.
- `{"type": "leave"}`
- `{"type": "say", "channel": "Room", "text": "..."}`
- `{"type": "button", "id": <item id>}`
- `{"type": "menu", "id": <item id>, "index": <option index>}`
- `{"type": "stop"}`

Server to browser:

- `welcome` carries the page title and either `room: null` or the whole room:
  code, this player's id and seat token, state (`lobby`, `running`, `ended`),
  the players, and every channel with its transcript items.
- `players` replaces the player list when someone joins, leaves, or goes away.
- `error` carries a message for the player, such as a full or unknown room.
- `channel`, `item`, `update`, `clear`, `remove_channel`, `awaiting`, `typing`,
  and `status` are incremental changes to that state.

`dialogbot/web_io.py` defines the item shapes. It has no HTTP dependency and is
tested directly in `tests/test_web.py`.
