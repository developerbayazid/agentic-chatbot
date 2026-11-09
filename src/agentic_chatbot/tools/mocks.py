"""Mock implementations of common external-service tools.

Every tool here returns simulated data so the agent can exercise realistic
workflows without API keys. Replace the body of a tool with a real client call
once the matching credentials are configured; the signatures and return shape
can stay the same.
"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import quote_plus

from langchain_core.tools import tool

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Simulated units per US dollar. Replace with a live rates API when available.
_EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 151.0,
    "BDT": 117.0,
    "INR": 83.0,
    "CAD": 1.36,
    "AUD": 1.52,
    "CNY": 7.24,
}

# In-memory calendar used by create_calendar_event / list_calendar_events.
_MOCK_CALENDAR: dict[str, dict] = {}


def _stable_seed(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def _to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web and return ranked results.

    Mock implementation: results are simulated until a search API key is set.
    """
    count = max(1, min(num_results, 10))
    results = [
        {
            "title": f"{query} — result {index}",
            "url": (
                f"https://example.com/search?q={quote_plus(query)}"
                f"&result={index}"
            ),
            "snippet": f"Simulated snippet {index} for '{query}'.",
        }
        for index in range(1, count + 1)
    ]

    return _to_json({"query": query, "results": results, "mock": True})


@tool
def fetch_url(url: str) -> str:
    """Fetch a web page and return its title and main text.

    Mock implementation: returns simulated page content. Only http(s) URLs are
    accepted.
    """
    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://."

    return _to_json(
        {
            "url": url,
            "status": 200,
            "title": f"Mock page for {url}",
            "content": (
                "This is simulated page content. Configure a real HTTP client "
                "or scraping service to retrieve actual content."
            ),
            "mock": True,
        }
    )


@tool
def get_news(topic: str = "general", limit: int = 5) -> str:
    """Get recent headlines for a topic.

    Mock implementation: headlines are simulated until a news API key is set.
    """
    count = max(1, min(limit, 10))
    today = datetime.now(timezone.utc).date().isoformat()

    articles = [
        {
            "title": f"{topic.title()} headline {index}",
            "source": "Mock News",
            "published": today,
            "summary": f"Simulated summary for {topic} story {index}.",
        }
        for index in range(1, count + 1)
    ]

    return _to_json({"topic": topic, "articles": articles, "mock": True})


@tool
def get_weather(location: str, unit: str = "celsius") -> str:
    """Get the current weather for a location.

    Mock implementation: values are derived deterministically from the location
    name until a weather API key is set. Unit is "celsius" or "fahrenheit".
    """
    if not location.strip():
        return "Error: location is required."

    unit = unit.strip().lower()
    if unit not in ("celsius", "fahrenheit"):
        return "Error: unit must be 'celsius' or 'fahrenheit'."

    seed = _stable_seed(location.strip().lower())
    celsius = 10 + seed % 21
    temperature = celsius if unit == "celsius" else round(celsius * 9 / 5 + 32, 1)
    conditions = ["sunny", "partly cloudy", "cloudy", "light rain", "windy"]

    return _to_json(
        {
            "location": location,
            "temperature": temperature,
            "unit": unit,
            "condition": conditions[seed % len(conditions)],
            "humidity_percent": 40 + seed % 50,
            "wind_kph": round(5 + (seed % 250) / 10, 1),
            "mock": True,
        }
    )


@tool
def get_stock_price(symbol: str) -> str:
    """Get a stock quote for a ticker symbol.

    Mock implementation: price and change are simulated until a market data API
    key is set.
    """
    ticker = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z.\-]{1,10}", ticker):
        return f"Error: invalid ticker symbol '{symbol}'."

    seed = _stable_seed(ticker)
    price = round(10 + (seed % 49000) / 100, 2)
    change = round(((seed % 700) - 350) / 100, 2)

    return _to_json(
        {
            "symbol": ticker,
            "price": price,
            "change": change,
            "change_percent": round(change / price * 100, 2),
            "currency": "USD",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "mock": True,
        }
    )


@tool
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount between currencies using mock exchange rates.

    Supported currencies: USD, EUR, GBP, JPY, BDT, INR, CAD, AUD, CNY.
    """
    source = from_currency.strip().upper()
    target = to_currency.strip().upper()

    if source not in _EXCHANGE_RATES or target not in _EXCHANGE_RATES:
        supported = ", ".join(sorted(_EXCHANGE_RATES))
        return f"Error: unsupported currency. Supported: {supported}."

    if amount < 0:
        return "Error: amount must not be negative."

    rate = _EXCHANGE_RATES[target] / _EXCHANGE_RATES[source]

    return _to_json(
        {
            "amount": amount,
            "from": source,
            "to": target,
            "rate": round(rate, 6),
            "converted": round(amount * rate, 2),
            "mock": True,
        }
    )


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email.

    Mock implementation: validates the address and reports a queued message;
    no email is actually sent. Configure an email provider to send for real.
    """
    address = to.strip()
    if not _EMAIL_PATTERN.fullmatch(address):
        return f"Error: invalid email address '{to}'."

    if not subject.strip():
        return "Error: subject is required."

    return _to_json(
        {
            "message_id": str(uuid.uuid4()),
            "to": address,
            "subject": subject,
            "status": "queued",
            "mock": True,
        }
    )


