# Verbage

Verbage is a Discord bot for telling interactive stories and running small
games inside a Discord server. Writers describe the story in a Ren'Py-inspired
`.script` language, and players experience it through Discord messages,
character webhooks, buttons, menus, typed responses, images, and multiple text
channels.

If you have used Twine or Ren'Py, the basic loop will feel familiar: write a
script, check it for errors, run `/start`, and let players choose their way
through the story. Verbage's twist is that Discord is the stage. A scene can
happen in one channel, several players can split up into different rooms, and
the resulting channels become a readable transcript of the path they took.

Use Verbage when you want to:

- Write interactive fiction and text game experiences that is
  played where your players already talk.
- Run multiplayer scenes, showing different conversations at
  the same time.
- Use Discord-native interactions to drive the story.
- All while keeping an author-first workflow: 
    - easy-to-learn syntax, 
    - image assets, 
    - local validation, 
    - and repeatable tests.

The default game directory is `game/`. The bot loads every `*.script` file there
and starts at `label setup:` in `main.script`. For an author-facing walkthrough,
see [tutorial.md](tutorial.md). For implementation semantics, see
[docs/runtime-semantics.md](docs/runtime-semantics.md).

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Create `.env` values:

```sh
DISCORD_TOKEN=...
GAME_DIR=game
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

## Running

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

Game state is currently stored in memory.

Each server gets its own active game session. A restart drops in-memory sessions
for all servers, but existing Discord channels and transcripts remain.



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

Run the local checker to validate your scripts:

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
## Extending the Syntax of Verbage Scripts

When adding a new script statement or command, keep the language pipeline in
sync from parser to Discord adapter. A good small change touches these places:

1. Add or update a statement dataclass in `dialogbot/model.py`.
   Keep it dependency-light; this is the parsed AST shape.

2. Parse the syntax in `dialogbot/parser.py`.
   Most command entry points start in `Parser.parse_statement()`. Add a focused
   parser method, emit helpful load-time errors, and update
   `validate_statements()` for references, interpolation, labels, variables, or
   assets that can be checked before the game starts.

3. Execute the statement in `dialogbot/runtime.py`.
   Add a branch in `GameSession.execute_statement()`. Runtime code should speak
   only in script concepts such as channels, labels, variables, and user
   actions.

4. Extend `DialogIO` only if the command needs a new kind of external IO.
   Add the protocol method in `dialogbot/io.py`, then implement it in both
   `dialogbot/discord_io.py` and `dialogbot/local_io.py`. The local adapter is
   what makes the feature testable without Discord.

5. Update helper tools.
   If the new statement affects timing or control flow, update `estimate.py`.
   Make sure `check.py` catches broken scripts through parser validation rather
   than letting failures happen during `/start`.

6. Add focused tests in `tests/test_scripts.py`.
   Prefer small inline scripts using `LocalDialogIO`. Test the happy path and at
   least one useful author error. If the feature affects Discord-only behavior,
   keep the runtime behavior behind `DialogIO` and assert against local events.

7. Document the syntax.
   Update [docs/runtime-semantics.md](docs/runtime-semantics.md) for
   implementers and [tutorial.md](tutorial.md) or
   `game_example/language_proposal.md` for writers.

8. Run the checks:

```sh
python3 -m unittest discover -s tests
python3 check.py game
python3 check.py game_example
python3 -m py_compile bot.py dialogbot/*.py
```

Recent examples to copy from:

- `show image "asset"` added a model node, parser validation, runtime dispatch,
  Discord/local adapter output, estimator handling, tests, and docs.
- Menu option interpolation reused existing dialogue interpolation, so it only
  needed runtime rendering, parser validation, tests, and docs.

## Maintainer Docs

- [Architecture](docs/architecture.md) explains the module layout and adapter
  boundary.
- [Runtime Semantics](docs/runtime-semantics.md) explains labels, jumps, run,
  menus, buttons, variables, and expression evaluation from the implementer's
  point of view.
- [Local Testing](docs/local-testing.md) explains how to test scripts and
  runtime behavior without Discord.
- [Deployment](docs/deployment.md) shows an example of how to deploy Verbage to
  a virtual machine so that it runs persistently. 
