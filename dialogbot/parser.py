from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .expressions import ExpressionError, validate_condition, validate_statement
from .model import (
    Button,
    ChannelLink,
    Character,
    ClearChannel,
    Dialogue,
    ExprStatement,
    If,
    IfBranch,
    InputBlock,
    InputCase,
    Jump,
    Label,
    LabelRef,
    Menu,
    MenuOption,
    Run,
    ScriptGame,
    SourceRef,
    Statement,
    TimeLimit,
    Wait,
)


class ScriptLoadError(Exception):
    pass


@dataclass
class Line:
    path: Path
    number: int
    indent: int
    text: str

    @property
    def source(self) -> SourceRef:
        return SourceRef(self.path, self.number)


def load_game(game_dir: str | Path) -> ScriptGame:
    root = Path(game_dir)
    errors: list[str] = []
    characters: dict[str, Character] = {}
    defaults: dict[str, Any] = {}
    labels: dict[tuple[str, str], Label] = {}

    for path in sorted(root.glob("*.script")):
        parsed = Parser(root, path).parse()
        errors.extend(parsed.errors)

        for key, character in parsed.characters.items():
            if key in characters:
                errors.append(f"{character.key} defined twice, second at {character.image_path or path}")
            characters[key] = character
        for key, value in parsed.defaults.items():
            if key in defaults:
                errors.append(f"default {key} defined twice in {path}")
            defaults[key] = value
        for key, label in parsed.labels.items():
            if key in labels:
                errors.append(f"label {label.display} defined twice, second at {label.source.format()}")
            labels[key] = label

    game = ScriptGame(characters=characters, defaults=defaults, labels=labels, game_dir=root)
    errors.extend(validate_game(game))
    if errors:
        raise ScriptLoadError("\n".join(errors))
    return game


@dataclass
class ParsedFile:
    characters: dict[str, Character]
    defaults: dict[str, Any]
    labels: dict[tuple[str, str], Label]
    errors: list[str]


