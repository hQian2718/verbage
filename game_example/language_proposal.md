# Script Language Reference

The bot interprets a Ren'Py-inspired script format. Every `.script` file inside `game/` is loaded at bot startup. The entry point is `label setup:` in `main.script`.

## File organization & namespacing

- All `*.script` files in `game/` are loaded at startup.
- A file's **namespace** is its filename stem. `interior.script` has namespace `interior`.
- **Labels** are scoped to their file's namespace.
- **Characters** and **variables** are global — defined in any file, visible everywhere.
- Character images resolve against `game/images/<basename>.{png,jpg,jpeg,gif,webp}` (first match wins).

## Comments

```
# Whole-line comment.
n "Hello"   # Trailing comment.
```

A `#` outside a string runs to end of line.

## Character definitions

```
define n = Character(
    "Narrator",
    color="#0d5c16",
    image="narrator",
)
```

- The left-hand variable (`n`) is the short identifier used in dialogue lines.
- `"Narrator"` is the display name shown in Discord.
- `color` is a hex string, stored on the character (reserved for future rendering).
- `image` is the asset basename, resolved against `game/images/`.
- All keyword args required. Trailing comma and multi-line form allowed.
- Characters are global.

## Variable defaults

```
default door_locked = True
default num_players = 2
default correct_code = "dead beef"
```

- Types: `int`, `str` (double-quoted), `bool` (`True` / `False`).
- A variable must be declared with `default` before it is read or assigned.
- Variables are global and shared across all concurrently running events.

## Labels

```
label setup:
    ...

label door(channel="Entrance"):
    ...
```

- A label names an indented block of statements, scoped to the file's namespace.
- Every label **except `setup`** must declare a channel: `label name(channel="X"):`.
- `label setup:` in `main.script` is the entry point invoked by `/start`. It is channel-less — it cannot emit dialogue; it typically only sets a `time limit` and `jump`s.
- When an event enters a label, it binds to that label's channel. Channels are lazy-created.

## Time limit

```
label setup:
    time limit 10 minutes
```

- `time limit <n> <unit>` — units: `seconds`, `minutes`, `hours`.
- Sets a game-wide deadline. On expiry every running event is cancelled, a timeout
  notice is posted in each active channel, and game state is dropped. Channels are kept.
- Intended for use in `setup`.

## Dialogue

```
n "You are outside a big restaurant."
j "Hello, party of $(num_players)?"
"YOU WIN!"
```

- Character dialogue: `<character-var> "text"`.
- Bare narration: a quoted string with no character — rendered as an italicized plain message (no avatar/name).
- Strings support interpolation in two forms:
  - `$(expression)` — explicit, delimited.
  - `$identifier` — shorthand; reads to the end of the identifier.
- Dialogue is single-line. Between successive lines the bot shows a typing indicator and waits a length-proportional duration (≈30 ms/char, clamped 1.5–6 s; tunable via env var).

## Images

```
show image "restaurant_front"
show image "restaurant_front":
    caption "The restaurant waits under the old willow tree."
show image "https://example.com/restaurant_front.png"
```

- Posts an image in the active channel, then continues.
- Local image names resolve against `game/images/`. `show image "restaurant_front"`
  checks common extensions such as `.png`, `.jpg`, `.jpeg`, `.gif`, and `.webp`.
- Exact filenames also work: `show image "restaurant_front.png"`.
- URL images may use `http://` or `https://`.
- The optional `caption` line supports normal dialogue interpolation.

## Jump

```
jump door                      # bare: current file, then main.script
jump interior.enter_restaurant  # qualified: interior.script
```

- Transfers control to the named label. **Does not return.**
- The event rebinds to the target label's channel.
- Bare label → current namespace, fallback `main.script`. Qualified `ns.label` → `<ns>.script`.

## Run (concurrency & channel switching)

```
run extra                              # one child event
run (kitchen, restroom, banquet_hall)  # three concurrent child events
```

- `run` forks one or more **child events**, each executing a label in that label's channel.
- The parent event blocks until **all** children finish, then continues at the statement after `run`. (`run` is fork-join; contrast with `jump`, which never returns.)
- A single `run label` is the way to run a section in a different channel and come back.
- `run (a, b, c)` runs the listed labels simultaneously.
- Child events share all global variables with the parent and each other.
- Each child's channel must be distinct from the other children's and from the parent's channel (one running label per channel).

## Menu

