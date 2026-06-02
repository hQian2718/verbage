from __future__ import annotations

import argparse
import sys

from dialogbot.parser import ScriptLoadError, load_game


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse dialog game scripts and report errors.")
    parser.add_argument("game_dir", nargs="?", default="game", help="Directory containing *.script files.")
    args = parser.parse_args()

    try:
        game = load_game(args.game_dir)
    except ScriptLoadError as exc:
        print("Script load failed:", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1

    image_count = sum(1 for character in game.characters.values() if character.image_path is not None)
    print(
        f"Loaded {len(game.labels)} labels, {len(game.characters)} characters, "
        f"{image_count} images, and {len(game.defaults)} defaults from {args.game_dir}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
