# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from aiohttp import web
from dotenv import load_dotenv

from dialogbot.parser import ScriptLoadError
from dialogbot.web_server import ACCESS_LOG_FORMAT, WebConfig, create_app


def main() -> None:
    load_dotenv(override=True)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Serve the dialog game as a web app.")
    parser.add_argument("--host", default=os.getenv("WEB_HOST", "127.0.0.1"), help="Interface to bind (WEB_HOST).")
    parser.add_argument("--port", type=int, default=int(os.getenv("WEB_PORT", "8080")), help="Port to bind (WEB_PORT).")
    parser.add_argument("--game-dir", default=os.getenv("WEB_GAME_DIR", "game_web"), help="Directory containing *.script files (WEB_GAME_DIR).")
    parser.add_argument("--dialog-min-delay", "--min-delay", type=float, help="Override DIALOG_MIN_DELAY for this process.")
    parser.add_argument("--dialog-max-delay", "--max-delay", type=float, help="Override DIALOG_MAX_DELAY for this process.")
    args = parser.parse_args()
    if args.dialog_min_delay is not None:
        os.environ["DIALOG_MIN_DELAY"] = str(args.dialog_min_delay)
    if args.dialog_max_delay is not None:
        os.environ["DIALOG_MAX_DELAY"] = str(args.dialog_max_delay)

    config = WebConfig(
        game_dir=Path(args.game_dir),
        title=os.getenv("WEB_TITLE", "Verbage").strip() or "Verbage",
        idle_timeout=float(os.getenv("WEB_SESSION_IDLE_TIMEOUT", "600")),
    )
    try:
        app = create_app(config)
    except ScriptLoadError as exc:
        raise SystemExit(f"Script load failed:\n{exc}")
    web.run_app(app, host=args.host, port=args.port, access_log_format=ACCESS_LOG_FORMAT)


if __name__ == "__main__":
    main()
