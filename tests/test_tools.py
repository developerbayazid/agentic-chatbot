from datetime import datetime

import pytest

from agentic_chatbot.tools import get_tools
from agentic_chatbot.tools.builtin import calculator, get_current_time


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("2+2", "4"),
        ("(3 + 4) * 2", "14"),
        ("10 / 4", "2.5"),
        ("2 ** 10", "1024"),
        ("-5 + 3", "-2"),
    ],
)
def test_calculator_evaluates_arithmetic(expression, expected):
    assert calculator.invoke({"expression": expression}) == expected


def test_calculator_returns_error_string_on_invalid_input():
    result = calculator.invoke({"expression": "import os"})

    assert result.startswith("Error:")


def test_calculator_returns_error_string_on_division_by_zero():
    assert calculator.invoke({"expression": "1 / 0"}) == "Error: division by zero"


def test_get_current_time_returns_iso_timestamp():
    result = get_current_time.invoke({"timezone": "UTC"})

    assert datetime.fromisoformat(result)


def test_get_current_time_uses_local_timezone_by_default():
    result = get_current_time.invoke({})

    assert datetime.fromisoformat(result).tzinfo is not None


def test_get_current_time_returns_error_for_unknown_timezone():
    result = get_current_time.invoke({"timezone": "Not/AZone"})

    assert result == "Error: unknown timezone 'Not/AZone'"


def test_registry_exposes_every_tool():
    assert {tool.name for tool in get_tools()} == {
        "base64_decode",
        "base64_encode",
        "calculate_age",
        "calculate_bmi",
        "calculate_loan_payment",
        "calculate_tip_split",
        "calculator",
        "convert_currency",
        "convert_timezone",
        "convert_units",
        "create_calendar_event",
        "days_between",
        "delete_note",
        "estimate_fuel_cost",
        "fetch_url",
        "find_recipe",
        "format_json",
        "generate_password",
        "generate_uuid",
        "get_current_time",
        "get_holidays",
        "get_news",
        "get_stock_price",
        "get_weather",
        "hash_text",
        "list_calendar_events",
        "list_notes",
        "regex_search",
        "save_note",
        "search_notes",
        "send_email",
        "send_slack_message",
        "summarize_text",
        "track_package",
        "translate_text",
        "web_search",
    }
