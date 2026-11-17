---
layout: default
title: Quickstart to Verbage
description: Learn how to write and run interactive Discord stories with Verbage.
---

<!--
Copyright (C) 2026 Kuan Qian
SPDX-License-Identifier: GPL-3.0-only
-->

## What Is Verbage?

Verbage is a Discord bot for telling interactive stories and running text games in a Discord server. Players can read dialog, but they can also make choices, type responses to NPCs, and make the story their own. 

If you have used Twine or Ren'Py, the idea will feel familiar: you write a script, Verbage checks it, and a player starts it with `/start`. However, Verbage does a couple of unique things.

- Unlike most visual novels or hypertext stories, Verbage lets you write singleplayer or multiplayer games.
- Multiple scenes can happen at the same time, in multiple text channels.
- After the players finish the story, their unique story is saved as message history.

If this intrigues you, you should use Verbage!

- [Show me how to write a script!](#the-syntax-of-verbage)
- [How do I play the story I created?](#deploying-and-running-the-game)

## Getting Started
As the game maker, you should download the code of Verbage. You can get it here:

- [Source Code on Github](https://github.com/hQian2718/verbage)
- [Source Code on itch.io](https://vielzahl.itch.io/verbage)

You need Python installed on your computer. Verbage recommends Python 3.12.

You can set up everything and check your installation via these commands. Run them by pasting them into the terminal.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

## The Syntax of Verbage

The animations beside each example show what it looks like when the game runs in Discord. The highlighted line is the one Verbage is running. Press **Replay** to watch one again.

Verbage scripts are plain text files ending in `.script`. You write scenes in the order they should happen, with choices and logic where players can change the story.

Here is the smallest useful script:

```text
label setup:
    "You stand outside a restaurant."
```

The indented lines under a label are the scene. Indentation matters: all the dialog and game logic inside the label should be indented with spaces; this tells Verbage they are part of this label.

The label "setup" is special. When placed in the main script (which must be titled main.script), Berbage will always start the game by running 'setup'.

Here's what this minimal story looks like in Discord. Players start the game by typing a **slash command** in Discord: `/start`.

<div class="vb-demo" data-demo="setup" role="img" aria-label="Alice types /start in a Discord server. The bot replies &quot;Starting the game.&quot;, a new #game channel appears, and the bot posts the narration &quot;You stand outside a restaurant.&quot; while line 2 of the script is highlighted."></div>

You can make a story entirely in the setup label! However, it may be easier to separate the story into managable chunks and give each their own label. 

### Organizing Your Files

Your game lives in the `game` directory.

```text
game/
    main.script
    characters.script
    act_1.script
    images/
        jiali.png
        narrator.jpg
```

Verbage loads every `.script` file in `game/`. You can keep everything in `main.script` at first, then move characters, acts, or locations into separate files when the story grows.

Three rules are worth remembering:

- `main.script` must contain `label setup:`.
- Character definitions and variable defaults can live in any `.script` file.
- A label in another file can be reached with `filename.label_name`, without the `.script` part.

For example, `jump act_1.begin` jumps to `label begin:` inside `game/act_1.script`.

<div class="vb-demo" data-demo="files" role="img" aria-label="A file tree of the game folder beside a terminal running check.py, which reads each script and image and reports 2 labels, 2 characters, 2 images and 0 defaults."></div>


### Defining Your Characters

You can make Verbage portray many NPCs by defining characters. This changes the default appearance of the avatar and display name associated with the lines.

You only need to define a character once. After that, you may use the short name on the left whenever that character speaks.

Using a character looks like this.

```text
define jia = Character(
    "Jia Li",
    color="#b16399",
    image="jiali",
)

label setup:
    jia "Welcome. Your table is almost ready."
```

In Discord, `"Jia Li"` is the display name. The script name `jia` is a shorthand for your use while writing the script. The `image` value is optional; if you include it, Verbage looks for an image named "jiali" in the game's images folder, such as `game/images/jiali.png` or `game/images/jiali.jpg`. It will be used as the character's avatar.

<div class="vb-demo" data-demo="character" role="img" aria-label="As the define block and then the dialogue line are highlighted, a Discord message appears from Jia Li with a pixel-art avatar saying &quot;Welcome. Your table is almost ready.&quot;"></div>

As an example of a second character, let's define a narrator:

```text
define n = Character(
    "Narrator",
    color="#a48335",
)

label setup:
    n "Rain taps against the restaurant windows."
    jia "Welcome, how many people in your party?"
```

### Writing with Labels abd Jumps

Labels are named sections of story. Use them for scenes, rooms, chapters, and repeated interactions.

Besides being an organizational tool, labels let your stories branch off by enabling `jump` commands. Look at this example where the story jumps forward:

```text
label setup:
    jump entrance

label entrance(channel="Entrance"):
    n "You stand outside a locked door."
    jump door

label door(channel="Entrance"):
    n "There is a keypad beside the door."
```

In this case, `jump` moves the story to another label and does not come back. Think of it as "go to the next scene."

The `channel="Entrance"` is a parameter that tells Verbage where this label should be played out in Discord. If the Discord channel does not exist yet, Verbage will create it. If you leave out `channel=`, the label uses the default channel, which you can also configure by going to the ".env" file. 

<div class="vb-demo" data-demo="channels" role="img" aria-label="The jump to the entrance label creates an #entrance channel in the Discord sidebar, where the Narrator posts &quot;You stand outside a locked door.&quot; and then &quot;There is a keypad beside the door.&quot;"></div>

`jump` can also jump back, letting you reuse earlier sections. This example shows a door that won't open.

```text
label setup:
    jump entrance

label entrance(channel="Entrance"):
    n "You stand outside a locked door."
    jump door
    # this jumps forward

label door(channel="Entrance"):
    n "You try the door, but it won't open."
    wait 5
    jump entrance
    # this jumps back
```

### Showing Choices With Menus

To present options to players, use a `menu:` when players should make a choice. Each option will appear in Discord as a button.

Suppose later in the restaurant, the players encounter a locked door they can investigate. Here's how you can use menus to ask players to choose:

```text
label door(channel="Entrance"):
    n "The keypad glows blue."

    menu:
        "Enter a code":
            jump enter_code

        "Walk away":
            n "You step back from the door."

    n "The night feels colder now."
```

As soon as one player clicks a button, the chosen option will run any commands inside it. The story continues after the menu unless that option uses `jump`.

<div class="vb-demo" data-demo="menu" role="img" aria-label="Under the narrator text &quot;The keypad glows blue.&quot;, two buttons appear: &quot;Enter a code&quot; and &quot;Walk away&quot;. Alice clicks &quot;Walk away&quot;, the buttons are disabled, and the Narrator says &quot;You step back from the door.&quot; then &quot;The night feels colder now.&quot;"></div>

You can hide or show options with `if`:

```text
default door_locked = True

label door(channel="Entrance"):
    menu:
        "Open the door" if not door_locked:
            n "You enter the restaurant's basement."

        "Enter a code" if door_locked:
            jump enter_code
```

At first, only "Enter a code" appears because  is `True`. After the story sets `door_locked` to `False`, "Open the door" can appear instead.

<div class="vb-demo" data-demo="conditional" role="img" aria-label="While door_locked is True, the menu shows only &quot;Enter a code&quot;. After the players crack the code, door_locked becomes False and the menu shows &quot;Open the door&quot; instead. Bob clicks it and the Narrator says &quot;You enter the restaurant&#x27;s basement.&quot;"></div>

Jumps in menu options lets you branch stories, but using a variable like `door_locked` lets you remember a player choice and change the story based on that later! Let's learn how to use them.

### Remebering Story State

Variables remember what has happened. Declare them with default before using them.
```
default clues_found = 0
default secret_door_locked = True
default suspect_name = ""
```

Use `$` lines to change variables:

```
$ clues_found += 1
$ secret_door_locked = False
$ suspect_name = "Jia Li"
```

Use if, elif, and else to branch:

```text
label report(channel="Great Hall"):
    if clues_found >= 3:
        n "You have enough evidence to accuse someone."
        jump accusation
    elif clues_found > 0:
        n "You have a theory, but not enough proof."
    else:
        n "You are still completely in the dark."
```

You can place if blocks inside labels, menus, buttons, and input cases.

<div class="vb-demo" data-demo="branches" role="img" aria-label="The report scene runs three times. With clues_found = 0 the Narrator says &quot;You are still completely in the dark.&quot;; with 1, &quot;You have a theory, but not enough proof.&quot;; with 3, &quot;You have enough evidence to accuse someone.&quot;"></div>

### Showing Images

Verbage can send more than text. You can already link to websites, images, and videos with Discord's link syntax:


Alternatively, you can use `show image` to post a picture into the current Discord channel. Verbage posts the image as a message and then continues.

```text
label restaurant_front(channel="Entrance"):
    show image "restaurant_front":
        caption "The restaurant waits under the old willow tree."
```

Put local image files in `game/images`. For `show image "restaurant_front"`,
Verbage looks for files such as `restaurant_front.png`,
`restaurant_front.jpg`, and `restaurant_front.webp`. You can also show an image
by URL:

```text
show image "https://example.com/restaurant_front.png"
```

<div class="vb-demo" data-demo="image" role="img" aria-label="The bot posts the caption &quot;The restaurant waits under the old willow tree.&quot; with a pixel-art picture of a restaurant at night beside a willow tree."></div>

### Breaktime!

With dialog, characters, menus, jumps, variables, and images, you can already tell interesting stories! Many visual novels can be written with only these features.

If you are new to Verbage, I would recommend familiarizing yourself with these building blocks. Maybe write a small scene or story first or take a break in your learning experience!
 
If you want to do more unique things with Verbage, check out the additional features below.


### Waiting 

Dialog in Verbage is automatically paced so that players have enough time to read each line as they appear. However, you can add additional pauses by this simple "wait" command: 

```text
wait 5
```

This waits five seconds.


### Timed Menus

You can force the players to pick an option quickly (or else!). The menu itself won't show how much time remains; but you can tell the players about the time limit before it appears.

```text
label overhear(channel="Dining Room"):
    menu timeout 20:
        "Interrupt the conversation":
            n "You clear your throat."

        "Keep listening":
            n "You stay quiet."

        timeout:
            n "The moment passes."
```

In this example, if no one clicks within 20 seconds, the `timeout:` branch runs.

<div class="vb-demo" data-demo="timed" role="img" aria-label="Two buttons appear, &quot;Interrupt the conversation&quot; and &quot;Keep listening&quot;. Twenty seconds pass with no clicks, the buttons are disabled, and the Narrator says &quot;The moment passes.&quot;"></div>

### Letting Players Type Responses

Use an `input` block when players should type something rather than click a button.

```text
default code_entered = ""
default correct_code = "dead beef"
default door_locked = True

label enter_code(channel="Entrance"):
    input "Enter the code on the keypad." into code_entered:
        case correct_code:
            n "The lock snaps open."
            $ door_locked = False
            jump door

        case _:
            n "The keypad flashes red."
            jump door
```

The prompt is posted in the current channel. Verbage waits for the next player message, stores it in `code_entered`, then checks the cases from top to bottom. `case _:` means "anything else."

<div class="vb-demo" data-demo="input" role="img" aria-label="The bot asks &quot;Enter the code on the keypad.&quot; Alice types &quot;dead beef&quot;, which is stored in code_entered. The first case matches, the Narrator says &quot;The lock snaps open.&quot;, and door_locked becomes False."></div>

For looser matching, use `contains`:

```text
default restroom_action = ""

label restroom(channel="Restroom"):
    input "What do you inspect?" into restroom_action:
        case contains "portrait" or "painting" or "winnie":
            n "You find a hidden button behind the frame."

        case _:
            n "You do not find anything unusual."
```

`contains` is case-insensitive, so `Portrait`, `portrait`, and `PORTRAIT` all work.

<div class="vb-demo" data-demo="contains" role="img" aria-label="The bot asks &quot;What do you inspect?&quot; Carol types &quot;I look behind the portrait.&quot; The answer contains &quot;portrait&quot;, so the Narrator replies &quot;You find a hidden button behind the frame.&quot;"></div>

### Using Persistent Menus For Multiplayer Moments

A normal `menu:` is for one decision. A `persistent menu:` stays open after a player clicks, which is useful when several players need to participate.

Here is a door that opens only after three different players click "Push together":

```text
default push_count = 0

label heavy_door(channel="Basement"):
    n "The iron door is too heavy for one person."

    persistent menu:
        "Push together":
            $ push_count += 1
            n "$(username()) throws their shoulder against the door."

            if push_count >= 3:
                n "With everyone pushing, the door finally opens."
                jump basement_open

        "Look for another way":
            n "You search the walls, but find no other passage."

label basement_open(channel="Basement"):
    n "Cold air rolls up from the stairs below."
```

`username()` returns the Discord display name of the player who clicked the menu option or button. That lets the story acknowledge who acted.

<div class="vb-demo" data-demo="persistent" role="img" aria-label="A persistent &quot;Push together&quot; button stays active as Alice, Bob and Carol click it in turn. The Narrator announces each push as push_count rises to 3, then says &quot;With everyone pushing, the door finally opens.&quot;"></div>

You can also put a timeout on a persistent menu:

```text
label closing_door(channel="Basement"):
    persistent menu timeout 30:
        "Hold the door":
            n "$(username()) keeps the door from closing."

        timeout:
            n "The door slams shut."
```

<div class="vb-demo" data-demo="persistentTimeout" role="img" aria-label="Alice clicks the persistent &quot;Hold the door&quot; button and the Narrator says &quot;Alice keeps the door from closing.&quot; After 30 seconds the button is disabled and the Narrator says &quot;The door slams shut.&quot;"></div>

### Running Stories In Multiple Channels

Verbage lets your story happen in several channels at once. `run` starts one or more labels and waits until all of them finish.

```text
label enter_restaurant(channel="Great Hall"):
    n "The party splits up to search the restaurant."
    run (kitchen, restroom, banquet_hall)
    n "Everyone returns to the Great Hall."

label kitchen(channel="Kitchen"):
    n "The kitchen is hot and noisy."
    button "Look around"
    n "You find a burned receipt."
    channel link "Return to Great Hall" to "Great Hall"

label restroom(channel="Restroom"):
    n "The restroom is quiet."
    button "Inspect the mirror"
    n "Someone wrote a number in the fogged glass."
    channel link "Return to Great Hall" to "Great Hall"

label banquet_hall(channel="Banquet Hall"):
    n "The tables are set for a banquet."
    button "Check under the table"
    n "You find a torn envelope."
    channel link "Return to Great Hall" to "Great Hall"
```

`run (kitchen, restroom, banquet_hall)` starts all three scenes at the same time. The Great Hall scene waits until the Kitchen, Restroom, and Banquet Hall scenes are all finished.

`channel link "Return to Great Hall" to "Great Hall"` posts a Discord button that helps players move to another channel. Bots cannot force a player's Discord view to switch, so this creates a convenient link instead.

<div class="vb-demo" data-demo="run" role="img" aria-label="After the Great Hall message, run creates #kitchen, #restroom and #banquet-hall channels, which fill with their scenes at the same time. Alice, Bob and Carol each click a button in one room, each room ends with a &quot;Return to Great Hall&quot; link, and the Great Hall then says &quot;Everyone returns to the Great Hall.&quot;"></div>

<div class="vb-demo" data-demo="runReturn" role="img" aria-label="The Great Hall waits on the run line while the three side scenes finish one by one. Once nothing is left to wait for, the Narrator says &quot;Everyone returns to the Great Hall.&quot;"></div>

### Additional Features

These smaller tools are handy once your story is moving.

A `button` is a one-option gate. The story waits until someone clicks it, then continues:

```text
default investigator = ""

label study(channel="Study"):
    button "Look around":
        $ investigator = username()
        n "$(investigator) notices fresh footprints."
```

<div class="vb-demo" data-demo="button" role="img" aria-label="A single &quot;Look around&quot; button appears. Alice clicks it, investigator is set to &quot;Alice&quot;, and the Narrator says &quot;Alice notices fresh footprints.&quot;"></div>

Add `timeout 15` if the button should expire:

```text
label study(channel="Study"):
    button "Look around" timeout 15:
        n "$(username()) searches the room just in time."
```

`clear channel` removes old messages from a game channel. Use it carefully; it is best for moments where you intentionally want to reset a room.

```text
clear channel "Restroom"
```

<div class="vb-demo" data-demo="clear" role="img" aria-label="The #restroom channel holds earlier messages. After the line &quot;A cleaner sweeps through the room.&quot;, clear channel removes every message, and the Narrator posts &quot;The restroom is quiet again.&quot;"></div>

`time limit` sets a game-wide deadline. It usually belongs in `label setup:`.

```text
label setup:
    time limit 45 minutes
    jump start
```

Comments help future-you understand the scene:

```text
# The players should know the door is important, but not how to open it yet.
n "The red door has no handle."
```

## Deploying and Running the Game

To run the game, you must be running the bot program on your computer and point it to your Discord server. This 
3. Go to your Discord Developer Portal [here](https://discord.com/developers/home) and create a new application.
4. Create a `.env` file and fill in environmental variables. These variables allow the bot to find your server and send messages to Discord.
5. Go to your server or make a new one.
6. Invite the bot to your server.
7. Run `/start`.

### Setting Your Environmental Variables

- `DISCORD_TOKEN`
    - Go to the Discord Developer Portal.
    - Open your application.
    - Go to the Bot page.
    - Reset and copy the bot token.
    - Keep this secret. Do not post it in Discord and do not commit it to Git.
- `GUILD_ID`
    - Open Discord.
    - Right-click your server.
    - Copy the server ID.
    - If you do not see this option, enable Developer Mode in Discord settings.
- `GAME_CATEGORY_NAME`
    - The Discord category where Verbage should create game channels.
    - Example: `Dialog Game`
- `GAME_DEFAULT_CHANNEL`
    - The channel name used by labels that do not specify `channel="..."`.
    - Example: `Game`

## Understanding The Source Code
Most of Verbage was written by a LLM! If you like to code with an agent, ask it how
this repository works. 

You can also read about the project from these docs:

- [Language syntax](language_syntax.md) is the complete reference for formatting `.script` files.
- [Runtime semantics](runtime-semantics.md) explains what each command does while the game is running.
- [Architecture](architecture.md) gives a map of the parser, runtime, Discord adapter, and local testing adapter.
- [Web frontend](web.md) shows how to serve the game to browsers, without Discord.
- [Local testing](local-testing.md) shows how to run scripts without Discord, using local mocks and saved output.
- [Deployment](deployment.md) covers the steps for running Verbage on a server.