class Parser:
    def __init__(self, game_dir: Path, path: Path) -> None:
        self.game_dir = game_dir
        self.path = path
        self.namespace = path.stem
        self.lines = preprocess(path)
        self.index = 0
        self.characters: dict[str, Character] = {}
        self.defaults: dict[str, Any] = {}
        self.labels: dict[tuple[str, str], Label] = {}
        self.errors: list[str] = []

    def parse(self) -> ParsedFile:
        while self.index < len(self.lines):
            line = self.lines[self.index]
            if line.indent != 0:
                self.error(line, "top-level statement must not be indented")
                self.index += 1
                continue
            text = line.text
            if text.startswith("define "):
                self.parse_define()
            elif text.startswith("default "):
                self.parse_default(line)
                self.index += 1
            elif text.startswith("label "):
                self.parse_label(line)
            else:
                self.error(line, f"unknown top-level statement: {text}")
                self.index += 1

        return ParsedFile(self.characters, self.defaults, self.labels, self.errors)

    def parse_define(self) -> None:
        first = self.lines[self.index]
        collected = [first.text]
        parens = first.text.count("(") - first.text.count(")")
        self.index += 1
        while self.index < len(self.lines) and parens > 0:
            line = self.lines[self.index]
            collected.append(line.text)
            parens += line.text.count("(") - line.text.count(")")
            self.index += 1

        raw = "\n".join(collected)
        match = re.match(r"define\s+([A-Za-z_]\w*)\s*=\s*Character\s*\((.*)\)\s*$", raw, re.S)
        if not match:
            self.error(first, "invalid Character definition")
            return
        key, body = match.groups()
        try:
            call = ast.parse(f"Character({body})", mode="eval").body
            if not isinstance(call, ast.Call) or len(call.args) != 1:
                raise ValueError("Character requires one display name argument")
            name = ast.literal_eval(call.args[0])
            kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call.keywords if kw.arg}
            color = kwargs["color"]
            # If no avatar key is provided, try the character key. Missing
            # files are fine; adapters can render the character without one.
            image = kwargs.get("image", key)
        except Exception as exc:
            self.error(first, f"invalid Character definition: {exc}")
            return
        if not isinstance(name, str) or not isinstance(color, str) or not isinstance(image, str):
            self.error(first, "Character name, color, and image must be strings")
            return
        self.characters[key] = Character(key, name, color, image, resolve_image(self.game_dir, image))

    def parse_default(self, line: Line) -> None:
        match = re.match(r"default\s+([A-Za-z_]\w*)\s*=\s*(.+)$", line.text)
        if not match:
            self.error(line, "invalid default statement")
            return
        name, raw_value = match.groups()
        try:
            value = ast.literal_eval(raw_value)
        except Exception as exc:
            self.error(line, f"invalid default value: {exc}")
            return
        if not isinstance(value, (bool, int, str)):
            self.error(line, "default value must be bool, int, or string")
            return
        self.defaults[name] = value

    def parse_label(self, line: Line) -> None:
        match = re.match(r'label\s+([A-Za-z_]\w*)\s*(?:\(\s*channel\s*=\s*"([^"]+)"\s*\))?\s*:\s*$', line.text)
        if not match:
            self.error(line, label_error_message(line.text))
            self.index += 1
            self.skip_indented_block(line.indent)
            return
        name, channel = match.groups()
        self.index += 1
        body = self.parse_block(line.indent)
        label = Label(self.namespace, name, channel, body, line.source)
        self.labels[label.key] = label

    def skip_indented_block(self, parent_indent: int) -> None:
        while self.index < len(self.lines) and self.lines[self.index].indent > parent_indent:
            self.index += 1

    def parse_block(self, parent_indent: int) -> list[Statement]:
        body: list[Statement] = []
        while self.index < len(self.lines):
            line = self.lines[self.index]
            if line.indent <= parent_indent:
                break
            body.append(self.parse_statement(line))
        return body

    def parse_statement(self, line: Line) -> Statement:
        text = line.text
        if text == "menu:" or text.startswith("menu timeout "):
            return self.parse_menu(line)
        if text.startswith("button "):
            return self.parse_button(line)
        if text.startswith("input "):
            return self.parse_input(line)
        if text.startswith("if "):
            return self.parse_if(line)
        if text.startswith("jump "):
            self.index += 1
            return Jump(line.source, LabelRef.parse(text[5:]))
        if text.startswith("run "):
            self.index += 1
            return Run(line.source, parse_run_targets(text[4:]))
        if text.startswith("wait "):
            self.index += 1
            return Wait(line.source, parse_number(text[5:], line, self))
        if text.startswith("clear channel "):
            self.index += 1
            return ClearChannel(line.source, parse_string_literal(text[len("clear channel ") :], line, self))
        if text.startswith("channel link "):
            self.index += 1
            return parse_channel_link(line, self)
        if text.startswith("$"):
            self.index += 1
            return ExprStatement(line.source, text[1:].strip())
        if text.startswith("time limit "):
            self.index += 1
            return TimeLimit(line.source, parse_time_limit(text, line, self))

        dialogue = re.match(r'(?:(\w+)\s+)?(".*")$', text)
        if dialogue:
            character, raw = dialogue.groups()
            self.index += 1
            return Dialogue(line.source, character, parse_string_literal(raw, line, self))

        self.error(line, f"unknown statement: {text}")
        self.index += 1
        return Dialogue(line.source, None, f"[invalid statement at {line.source.format()}]")

    def parse_menu(self, line: Line) -> Menu:
        timeout_seconds = parse_optional_timeout(line.text, "menu", line, self)
        self.index += 1
        options: list[MenuOption] = []
        timeout_body: list[Statement] | None = None
        while self.index < len(self.lines):
            option_line = self.lines[self.index]
            if option_line.indent <= line.indent:
                break
            if option_line.text == "timeout:":
                self.index += 1
                timeout_body = self.parse_block(option_line.indent)
                continue
            match = re.match(r'"((?:\\"|[^"])*)"(?:\s+if\s+(.+))?:\s*$', option_line.text)
            if not match:
                self.error(option_line, "invalid menu option")
                self.index += 1
                continue
            text, condition = match.groups()
            self.index += 1
            body = self.parse_block(option_line.indent)
            options.append(MenuOption(text.replace('\\"', '"'), condition, body, option_line.source))
        return Menu(line.source, options, timeout_seconds, timeout_body)

    def parse_button(self, line: Line) -> Button:
        match = re.match(r'button\s+"((?:\\"|[^"])*)"\s*:?\s*$', line.text)
        if not match:
            self.error(line, "invalid button statement")
            self.index += 1
            return Button(line.source, "", [])
        self.index += 1
        body = self.parse_block(line.indent)
        return Button(line.source, match.group(1).replace('\\"', '"'), body)

    def parse_input(self, line: Line) -> InputBlock:
        match = re.match(
            r'input\s+(".*")\s+into\s+([A-Za-z_]\w*)(?:\s+timeout\s+(.+?))?\s*:\s*$',
            line.text,
        )
        if not match:
            self.error(line, 'invalid input block; expected: input "Prompt" into variable:')
            self.index += 1
            return InputBlock(line.source, "", "", None, [])
        prompt_raw, variable, timeout_raw = match.groups()
        prompt = parse_string_literal(prompt_raw, line, self)
        timeout_seconds = parse_duration(timeout_raw, line, self) if timeout_raw else None
        self.index += 1
        cases: list[InputCase] = []
        while self.index < len(self.lines):
            case_line = self.lines[self.index]
            if case_line.indent <= line.indent:
                break
            match = re.match(r"case\s+(.+):\s*$", case_line.text)
            if not match:
                self.error(case_line, "invalid input case")
                self.index += 1
                continue
            raw_case = match.group(1).strip()
            if raw_case == "_":
                kind = "default"
                expression = None
            elif raw_case == "timeout":
                kind = "timeout"
                expression = None
            elif raw_case.startswith("contains "):
                kind = "contains"
                expression = raw_case[len("contains ") :].strip()
            else:
                kind = "equals"
                expression = raw_case
            self.index += 1
            cases.append(InputCase(kind, expression, self.parse_block(case_line.indent), case_line.source))
        return InputBlock(line.source, prompt, variable, timeout_seconds, cases)

    def parse_if(self, line: Line) -> If:
        branches: list[IfBranch] = []
        while self.index < len(self.lines):
            branch_line = self.lines[self.index]
            if branch_line.indent != line.indent:
                break
            if branch_line.text.startswith("if "):
                condition = branch_line.text[3:].removesuffix(":").strip()
            elif branch_line.text.startswith("elif "):
                condition = branch_line.text[5:].removesuffix(":").strip()
            elif branch_line.text == "else:":
                condition = None
            else:
                break
            if not branch_line.text.endswith(":"):
                self.error(branch_line, "if/elif/else branch must end with ':'")
            self.index += 1
            branches.append(IfBranch(condition, self.parse_block(branch_line.indent), branch_line.source))
        return If(line.source, branches)

    def error(self, line: Line, message: str) -> None:
        self.errors.append(f"{line.source.format()}: {message}")


