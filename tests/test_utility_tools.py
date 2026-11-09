import json

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


def test_convert_units_length_and_mass():
    assert convert_units.invoke(
        {"value": 1, "from_unit": "km", "to_unit": "m"}
    ) == "1000 m"
    assert convert_units.invoke(
        {"value": 2, "from_unit": "lb", "to_unit": "kg"}
    ) == "0.907185 kg"


def test_convert_units_temperature():
    assert convert_units.invoke(
        {"value": 100, "from_unit": "c", "to_unit": "f"}
    ) == "212 f"
    assert convert_units.invoke(
        {"value": 32, "from_unit": "f", "to_unit": "c"}
    ) == "0 c"


def test_convert_units_rejects_incompatible_units():
    result = convert_units.invoke(
        {"value": 1, "from_unit": "kg", "to_unit": "m"}
    )

    assert result.startswith("Error:")


def test_generate_uuid_is_valid():
    value = generate_uuid.invoke({})

    assert len(value) == 36
    assert value.count("-") == 4


def test_generate_password_respects_length_and_symbols():
    password = generate_password.invoke({"length": 24, "use_symbols": True})

    assert len(password) == 24
    assert any(character in "!@#$%^&*()-_=+[]{};:,.?" for character in password)


def test_generate_password_rejects_short_length():
    result = generate_password.invoke({"length": 4})

    assert result.startswith("Error:")


def test_hash_text_known_digest():
    assert (
        hash_text.invoke({"text": "abc", "algorithm": "sha256"})
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_hash_text_rejects_unknown_algorithm():
    assert hash_text.invoke(
        {"text": "abc", "algorithm": "crc32"}
    ).startswith("Error:")


def test_base64_round_trip():
    encoded = base64_encode.invoke({"text": "hello world"})

    assert encoded == "aGVsbG8gd29ybGQ="
    assert base64_decode.invoke({"text": encoded}) == "hello world"


def test_base64_decode_reports_invalid_input():
    assert base64_decode.invoke({"text": "not base64!!"}).startswith("Error:")


def test_format_json_pretty_prints_and_reports_errors():
    assert format_json.invoke({"raw_json": '{"b":2,"a":1}'}) == (
        '{\n  "b": 2,\n  "a": 1\n}'
    )
    assert format_json.invoke({"raw_json": "{bad"}).startswith("Error:")


def test_regex_search_returns_matches():
    matches = json.loads(
        regex_search.invoke(
            {"pattern": r"\d+", "text": "a1 b22 c333"}
        )
    )

    assert [match["match"] for match in matches] == ["1", "22", "333"]


def test_regex_search_reports_invalid_pattern():
    assert regex_search.invoke(
        {"pattern": "(", "text": "x"}
    ).startswith("Error:")


def test_summarize_text_keeps_first_sentences():
    text = "First sentence. Second sentence. Third sentence. Fourth sentence."

    assert (
        summarize_text.invoke({"text": text, "max_sentences": 2})
        == "First sentence. Second sentence."
    )
