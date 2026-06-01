# Runtime Semantics

This document describes the implementation behavior. For author-facing syntax,
start with `game/language_proposal.md`.

## Loading

`load_game("game")` reads every `*.script` file in `game/`.

The filename stem becomes the namespace:

- `main.script` -> `main`
- `interior.script` -> `interior`

Labels are stored as `(namespace, label_name)`. Characters and variables are
global across namespaces.

The required entry point is:

```text
label setup:
```

in `main.script`.

## Labels And Channels

Every label except `setup` must declare a channel:

```text
label kitchen(channel="Kitchen"):
```

When an event enters a label, `GameSession.bind_channel()` claims that script
channel name. Only one event may run in a channel at a time. This protects the
story transcript from two concurrent labels interleaving output in the same
place.

The IO adapter decides how script channel names map to the outside world. The
Discord adapter creates/reuses Discord text channels. The local adapter creates
JSONL transcript files.

## Jump

`jump target` is a tail call. It does not return.

The runtime implements this by raising `JumpSignal` through nested blocks. That
lets a `jump` inside a menu option, button body, or `if` body exit the current
label immediately and rebind the same event to the target label.

Bare labels resolve in this order:

1. Current namespace.
2. `main`.

Qualified labels such as `interior.enter_restaurant` resolve directly.

## Run

`run` is fork-join concurrency:

```text
run (kitchen, restroom, banquet_hall)
```

The parent event starts one child task per target label and waits until all
children finish. Child events share global variables with the parent, but each
has its own current channel and last-click user.

Because channels are locked per active event, sibling `run` targets must bind to
different channels.

## Menus

A menu renders visible options through the adapter. Conditions are evaluated
once when the menu is opened.

When a user clicks an option:

- The runtime records that user for `username()`.
- The selected option body executes inline.
- If the body reaches `continue`, the menu closes and execution resumes at the
  statement after the menu in the same label.
- If the body reaches a `jump`, the menu closes and control leaves the current
  label.
- If the body does not jump, the menu stays live for more users.

The Discord adapter enforces one click per user per menu view. Local tests can
queue menu clicks with `LocalDialogIO.queue_menu()`.

Timed menus use `menu timeout <seconds>:`. On timeout, the runtime closes the
menu and runs the optional `timeout:` branch. If no timeout branch exists,
execution continues after the menu block.

## Buttons

A button is a gate. The runtime waits for the first click, records that user for
`username()`, then runs the optional body once.

```text
button "Look around":
    $ kitchen_investigator = username()
```

## Channel Links

`channel link "Label" to "Channel"` posts a non-blocking navigation button.
Discord link buttons open the target channel for the user, but do not produce a
click event, so this statement never blocks script execution.

The runtime asks the IO adapter to create or resolve the target channel before
posting the link.

## Input Blocks

Input blocks consolidate text prompts, storage, and branching:

```text
input "Enter the code on the keypad." into code_entered:
    case correct_code:
        jump unlocked

    case _:
        jump locked
```

The captured message is assigned to the declared variable before cases run.
`case value:` performs equality against a literal or variable expression.
`case contains "x" or "y":` applies the script `contains` operator to the
captured text. `case timeout:` is available only when the block uses
`timeout <seconds>`.

## Variables

Variables must be declared with `default` before use. All events in a session
share one variable dictionary.

The runtime uses a lock around reads and writes. This protects individual
variable operations, but it does not make multi-statement story logic atomic.
When adding more concurrent mechanics, prefer explicit script structure over
implicit assumptions about ordering.

## Dialogue And Interpolation

Character dialogue:

```text
n "Hello, party of $(num_players)?"
```

Bare narration:

```text
"YOU WIN!"
```

Interpolation runs in two passes:

1. Explicit `$(expression)`.
2. Shorthand `$identifier`.

This order prevents identifiers inside explicit expressions from being expanded
too early.

## Expressions

Most expressions are a restricted Python-like subset parsed with Python's `ast`.
Only known-safe nodes are allowed.

The `contains` operator is not Python. It is script syntax handled before the
Python AST path:

```text
if input() contains "portrait" or "winnie" or "investigate":
```

This means:

```text
(input() contains "portrait")
or (input() contains "winnie")
or (input() contains "investigate")
```

The runtime evaluates the left side once, then compares it case-insensitively
against each right-side alternative.

The MVP permits at most one `input()` call per expression. That keeps blocking
message waits predictable. `input()` also accepts one optional string prompt:

```text
$ code_entered = input("Enter the code on the keypad.")
```

The Discord adapter posts the prompt in the active channel before waiting for
the user's next message.

## Timeouts And Errors

`time limit` creates a timeout task. On expiry, the session posts a notice to
known channels, cancels running events, and marks the session done.

Runtime failures produce a short error id in-channel and log the full exception.
Load-time errors prevent `/start` from launching a broken script.
