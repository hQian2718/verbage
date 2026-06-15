<!--
Copyright (C) 2026 Placeholder Name
SPDX-License-Identifier: GPL-3.0-only
-->

# Deployment

This guide describes the simple production setup for running Verbage on an AWS
Lightsail Ubuntu VM. The same shape also works on any small Linux VM:

- The repo lives at `/opt/dialog-bot`.
- A Python virtual environment lives at `/opt/dialog-bot/.venv`.
- The bot runs as a `systemd` service.
- `deploy/deploy.sh` is the repeatable deploy command.

The bot only needs outbound network access to Discord. You do not need to open a
public inbound application port.

## Discord Setup

Create a Discord application and bot in the Discord Developer Portal. Enable
Message Content Intent for `input()` support.

Invite the bot to every server where it should run with both scopes:

- `bot`
- `applications.commands`

The installed bot needs these permissions:

- Send Messages
- Manage Channels
- Manage Webhooks
- Read Message History
- Manage Messages, for `clear channel`

Production should leave `DEV_GUILD_ID` blank or unset. When `DEV_GUILD_ID` is
set, slash command sync is limited to that one development server.

## First Deploy

Install system packages:

```sh
sudo apt update
sudo apt install -y git python3 python3-venv
```

Clone the repo and give your SSH user ownership. Replace `<repo-url>` with the
Git URL and replace `ubuntu` if your VM username is different.

```sh
sudo git clone <repo-url> /opt/dialog-bot
sudo chown -R "$(whoami):$(whoami)" /opt/dialog-bot
cd /opt/dialog-bot
```

Create the environment file:

```sh
cp .env.example .env
nano .env
```

Fill in at least:

```env
DISCORD_TOKEN=your_token_here
GAME_DIR=game
DEV_GUILD_ID=
```

Install the project and check the scripts once:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install --no-build-isolation -e .
.venv/bin/python check.py
```

If `check.py` reports missing images on the VM but not locally, check filename
casing. Linux filesystems are case-sensitive, so `show image "Cheng Ji"` does
not match `game/images/cheng ji.png`.

Install the service:

```sh
sudo cp deploy/dialog-bot.service /etc/systemd/system/dialog-bot.service
sudo nano /etc/systemd/system/dialog-bot.service
```

Check these lines:

```ini
WorkingDirectory=/opt/dialog-bot
EnvironmentFile=/opt/dialog-bot/.env
ExecStart=/opt/dialog-bot/.venv/bin/python /opt/dialog-bot/bot.py
User=ubuntu
```

Change `User=ubuntu` to the result of `whoami` if your VM uses a different
username.

Load and enable the service:

```sh
sudo systemctl daemon-reload
sudo systemctl enable dialog-bot
```

Run the deploy script:

```sh
deploy/deploy.sh
```

Watch logs:

```sh
journalctl -u dialog-bot -f
```

## Future Deploys

After the first deploy, the normal manual deploy is:

```sh
cd /opt/dialog-bot
deploy/deploy.sh
```

The script:

- Refuses to deploy over local uncommitted changes.
- Fetches the target branch from the remote.
- Fast-forwards the checkout.
- Creates `.venv` if needed.
- Upgrades installer tooling.
- Installs the project from `pyproject.toml`.
- Runs `check.py`.
- Compiles Python sources.
- Restarts the `systemd` service.
- Prints service status.

You can override defaults with environment variables:

```sh
APP_DIR=/opt/dialog-bot BRANCH=main REMOTE=origin SERVICE_NAME=dialog-bot deploy/deploy.sh
```

## Logs and Status

Use these commands while debugging:

```sh
sudo systemctl status dialog-bot --no-pager
journalctl -u dialog-bot -n 100 --no-pager
journalctl -u dialog-bot -f
```

To see the exact unit file and any overrides that `systemd` is using:

```sh
sudo systemctl cat dialog-bot
systemctl show dialog-bot -p FragmentPath -p DropInPaths -p User
```

## Common Issues

### `status=217/USER`

This means `systemd` cannot start the service as the user named in the unit
file. Check the configured user:

```sh
systemctl show dialog-bot -p User
getent passwd ubuntu
whoami
```

Edit the unit file with `sudo`:

```sh
sudo nano /etc/systemd/system/dialog-bot.service
```

Set `User=` to a real non-root VM user, then reload and restart:

```sh
sudo systemctl daemon-reload
sudo systemctl restart dialog-bot
sudo systemctl status dialog-bot --no-pager
```

Also make sure that user owns the app checkout:

```sh
sudo chown -R "$(whoami):$(whoami)" /opt/dialog-bot
```

### Slash Commands Do Not Appear

Global command sync can take time to appear in Discord. For a development
server, set `DEV_GUILD_ID` in `.env` and restart the service. For production,
leave `DEV_GUILD_ID` blank so commands register globally for all installed
servers.

Make sure the bot was invited with the `applications.commands` scope.

## GitHub Actions

Keep `deploy/deploy.sh` as the source of truth. A GitHub Action can SSH into the
VM and run that script after pushes to `main`:

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy over SSH
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.LIGHTSAIL_HOST }}
          username: ${{ secrets.LIGHTSAIL_USER }}
          key: ${{ secrets.LIGHTSAIL_SSH_KEY }}
          script: |
            cd /opt/dialog-bot
            deploy/deploy.sh
```

Use GitHub secrets for the host, username, and private SSH key. Keep
`DISCORD_TOKEN` only on the VM in `.env`.

## AWS CLI

AWS CLI is useful for infrastructure tasks such as creating Lightsail snapshots,
managing static IPs, or adjusting firewall rules. It is not needed for normal
application deploys. For day-to-day bot updates, SSH plus `deploy/deploy.sh` is
simpler and easier to inspect.