```
menu:
    "Enter the Restaurant" if not door_locked:
        $ enter_count += 1
        jump door

    "Enter a Code" if door_locked:
        jump enter_code
```

- Each option has visible text and an optional `if <cond>:` clause.
- Options whose condition is false at display time are omitted entirely.
- Renders as Discord buttons in the active channel.
- Option text supports normal interpolation, e.g. `"Serve $dish"` or
  `"Talk to $(npc_name)"`.
- **Click semantics:** anyone in the channel may click. Each user may click at most once
  per menu showing. The menu stays live for other users until execution leaves the menu
  block via a `jump` in a chosen body. A click runs the chosen body inline.
- `menu timeout <seconds>:` closes after the duration. If a `timeout:` branch
  exists, it runs; otherwise execution continues after the menu block.

```
menu timeout 30:
    "Ask Jia li for directions":
        j "Sure, follow me."
        channel link "Follow her" to "Restroom"

    timeout:
        j "Nevermind."
```

## Input block

```
input "Enter the code on the keypad." into code_entered:
    case correct_code:
        n "The lock snaps open."
        $ door_locked = False
        jump door

    case _:
        n "The keypad flashes red."
        jump door
```

- Posts the prompt, waits for the next non-bot message in the active channel,
  stores it in the declared variable, then evaluates cases in order.
- `case value:` compares the captured text to a literal or variable expression.
- `case contains "x" or "y":` applies the case-insensitive `contains` operator
  to the captured text.
- `case _:` is the default fallback.
- `input "Prompt" into variable timeout <seconds>:` times out. If `case
  timeout:` exists, it runs; otherwise execution continues after the input block.

## Button

```
button "Look around"        # bodyless gate
button "press it":          # gate + body
    $ secret_door_locked = False
    n "You press the button."
```

- Posts a single button in the active channel.
- The **first** click by anyone resolves it; execution then proceeds (running the body, if present, once).
- The clicker is recorded — `username()` returns that user afterward.

## If / elif / else

```
if enter_count == num_players:
    n "You all enter the restaurant."
    jump interior.enter_restaurant
elif enter_count > 0:
    n "Someone is still outside."
else:
    n "No one has entered yet."
```

- `if`, optional `elif` chain, optional `else`. Bodies indented.
- Conditions go through the restricted expression evaluator.

## Wait

```
wait 5
```

- `wait <n>` pauses the current event for `n` seconds. Other events keep running.

## Clear channel

```
clear channel "Restroom"
```

- Purges all messages in the named channel.

## Channel link

```
channel link "Return to Great Hall" to "Great Hall"
```

- Posts a non-blocking button that opens the target channel.
- Discord does not let bots forcibly switch a user's current channel view; this
  renders as a link button instead.
- The target channel is lazy-created if needed.

## Expression statements

```
$ enter_count += 1
$ door_locked = False
$ kitchen_investigator = username()
```

- Lines starting with `$` go to the restricted expression evaluator.
- Supported:
  - Assignments: `=`, `+=`, `-=`
  - Arithmetic: `+ - * / // %`
  - Comparisons: `== != < <= > >=`
  - Boolean: `and`, `or`, `not`
  - `contains` — case-insensitive substring test. `X contains A or B or C` distributes:
    it means `(X contains A) or (X contains B) or (X contains C)`.
  - Parentheses
  - Literals: int, str (double-quoted), `True`, `False`
  - Variable references (must be declared via `default`)
  - Built-ins: `input()`, `input("prompt")`, `username()`
- Anything outside this allowlist (arbitrary calls, attribute access, imports,
  comprehensions, etc.) is rejected at load time.

## Built-ins

| Name | Blocks? | Returns | Notes |
|---|---|---|---|
| `input(prompt)` | yes | `str` | Posts the optional string prompt, then captures the next non-bot message in the active channel. May appear inside a condition (e.g. `if input("What do you inspect?") contains "x":`); MVP allows one `input()` per expression. |
| `username()` | no | `str` | Identifier of the user who last clicked a `button`/`menu` option in this event. Empty string if none. |

The built-in set is intentionally minimal and may grow.

## Error handling

- **Load-time errors** (syntax, unknown character, allowlist violation, missing `setup`,
  label with no channel): logged; the bot refuses to register `/start` until fixed.
- **Runtime errors** (undeclared variable, channel conflict, type mismatch): logged with
  full game/event context; the game is halted and an error notice is posted in-channel
  with a short identifier the operator can grep for in the logs.
