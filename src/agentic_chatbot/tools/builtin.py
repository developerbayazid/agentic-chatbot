"""Built-in tools available to the chat model."""

import ast
import operator
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _evaluate(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body)

    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value

    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        operation = _BINARY_OPERATORS[type(node.op)]
        return operation(_evaluate(node.left), _evaluate(node.right))

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        operation = _UNARY_OPERATORS[type(node.op)]
        return operation(_evaluate(node.operand))

    raise ValueError(f"unsupported expression element: {type(node).__name__}")


@tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression and return the result.

    Supports numbers, parentheses, and the operators +, -, *, /, //, %, and **.
    """
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_evaluate(tree))
    except Exception as error:
        return f"Error: {error}"


@tool
def get_current_time(timezone: str | None = None) -> str:
    """Return the current date and time in ISO 8601 format.

    Optionally pass an IANA timezone name such as "Asia/Dhaka" or "UTC".
    Without one, the server's local timezone is used.
    """
    try:
        if timezone:
            moment = datetime.now(ZoneInfo(timezone))
        else:
            moment = datetime.now().astimezone()
    except ZoneInfoNotFoundError:
        return f"Error: unknown timezone '{timezone}'"

    return moment.isoformat()
