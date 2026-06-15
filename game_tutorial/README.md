<!--
Copyright (C) 2026 Kuan Qian
SPDX-License-Identifier: GPL-3.0-only
-->

# Tutorial Capture Game

This folder contains a small Verbage game for taking screenshots used by
`tutorial.md`.

To run it without renaming folders, set:

```env
GAME_DIR=game_tutorial
GAME_CATEGORY_NAME=Verbage Tutorial Capture
GAME_DEFAULT_CHANNEL=Tutorial Capture
```

Then start the bot and run `/start` in Discord.

## Capture Flow

The game advances one screenshot setup at a time. Most screens pause on a
`Next capture` button so you can take the screenshot before continuing.

Some captures need specific actions:

- Timed menu: do not click anything; wait for the timeout message.
- Code input: type `dead beef`.
- Natural-language input: type `I look behind the portrait.`
- Persistent multiplayer menu: have three different Discord users click
  `Push together`, or use three test accounts.
- Multi-channel scene: click the room buttons in Kitchen, Restroom, and
  Banquet Hall so the Great Hall can continue.
- Clear-channel screenshot: capture the Restroom before clicking
  `Clear Restroom now`, then capture it again after the channel is cleared.

The tutorial's file-tree screenshot is not produced by Discord. Capture that
from your editor or file browser.

The character-avatar screenshot uses `image="jiali"`. Add a local avatar at
`game_tutorial/images/jiali.png` or `game_tutorial/images/jiali.jpg` if you want
Jia Li to appear with a custom profile image.