@tool
def send_slack_message(channel: str, text: str) -> str:
    """Send a message to a Slack channel.

    Mock implementation: reports a simulated delivery; no message is sent until
    a Slack token is configured.
    """
    if not channel.strip():
        return "Error: channel is required."

    if not text.strip():
        return "Error: text is required."

    return _to_json(
        {
            "channel": channel,
            "text": text,
            "ts": datetime.now(timezone.utc).timestamp(),
            "status": "delivered",
            "mock": True,
        }
    )


@tool
def create_calendar_event(
    title: str,
    start_time: str,
    duration_minutes: int = 30,
    location: str = "",
) -> str:
    """Create a calendar event in the in-memory mock calendar.

    start_time is an ISO 8601 timestamp (for example 2026-11-09T15:00:00).
    """
    if not title.strip():
        return "Error: title is required."

    if duration_minutes <= 0:
        return "Error: duration_minutes must be positive."

    event = {
        "event_id": str(uuid.uuid4()),
        "title": title,
        "start_time": start_time,
        "duration_minutes": duration_minutes,
        "location": location,
        "mock": True,
    }
    _MOCK_CALENDAR[event["event_id"]] = event

    return _to_json(event)


@tool
def list_calendar_events(date: str | None = None) -> str:
    """List events from the in-memory mock calendar.

    Optionally pass a date prefix such as 2026-11-09 to filter events.
    """
    events = list(_MOCK_CALENDAR.values())

    if date:
        events = [
            event for event in events if event["start_time"].startswith(date)
        ]

    return _to_json({"events": events, "count": len(events), "mock": True})


@tool
def find_recipe(query: str, max_results: int = 3) -> str:
    """Search for recipes by dish or ingredient.

    Mock implementation: recipes are simulated until a recipe API key is set.
    """
    if not query.strip():
        return "Error: query is required."

    count = max(1, min(max_results, 5))
    recipes = [
        {
            "title": f"{query.title()} recipe {index}",
            "servings": 2,
            "ingredients": [
                f"1 portion {query}",
                "1 tbsp olive oil",
                "Salt and pepper to taste",
            ],
            "steps": [
                "Prepare the ingredients.",
                "Cook until done and season to taste.",
            ],
            "mock": True,
        }
        for index in range(1, count + 1)
    ]

    return _to_json({"query": query, "recipes": recipes, "mock": True})


@tool
def get_holidays(country: str = "US", year: int | None = None) -> str:
    """List public holidays for a country and year.

    Mock implementation: returns a short sample of holidays for US, UK, BD, IN,
    or CA until a holiday calendar API is configured.
    """
    holidays = {
        "US": [
            ("New Year's Day", "01-01"),
            ("Independence Day", "07-04"),
            ("Christmas Day", "12-25"),
        ],
        "UK": [
            ("New Year's Day", "01-01"),
            ("Christmas Day", "12-25"),
            ("Boxing Day", "12-26"),
        ],
        "BD": [
            ("Language Martyrs' Day", "02-21"),
            ("Independence Day", "03-26"),
            ("Victory Day", "12-16"),
        ],
        "IN": [
            ("Republic Day", "01-26"),
            ("Independence Day", "08-15"),
            ("Gandhi Jayanti", "10-02"),
        ],
        "CA": [
            ("New Year's Day", "01-01"),
            ("Canada Day", "07-01"),
            ("Christmas Day", "12-25"),
        ],
    }

    code = country.strip().upper()
    if code not in holidays:
        supported = ", ".join(sorted(holidays))
        return f"Error: unsupported country. Supported: {supported}."

    target_year = year or datetime.now(timezone.utc).year
    entries = [
        {"name": name, "date": f"{target_year}-{month_day}"}
        for name, month_day in holidays[code]
    ]

    return _to_json(
        {
            "country": code,
            "year": target_year,
            "holidays": entries,
            "mock": True,
        }
    )


@tool
def track_package(tracking_number: str) -> str:
    """Track a parcel by its tracking number.

    Mock implementation: status and events are simulated until a carrier API
    integration is configured.
    """
    number = tracking_number.strip().upper()
    if not re.fullmatch(r"[A-Z0-9\-]{5,30}", number):
        return f"Error: invalid tracking number '{tracking_number}'."

    seed = _stable_seed(number)
    statuses = ["in_transit", "out_for_delivery", "delivered"]
    status = statuses[seed % len(statuses)]

    events = [
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "location": "Origin facility",
            "description": "Parcel accepted",
        },
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "location": "Regional hub",
            "description": f"Status: {status.replace('_', ' ')}",
        },
    ]

    return _to_json(
        {
            "tracking_number": number,
            "status": status,
            "events": events,
            "mock": True,
        }
    )


@tool
def translate_text(
    text: str,
    target_language: str,
    source_language: str = "auto",
) -> str:
    """Translate text into a target language.

    Mock implementation: returns the input marked as a simulated translation
    until a translation API key is configured.
    """
    if not text.strip():
        return "Error: text is empty."

    if not target_language.strip():
        return "Error: target_language is required."

    return _to_json(
        {
            "translated_text": f"[mock {target_language}] {text}",
            "source_language": source_language,
            "target_language": target_language,
            "note": "Simulated translation; configure a translation API for real output.",
            "mock": True,
        }
    )