def preprocess(path: Path) -> list[Line]:
    lines: list[Line] = []
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        stripped = strip_comment(raw.expandtabs(4)).rstrip()
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append(Line(path, number, indent, stripped.strip()))
    return lines


def strip_comment(line: str) -> str:
    in_string = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if char == "#" and not in_string:
            return line[:index]
    return line


def resolve_image(game_dir: Path, basename: str) -> Path | None:
    for extension in ("png", "jpg", "jpeg", "gif", "webp"):
        candidate = game_dir / "images" / f"{basename}.{extension}"
        if candidate.exists():
            return candidate
    return None


def parse_string_literal(raw: str, line: Line, parser: Parser) -> str:
    try:
        value = ast.literal_eval(raw)
    except Exception as exc:
        parser.error(line, f"invalid string literal: {exc}")
        return ""
    if not isinstance(value, str):
        parser.error(line, "expected string literal")
        return ""
    return value


def parse_number(raw: str, line: Line, parser: Parser) -> float:
    try:
        return float(raw)
    except ValueError:
        parser.error(line, "expected numeric value")
        return 0


def parse_time_limit(text: str, line: Line, parser: Parser) -> float:
    match = re.match(r"time\s+limit\s+(\d+(?:\.\d+)?)\s+(seconds?|minutes?|hours?)$", text)
    if not match:
        parser.error(line, "invalid time limit")
        return 0
    amount = float(match.group(1))
    unit = match.group(2)
    if unit.startswith("minute"):
        return amount * 60
    if unit.startswith("hour"):
        return amount * 3600
    return amount


def parse_duration(raw: str, line: Line, parser: Parser) -> float:
    match = re.match(r"(\d+(?:\.\d+)?)(?:\s+(seconds?|minutes?|hours?))?$", raw.strip())
    if not match:
        parser.error(line, "invalid duration")
        return 0
    amount = float(match.group(1))
    unit = match.group(2) or "seconds"
    if unit.startswith("minute"):
        return amount * 60
    if unit.startswith("hour"):
        return amount * 3600
    return amount


def label_error_message(text: str) -> str:
    expected = 'expected: label name(channel="Channel Name"): or label setup:'
    if not text.endswith(":"):
        return f"invalid label declaration; label declarations must end with ':'. {expected}"

    match = re.match(r"label\s+([A-Za-z_]\w*)\s*\((.*)\)\s*:\s*$", text)
    if match:
        raw_args = match.group(2)
        if re.search(r"\bChannel\s*=", raw_args):
            return 'invalid label declaration; use lowercase channel=, for example: label start(channel="Room"):'
        if "channel" in raw_args:
            return 'invalid label declaration; channel must be written as channel="Room"'
        return f"invalid label declaration; unsupported label parameter list ({raw_args!r}). {expected}"

    return f"invalid label declaration; {expected}"


