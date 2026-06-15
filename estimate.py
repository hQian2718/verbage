# Copyright (C) 2026 Kuan Qian
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from dialogbot.config import GameConfig
from dialogbot.model import (
    Button,
    ChannelLink,
    ClearChannel,
    Continue,
    Dialogue,
    ExprStatement,
    If,
    InputBlock,
    Jump,
    Label,
    LabelRef,
    Menu,
    Run,
    ShowImage,
    Statement,
    TimeLimit,
    Wait,
)
from dialogbot.parser import ScriptLoadError, load_game, resolve_label

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv() -> bool:
        return False


@dataclass(frozen=True)
class EstimateStep:
    source: str
    kind: str
    seconds: float
    detail: str


@dataclass(frozen=True)
class Estimate:
    label: Label
    seconds: float
    steps: list[EstimateStep]
    notes: list[str]


def estimate_label(label: Label, config: GameConfig) -> Estimate:
    steps: list[EstimateStep] = []
    notes: list[str] = []
    seconds = estimate_statements(label.body, config, steps, notes)
    return Estimate(label, seconds, steps, notes)


def estimate_statements(
    statements: list[Statement],
    config: GameConfig,
    steps: list[EstimateStep],
    notes: list[str],
) -> float:
    total = 0.0
    for statement in statements:
        if isinstance(statement, Dialogue):
            seconds = dialogue_seconds(statement.text, config)
            steps.append(
                EstimateStep(
                    statement.source.format(),
                    "dialogue",
                    seconds,
                    f"{len(statement.text)} chars",
                )
            )
            total += seconds
        elif isinstance(statement, Wait):
            seconds = statement.seconds * config.wait_scale
            steps.append(EstimateStep(statement.source.format(), "wait", seconds, "script wait"))
            total += seconds
        elif isinstance(statement, Jump):
            notes.append(f"{statement.source.format()}: jumps to {statement.target.display()}; target not included.")
            break
        elif isinstance(statement, Run):
            targets = ", ".join(target.display() for target in statement.targets)
            notes.append(f"{statement.source.format()}: runs concurrent labels ({targets}); branch duration not estimated.")
            break
        elif isinstance(statement, Menu):
            notes.append(f"{statement.source.format()}: menu branches on player choice; option bodies not estimated.")
            break
        elif isinstance(statement, Button):
            timeout = f" Timeout: {format_seconds(statement.timeout_seconds)}." if statement.timeout_seconds else ""
            notes.append(f"{statement.source.format()}: button waits for player input; body not estimated.{timeout}")
            break
        elif isinstance(statement, InputBlock):
            timeout = f" Timeout: {format_seconds(statement.timeout_seconds)}." if statement.timeout_seconds else ""
            notes.append(f"{statement.source.format()}: input branches on player text; cases not estimated.{timeout}")
            break
        elif isinstance(statement, If):
            notes.append(f"{statement.source.format()}: conditional branch; branch bodies not estimated.")
            break
        elif isinstance(statement, Continue):
            notes.append(f"{statement.source.format()}: continue exits a menu; following path depends on the menu.")
            break
        elif isinstance(statement, (ChannelLink, ClearChannel, ExprStatement, ShowImage, TimeLimit)):
            continue
        else:
            notes.append(f"{statement.source.format()}: unsupported statement {type(statement).__name__}; stopped.")
            break
    return total


def dialogue_seconds(text: str, config: GameConfig) -> float:
    return config.dialogue_seconds(text)


def format_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "none"
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}m {rest:.1f}s"


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Estimate straight-line runtime for a script label.")
    parser.add_argument("label", help='Label name, such as "start" or "act_1.begin".')
    parser.add_argument("--game-dir", default="game", help="Directory containing *.script files.")
    args = parser.parse_args()

    try:
        game = load_game(args.game_dir)
        label = resolve_label(game, "main", LabelRef.parse(args.label))
    except ScriptLoadError as exc:
        print(f"Estimate failed:\n{exc}", file=sys.stderr)
        return 1

    config = GameConfig.from_env()
    estimate = estimate_label(label, config)
    print(f"Label: {estimate.label.display} ({estimate.label.source.format()})")
    print(f"Estimated straight-line time: {format_seconds(estimate.seconds)}")
    print(
        "Timing config: "
        f"per_char={config.delay_per_char}, min={config.min_delay}, max={config.max_delay}, "
        f"typing={config.typing_delay}, wait_scale={config.wait_scale}"
    )
    if estimate.steps:
        print("\nBreakdown:")
        for step in estimate.steps:
            print(f"- {step.source}: {step.kind} {format_seconds(step.seconds)} ({step.detail})")
    if estimate.notes:
        print("\nNotes:")
        for note in estimate.notes:
            print(f"- {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
