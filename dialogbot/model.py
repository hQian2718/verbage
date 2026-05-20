from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceRef:
    path: Path
    line: int

    def format(self) -> str:
        return f"{self.path}:{self.line}"


@dataclass(frozen=True)
class Character:
    key: str
    name: str
    color: str
    image: str
    image_path: Path | None


@dataclass(frozen=True)
class LabelRef:
    namespace: str | None
    name: str

    @classmethod
    def parse(cls, raw: str) -> "LabelRef":
        raw = raw.strip()
        if "." in raw:
            namespace, name = raw.split(".", 1)
            return cls(namespace, name)
        return cls(None, raw)

    def display(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name


@dataclass
class ScriptGame:
    characters: dict[str, Character]
    defaults: dict[str, Any]
    labels: dict[tuple[str, str], "Label"]
    game_dir: Path


@dataclass
class Label:
    namespace: str
    name: str
    channel: str | None
    body: list["Statement"]
    source: SourceRef

    @property
    def key(self) -> tuple[str, str]:
        return (self.namespace, self.name)

    @property
    def display(self) -> str:
        return f"{self.namespace}.{self.name}"


@dataclass
class Statement:
    source: SourceRef


@dataclass
class Dialogue(Statement):
    character: str | None
    text: str


@dataclass
class Jump(Statement):
    target: LabelRef


@dataclass
class Run(Statement):
    targets: list[LabelRef]


@dataclass
class MenuOption:
    text: str
    condition: str | None
    body: list[Statement]
    source: SourceRef


@dataclass
class Menu(Statement):
    options: list[MenuOption]


@dataclass
class Button(Statement):
    text: str
    body: list[Statement]


@dataclass
class IfBranch:
    condition: str | None
    body: list[Statement]
    source: SourceRef


@dataclass
class If(Statement):
    branches: list[IfBranch]


@dataclass
class Wait(Statement):
    seconds: float


@dataclass
class ClearChannel(Statement):
    channel: str


@dataclass
class ChannelLink(Statement):
    text: str
    channel: str


@dataclass
class ExprStatement(Statement):
    expression: str


@dataclass
class TimeLimit(Statement):
    seconds: float