def parse_optional_timeout(text: str, keyword: str, line: Line, parser: Parser) -> float | None:
    if text == f"{keyword}:":
        return None
    match = re.match(rf"{keyword}\s+timeout\s+(.+):\s*$", text)
    if not match:
        parser.error(line, f"invalid {keyword} timeout")
        return None
    return parse_duration(match.group(1), line, parser)


def parse_channel_link(line: Line, parser: Parser) -> ChannelLink:
    match = re.match(r'channel\s+link\s+(".*")\s+to\s+(".*")$', line.text)
    if not match:
        parser.error(line, 'invalid channel link; expected: channel link "Label" to "Channel"')
        return ChannelLink(line.source, "", "")
    label_raw, channel_raw = match.groups()
    return ChannelLink(
        line.source,
        parse_string_literal(label_raw, line, parser),
        parse_string_literal(channel_raw, line, parser),
    )


def parse_run_targets(raw: str) -> list[LabelRef]:
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        return [LabelRef.parse(part.strip()) for part in raw[1:-1].split(",") if part.strip()]
    return [LabelRef.parse(raw)]


def validate_game(game: ScriptGame) -> list[str]:
    errors: list[str] = []
    if ("main", "setup") not in game.labels:
        errors.append("missing entry point label main.setup")

    for label in game.labels.values():
        if label.name != "setup" and not label.channel:
            errors.append(f"{label.source.format()}: label {label.display} must declare channel")
        if label.name == "setup" and label.channel:
            errors.append(f"{label.source.format()}: setup label must not declare channel")
        errors.extend(validate_statements(game, label, label.body))
    return errors


def validate_statements(game: ScriptGame, label: Label, statements: list[Statement]) -> list[str]:
    errors: list[str] = []
    for statement in statements:
        try:
            if isinstance(statement, Dialogue):
                if statement.character and statement.character not in game.characters:
                    errors.append(f"{statement.source.format()}: unknown character {statement.character}")
                validate_interpolation(statement.text, game.defaults)
            elif isinstance(statement, Jump):
                resolve_label(game, label.namespace, statement.target)
            elif isinstance(statement, Run):
                for target in statement.targets:
                    resolve_label(game, label.namespace, target)
            elif isinstance(statement, Menu):
                if statement.timeout_body and statement.timeout_seconds is None:
                    errors.append(f"{statement.source.format()}: menu timeout branch requires menu timeout")
                for option in statement.options:
                    if option.condition:
                        validate_condition(option.condition, game.defaults)
                    errors.extend(validate_statements(game, label, option.body))
                if statement.timeout_body:
                    errors.extend(validate_statements(game, label, statement.timeout_body))
            elif isinstance(statement, Button):
                errors.extend(validate_statements(game, label, statement.body))
            elif isinstance(statement, InputBlock):
                if statement.variable not in game.defaults:
                    errors.append(f"{statement.source.format()}: unknown input variable {statement.variable}")
                for case in statement.cases:
                    if case.kind == "timeout" and statement.timeout_seconds is None:
                        errors.append(f"{case.source.format()}: input timeout case requires input timeout")
                    if case.kind == "contains" and case.expression:
                        validate_condition(f"{statement.variable} contains {case.expression}", game.defaults)
                    elif case.kind == "equals" and case.expression:
                        validate_condition(case.expression, game.defaults)
                    errors.extend(validate_statements(game, label, case.body))
            elif isinstance(statement, If):
                for branch in statement.branches:
                    if branch.condition:
                        validate_condition(branch.condition, game.defaults)
                    errors.extend(validate_statements(game, label, branch.body))
            elif isinstance(statement, ExprStatement):
                validate_statement(statement.expression, game.defaults)
        except (ScriptLoadError, ExpressionError) as exc:
            errors.append(f"{statement.source.format()}: {exc}")
    return errors


def resolve_label(game: ScriptGame, current_namespace: str, target: LabelRef) -> Label:
    candidates: list[tuple[str, str]]
    if target.namespace:
        candidates = [(target.namespace, target.name)]
    else:
        candidates = [(current_namespace, target.name), ("main", target.name)]
    for candidate in candidates:
        if candidate in game.labels:
            return game.labels[candidate]
    raise ScriptLoadError(f"unknown label {target.display()}")


def validate_interpolation(text: str, defaults: dict[str, Any]) -> None:
    for expression in re.findall(r"\$\(([^)]+)\)", text):
        validate_condition(expression, defaults)
    for name in re.findall(r"\$([A-Za-z_]\w*)", text):
        if name not in defaults:
            raise ExpressionError(f"unknown variable {name}")
