#!/usr/bin/env bash
# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/dialog-bot}"
BRANCH="${BRANCH:-main}"
REMOTE="${REMOTE:-origin}"
SERVICE_NAME="${SERVICE_NAME:-dialog-bot}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

log() {
  printf '[deploy] %s\n' "$*"
}

run_sudo() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

cd "$APP_DIR"

if [[ ! -d .git ]]; then
  log "ERROR: $APP_DIR is not a git checkout."
  exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  log "ERROR: working tree has local changes. Commit, stash, or reset them before deploying."
  git status --short
  exit 1
fi

log "Fetching $REMOTE/$BRANCH"
git fetch "$REMOTE" "$BRANCH"

log "Checking out $BRANCH"
git checkout "$BRANCH"

log "Fast-forwarding to $REMOTE/$BRANCH"
git merge --ff-only "$REMOTE/$BRANCH"

if [[ ! -x .venv/bin/python ]]; then
  log "Creating virtual environment with $PYTHON_BIN"
  "$PYTHON_BIN" -m venv .venv
fi

log "Upgrading installer tooling"
.venv/bin/python -m pip install --upgrade pip setuptools wheel

log "Installing project"
.venv/bin/python -m pip install --no-build-isolation -e .

log "Checking scripts"
.venv/bin/python check.py

log "Compiling Python sources"
.venv/bin/python -m compileall -q bot.py check.py estimate.py dialogbot

log "Restarting $SERVICE_NAME"
run_sudo systemctl restart "$SERVICE_NAME"

log "Service status"
run_sudo systemctl --no-pager --full status "$SERVICE_NAME"

log "Done"
