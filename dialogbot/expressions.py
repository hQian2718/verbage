# Copyright (C) 2026 Placeholder Name
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import ast
import operator
import re
from typing import Any, Protocol


class ExpressionError(Exception):
    pass


class EvalContext(Protocol):
    async def get_var(self, name: str) -> Any: ...
    async def set_var(self, name: str, value: Any) -> None: ...
    async def wait_for_input(self, prompt: str | None = None) -> str: ...
    def username(self) -> str: ...


ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

ALLOWED_CMPOPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def validate_condition(expression: str, defaults: dict[str, Any]) -> None:
    validate_expr_text(expression, defaults)


def validate_statement(statement: str, defaults: dict[str, Any]) -> None:
    try:
        tree = ast.parse(statement, mode="exec")
    except SyntaxError as exc:
        raise ExpressionError(str(exc)) from exc
    if len(tree.body) != 1 or not isinstance(tree.body[0], (ast.Assign, ast.AugAssign)):
        raise ExpressionError("expression statement must be an assignment")
    node = tree.body[0]
    target = node.targets[0] if isinstance(node, ast.Assign) else node.target
    if not isinstance(target, ast.Name):
        raise ExpressionError("assignment target must be a variable")
    if target.id not in defaults:
        raise ExpressionError(f"unknown variable {target.id}")
    value = node.value
    validate_ast(value, defaults)


async def eval_condition(expression: str, context: EvalContext) -> Any:
    # contains is script syntax, not Python syntax, so handle it before using the
    # Python AST for the rest of the restricted expression language.
    if has_contains(expression):
        return await eval_contains(expression, context)
    return await eval_expr_text(expression, context)


async def exec_statement(statement: str, context: EvalContext) -> None:
    tree = ast.parse(statement, mode="exec")
    node = tree.body[0]
    if isinstance(node, ast.Assign):
        target = node.targets[0]
        assert isinstance(target, ast.Name)
        value = await eval_node(node.value, context)
        await context.set_var(target.id, value)
        return
    if isinstance(node, ast.AugAssign):
        target = node.target
        assert isinstance(target, ast.Name)
        current = await context.get_var(target.id)
        value = await eval_node(node.value, context)
        op = ALLOWED_BINOPS.get(type(node.op))
        if not op:
            raise ExpressionError("unsupported assignment operator")
        await context.set_var(target.id, op(current, value))
        return
    raise ExpressionError("unsupported expression statement")


async def eval_expr_text(expression: str, context: EvalContext) -> Any:
    tree = ast.parse(expression, mode="eval")
    return await eval_node(tree.body, context)


def validate_expr_text(expression: str, defaults: dict[str, Any]) -> None:
    if has_contains(expression):
        left, alternatives = split_contains(expression)
        # input() blocks on Discord messages. The MVP allows at most one blocking
        # read in a single expression so evaluation order stays obvious.
        input_count = count_builtin_calls(left, "input")
        input_count += sum(count_builtin_calls(item, "input") for item in alternatives)
        if input_count > 1:
            raise ExpressionError("contains expression may call input() at most once")
        validate_expr_text(left, defaults)
        for item in alternatives:
            validate_expr_text(item, defaults)
        return
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(str(exc)) from exc
    validate_ast(tree.body, defaults)


def validate_ast(node: ast.AST, defaults: dict[str, Any]) -> None:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (bool, int, str)):
            raise ExpressionError("literal must be bool, int, or string")
        return
    if isinstance(node, ast.Name):
        if node.id not in defaults:
            raise ExpressionError(f"unknown variable {node.id}")
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in ALLOWED_BINOPS:
            raise ExpressionError("unsupported operator")
        validate_ast(node.left, defaults)
        validate_ast(node.right, defaults)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub, ast.UAdd)):
        validate_ast(node.operand, defaults)
        return
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        for value in node.values:
            validate_ast(value, defaults)
        return
    if isinstance(node, ast.Compare):
        validate_ast(node.left, defaults)
        for op, comparator in zip(node.ops, node.comparators):
            if type(op) not in ALLOWED_CMPOPS:
                raise ExpressionError("unsupported comparison")
            validate_ast(comparator, defaults)
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in {"input", "username"}:
            raise ExpressionError("unsupported function call")
        if node.keywords:
            raise ExpressionError("built-ins do not take keyword arguments")
        if node.func.id == "username" and node.args:
            raise ExpressionError("username() does not take arguments")
        if node.func.id == "input":
            if len(node.args) > 1:
                raise ExpressionError("input() accepts at most one prompt argument")
            if node.args and not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                raise ExpressionError("input() prompt must be a string literal")
        return
    raise ExpressionError(f"unsupported expression: {type(node).__name__}")


async def eval_node(node: ast.AST, context: EvalContext) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return await context.get_var(node.id)
    if isinstance(node, ast.BinOp):
        op = ALLOWED_BINOPS[type(node.op)]
        return op(await eval_node(node.left, context), await eval_node(node.right, context))
    if isinstance(node, ast.UnaryOp):
        value = await eval_node(node.operand, context)
        if isinstance(node.op, ast.Not):
            return not value
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return +value
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for value_node in node.values:
                value = await eval_node(value_node, context)
                if not value:
                    return value
            return value
        for value_node in node.values:
            value = await eval_node(value_node, context)
            if value:
                return value
        return value
    if isinstance(node, ast.Compare):
        left = await eval_node(node.left, context)
        for op_node, comparator in zip(node.ops, node.comparators):
            right = await eval_node(comparator, context)
            if not ALLOWED_CMPOPS[type(op_node)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "input":
            prompt = node.args[0].value if node.args else None
            return await context.wait_for_input(prompt)
        if node.func.id == "username":
            return context.username()
    raise ExpressionError(f"unsupported expression: {type(node).__name__}")


def has_contains(expression: str) -> bool:
    return re.search(r"\scontains\s", expression) is not None


def split_contains(expression: str) -> tuple[str, list[str]]:
    # X contains A or B or C means:
    # (X contains A) or (X contains B) or (X contains C)
    left, right = re.split(r"\scontains\s", expression, maxsplit=1)
    alternatives = split_top_level_or(right)
    if not left.strip() or not alternatives:
        raise ExpressionError("invalid contains expression")
    return left.strip(), alternatives


async def eval_contains(expression: str, context: EvalContext) -> bool:
    left_text, alternatives = split_contains(expression)
    haystack = str(await eval_expr_text(left_text, context)).lower()
    for item in alternatives:
        needle = str(await eval_expr_text(item, context)).lower()
        if needle in haystack:
            return True
    return False


def split_top_level_or(expression: str) -> list[str]:
    # Split only the distributed "or" terms for contains. Ignore "or" inside
    # strings and parentheses so normal sub-expressions survive intact.
    parts: list[str] = []
    in_string = False
    escaped = False
    depth = 0
    start = 0
    index = 0
    while index < len(expression):
        char = expression[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif depth == 0 and expression[index : index + 4] == " or ":
                parts.append(expression[start:index].strip())
                index += 3
                start = index + 1
        index += 1
    parts.append(expression[start:].strip())
    return [part for part in parts if part]


def count_builtin_calls(expression: str, name: str) -> int:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(str(exc)) from exc
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
    )
