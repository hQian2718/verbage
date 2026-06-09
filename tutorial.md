## What Is Verbage?

Verbage is a Discord bot for telling interactive stories and running small games in a Discord server. Players read scenes, click choices, type responses, split into different channels, and change what happens.

If you have used Twine or Ren'Py, the idea will feel familiar: you write a script, Verbage checks it, and a player starts it with `/start`.

[[Quickstart to Verbage#The Syntax of Verbage|Show me how to write a script!]]
[[Quickstart to Verbage#Deploying and Running the Game|How do I play the story I created?]]

## The Syntax of Verbage

Verbage scripts are plain text files ending in `.script`. You write scenes in the order they should happen, with choices and logic where players can change the story.

Here is the smallest useful script:

```text
label setup:
    "You stand outside a restaurant."
```

When someone runs `/start`, Verbage looks for `label setup:` in `main.script` and begins there. The indented lines under a label are the scene. Indentation matters: anything inside the label should be indented with spaces.

Suggested image: place a screenshot immediately after this paragraph showing the script beside the Discord output.

Alt text: A code editor shows `label setup:` with one narrator line. Next to it, a Discord channel shows a Narrator message saying "You stand outside a restaurant."

### Defining Your Characters

Characters are the voices in your game. You define a character once, then use the short name on the left whenever that character speaks.

```text
define jia = Character(
    "Jia Li",
    color="#b16399",
    image="jiali",
)

label setup:
    jia "Welcome. Your table is almost ready."
```

In Discord, `"Jia Li"` is the display name. The script name `jia` is only for you. The `image` value is optional; if you include it, Verbage looks for an image such as `game/images/jiali.png` or `game/images/jiali.jpg` and uses it as the character's avatar.

Suggested image: place a screenshot after this explanation showing character dialogue with a custom avatar.

Alt text: A Discord message appears from Jia Li with a custom profile image. The message says, "Welcome. Your table is almost ready."

You can also define a narrator:

```text
define n = Character(
    "Narrator",
    color="#a48335",
)

label setup:
    n "Rain taps against the restaurant windows."
```

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

Suggested image: place a file-tree screenshot after the directory example.

Alt text: A project file tree shows a `game` folder containing `main.script`, `characters.script`, `act_1.script`, and an `images` folder with character images.

### Writing Scenes With Labels

Labels are named sections of story. Use them for scenes, rooms, chapters, repeated interactions, and places players can jump back to.

```text
label setup:
    jump entrance

label entrance(channel="Entrance"):
    n "You stand outside a locked restaurant."
    jump door

label door(channel="Entrance"):
    n "There is a keypad beside the door."
```

`jump` moves the story to another label and does not come back. Think of it as "go to the next scene."

The optional `channel="Entrance"` tells Verbage where this label should happen in Discord. If the Discord channel does not exist, Verbage creates it. If you leave out `channel=`, the label uses the default channel from your `.env` file.

Suggested image: place a screenshot here showing the automatically created `Entrance` channel.

Alt text: A Discord sidebar shows a game category with an `Entrance` text channel. The channel contains narrator messages from the entrance and door labels.

You can write bare narration without a character:

```text
"The lock clicks."
```

You can pause the current scene:

```text
wait 5
```

That waits five seconds. Other scenes running at the same time keep going.

### Showing Choices With Menus

Use a `menu:` when players should choose between options. Each option appears as a Discord button.

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

A regular `menu:` waits for one click. After the chosen option finishes, the story continues after the menu unless that option uses `jump`.

Menu option text can use variables, just like dialogue:

```text
default dish = "Vegetarian Goose"

label table(channel="Dining Room"):
    menu:
        "Serve $dish":
            n "You carry out the $dish."
```

Suggested image: place a screenshot after this menu example showing the two Discord buttons.

Alt text: A Discord message contains two clickable buttons labeled "Enter a code" and "Walk away" below the narrator text "The keypad glows blue."

You can hide or show options with `if`:

```text
default door_locked = True

label door(channel="Entrance"):
    menu:
        "Open the door" if not door_locked:
            n "You enter the restaurant."

        "Enter a code" if door_locked:
            jump enter_code
```

At first, only "Enter a code" appears because `door_locked` is `True`. After the story sets `door_locked` to `False`, "Open the door" can appear instead.

Suggested image: place a before-and-after image here: first the locked-door menu, then the unlocked-door menu.

Alt text: Two Discord screenshots are shown side by side. The first shows only an "Enter a code" button. The second, after the lock opens, shows an "Open the door" button.

Timed menus are useful when hesitation matters:

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

If nobody clicks within 20 seconds, the `timeout:` branch runs.

Suggested image: place a screenshot here showing a timed menu after it has expired.

Alt text: A Discord menu has disabled buttons, and the narrator has posted "The moment passes."

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

Suggested image: place a screenshot here showing the prompt, the player's typed answer, and the bot's response.

Alt text: In Discord, the bot asks "Enter the code on the keypad." A player types "dead beef." The narrator responds, "The lock snaps open."

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

Suggested image: place a screenshot after this example showing a natural-language player response.

Alt text: A player types "I look behind the portrait." The bot recognizes the word "portrait" and replies, "You find a hidden button behind the frame."

### Remembering Story State

Variables remember what has happened. Declare them with `default` before using them.

```text
default clues_found = 0
default secret_door_locked = True
default suspect_name = ""
```

Use `$` lines to change variables:

```text
$ clues_found += 1
$ secret_door_locked = False
$ suspect_name = "Jia Li"
```

Use `if`, `elif`, and `else` to branch:

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

You can place `if` blocks inside labels, menus, buttons, and input cases.

Suggested image: place a diagram or screenshot here showing the same scene producing different text depending on `clues_found`.

Alt text: Three possible Discord outputs are shown for the report scene: no clues, some clues, and enough clues to accuse someone.

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

Suggested image: place a screenshot here showing multiple player names appearing as they click.

Alt text: A Discord channel shows a persistent "Push together" button. Messages say that Alice, Bob, and Carol each push the door, followed by "With everyone pushing, the door finally opens."

You can also put a timeout on a persistent menu:

```text
label closing_door(channel="Basement"):
    persistent menu timeout 30:
        "Hold the door":
            n "$(username()) keeps the door from closing."

        timeout:
            n "The door slams shut."
```

Suggested image: place a screenshot here showing a persistent menu that timed out.

Alt text: The persistent menu buttons are disabled, and the narrator says, "The door slams shut."

### Running Scenes In Multiple Channels

Discord lets your story happen in several channels at once. `run` starts one or more labels and waits until all of them finish.

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

Suggested image: place a wide screenshot here showing the Discord channel list with Great Hall, Kitchen, Restroom, and Banquet Hall.

Alt text: Discord shows a game category with four text channels. The Kitchen, Restroom, and Banquet Hall channels each contain a small scene and a "Return to Great Hall" link button.

Suggested image: place a second screenshot after the previous one showing the Great Hall after all three side scenes finish.

Alt text: The Great Hall channel shows the setup message, then later a message saying, "Everyone returns to the Great Hall."

### Additional Features

These smaller tools are handy once your story is moving.

Use `show image` to post a picture into the current Discord channel. This is
inspired by Ren'Py's `show` statement, but Verbage keeps the first version
simple: it posts the image as a message and then continues.

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

Suggested image: place a screenshot here showing a local image posted in a
Discord channel with its caption.

Alt text: A Discord channel shows a large image of a restaurant exterior. Above
or beside it, the caption reads, "The restaurant waits under the old willow
tree."

A `button` is a one-option gate. The story waits until someone clicks it, then continues:

```text
default investigator = ""

label study(channel="Study"):
    button "Look around":
        $ investigator = username()
        n "$(investigator) notices fresh footprints."
```

Suggested image: place a screenshot here showing a single "Look around" button before and after it is clicked.

Alt text: A Discord message shows one button labeled "Look around." After a player clicks it, the bot says that player's name and describes the footprints.

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

Suggested image: place a before-and-after screenshot here only if your tutorial wants to emphasize cleanup.

Alt text: The first Discord screenshot shows several old messages in the Restroom channel. The second screenshot shows the channel cleared, ready for the next scene.

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

To run the game, you must be running the bot program on your computer and point it to your Discord server.

1. Download the source code of Verbage.
2. Put all of your scripts and images into the `game` directory.
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
