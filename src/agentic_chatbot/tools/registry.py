"""Tool registry: the single source of truth for available tools."""

from langchain_core.tools import BaseTool

from agentic_chatbot.repository import NotesRepository
from agentic_chatbot.tools.builtin import calculator, get_current_time
from agentic_chatbot.tools.life import (
    calculate_age,
    calculate_bmi,
    calculate_loan_payment,
    calculate_tip_split,
    convert_timezone,
    days_between,
    estimate_fuel_cost,
)
from agentic_chatbot.tools.mocks import (
    convert_currency,
    create_calendar_event,
    fetch_url,
    find_recipe,
    get_holidays,
    get_news,
    get_stock_price,
    get_weather,
    list_calendar_events,
    send_email,
    send_slack_message,
    track_package,
    translate_text,
    web_search,
)
from agentic_chatbot.tools.notes import create_note_tools
from agentic_chatbot.tools.utilities import (
    base64_decode,
    base64_encode,
    convert_units,
    format_json,
    generate_password,
    generate_uuid,
    hash_text,
    regex_search,
    summarize_text,
)

STATIC_TOOLS: list[BaseTool] = [
    calculator,
    get_current_time,
    web_search,
    fetch_url,
    get_news,
    get_weather,
    get_stock_price,
    convert_currency,
    send_email,
    send_slack_message,
    create_calendar_event,
    list_calendar_events,
    translate_text,
    generate_uuid,
    generate_password,
    hash_text,
    base64_encode,
    base64_decode,
    format_json,
    regex_search,
    summarize_text,
    convert_units,
    calculate_loan_payment,
    calculate_tip_split,
    calculate_bmi,
    calculate_age,
    days_between,
    convert_timezone,
    estimate_fuel_cost,
    find_recipe,
    get_holidays,
    track_package,
]


def get_tools(notes_repository: NotesRepository) -> list[BaseTool]:
    """Return every tool, including notes tools bound to the repository."""
    return [*STATIC_TOOLS, *create_note_tools(notes_repository)]
