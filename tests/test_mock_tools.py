import json

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


def test_web_search_returns_requested_mock_results():
    payload = json.loads(
        web_search.invoke({"query": "langgraph", "num_results": 3})
    )

    assert payload["mock"] is True
    assert payload["query"] == "langgraph"
    assert len(payload["results"]) == 3


def test_fetch_url_validates_scheme_and_returns_mock_page():
    assert fetch_url.invoke({"url": "ftp://example.com"}).startswith("Error:")

    payload = json.loads(fetch_url.invoke({"url": "https://example.com"}))
    assert payload["status"] == 200
    assert payload["mock"] is True


def test_get_news_returns_requested_count():
    payload = json.loads(get_news.invoke({"topic": "ai", "limit": 2}))

    assert payload["topic"] == "ai"
    assert len(payload["articles"]) == 2
    assert payload["mock"] is True


def test_get_weather_is_deterministic_and_converts_units():
    celsius = json.loads(
        get_weather.invoke({"location": "Dhaka", "unit": "celsius"})
    )
    fahrenheit = json.loads(
        get_weather.invoke({"location": "Dhaka", "unit": "fahrenheit"})
    )

    assert fahrenheit["temperature"] == round(celsius["temperature"] * 9 / 5 + 32, 1)
    assert celsius["mock"] is True


def test_get_weather_rejects_unknown_unit():
    assert get_weather.invoke(
        {"location": "Dhaka", "unit": "kelvin"}
    ).startswith("Error:")


def test_get_stock_price_validates_symbol():
    assert get_stock_price.invoke({"symbol": "!!"}).startswith("Error:")

    payload = json.loads(get_stock_price.invoke({"symbol": "aapl"}))
    assert payload["symbol"] == "AAPL"
    assert payload["mock"] is True


def test_convert_currency_uses_mock_rate():
    payload = json.loads(
        convert_currency.invoke(
            {"amount": 100, "from_currency": "usd", "to_currency": "eur"}
        )
    )

    assert payload["from"] == "USD"
    assert payload["rate"] == 0.92
    assert payload["converted"] == 92.0


def test_convert_currency_rejects_unknown_currency():
    result = convert_currency.invoke(
        {"amount": 10, "from_currency": "USD", "to_currency": "XYZ"}
    )

    assert result.startswith("Error:")


def test_send_email_validates_address():
    assert send_email.invoke(
        {"to": "not-an-email", "subject": "Hi", "body": "Hello"}
    ).startswith("Error:")

    payload = json.loads(
        send_email.invoke(
            {"to": "user@example.com", "subject": "Hi", "body": "Hello"}
        )
    )
    assert payload["status"] == "queued"
    assert payload["mock"] is True


def test_send_slack_message_requires_channel_and_text():
    assert send_slack_message.invoke(
        {"channel": "", "text": "hello"}
    ).startswith("Error:")
    assert send_slack_message.invoke(
        {"channel": "#general", "text": ""}
    ).startswith("Error:")

    payload = json.loads(
        send_slack_message.invoke({"channel": "#general", "text": "hello"})
    )
    assert payload["status"] == "delivered"


def test_calendar_create_and_list_round_trip():
    created = json.loads(
        create_calendar_event.invoke(
            {
                "title": "Design review",
                "start_time": "2026-12-01T10:00:00",
                "duration_minutes": 45,
            }
        )
    )

    assert created["title"] == "Design review"

    listed = json.loads(
        list_calendar_events.invoke({"date": "2026-12-01"})
    )

    assert any(
        event["event_id"] == created["event_id"] for event in listed["events"]
    )


def test_create_calendar_event_rejects_invalid_duration():
    assert create_calendar_event.invoke(
        {"title": "Bad", "start_time": "2026-12-01T10:00:00", "duration_minutes": 0}
    ).startswith("Error:")


def test_translate_text_marks_mock_output():
    payload = json.loads(
        translate_text.invoke(
            {"text": "Hello", "target_language": "Spanish"}
        )
    )

    assert payload["translated_text"] == "[mock Spanish] Hello"
    assert payload["mock"] is True


def test_find_recipe_returns_requested_count():
    payload = json.loads(
        find_recipe.invoke({"query": "chicken curry", "max_results": 2})
    )

    assert len(payload["recipes"]) == 2
    assert payload["mock"] is True


def test_get_holidays_for_supported_country():
    payload = json.loads(
        get_holidays.invoke({"country": "bd", "year": 2027})
    )

    assert payload["country"] == "BD"
    assert payload["year"] == 2027
    assert all(
        holiday["date"].startswith("2027-") for holiday in payload["holidays"]
    )


def test_get_holidays_rejects_unknown_country():
    assert get_holidays.invoke(
        {"country": "ZZ", "year": 2027}
    ).startswith("Error:")


def test_track_package_validates_and_returns_status():
    assert track_package.invoke(
        {"tracking_number": "!!"}
    ).startswith("Error:")

    payload = json.loads(
        track_package.invoke({"tracking_number": "AB123456789"})
    )

    assert payload["tracking_number"] == "AB123456789"
    assert payload["status"] in {"in_transit", "out_for_delivery", "delivered"}
    assert payload["mock"] is True
