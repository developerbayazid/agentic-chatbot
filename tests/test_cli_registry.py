"""Command registry behavior: lookup, grouping, suggestions, fuzzy matching."""

import pytest

from agentic_chatbot.cli.registry import (
    CATEGORY_CONVERSATION,
    CATEGORY_GENERAL,
    Command,
    Completion,
    command_names,
    grouped,
    normalize,
    resolve,
    similar_commands,
    split_input,
    suggest,
)


def _command(name, category=CATEGORY_GENERAL, description="desc"):
    return Command(
        name=name,
        description=description,
        category=category,
        usage=name,
        example=name,
        behavior="behaves",
        arguments="none",
        handler=lambda session, argument: None,
    )


COMMANDS = [
    _command("/help"),
    _command("/exit"),
    _command("/new", CATEGORY_CONVERSATION),
    _command("/threads", CATEGORY_CONVERSATION),
    _command("/delete", CATEGORY_CONVERSATION),
]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/help", "/help"),
        ("HELP", "/help"),
        (" help ", "/help"),
        ("/HELP", "/help"),
    ],
)
def test_normalize_accepts_forms_with_and_without_slash(raw, expected):
    assert normalize(raw) == expected


def test_normalize_returns_empty_for_blank():
    assert normalize("   ") == ""


def test_resolve_accepts_slashless_names():
    assert resolve(COMMANDS, "threads").name == "/threads"
    assert resolve(COMMANDS, "/threads").name == "/threads"


def test_resolve_returns_none_for_unknown():
    assert resolve(COMMANDS, "/nope") is None


def test_command_names_are_ordered_as_declared():
    assert command_names(COMMANDS) == [
        "/help",
        "/exit",
        "/new",
        "/threads",
        "/delete",
    ]


def test_grouped_orders_known_categories_first_and_sorts_names():
    groups = grouped(COMMANDS)

    assert [category for category, _ in groups] == [
        CATEGORY_GENERAL,
        CATEGORY_CONVERSATION,
    ]
    general = dict(groups)[CATEGORY_GENERAL]
    assert [command.name for command in general] == ["/exit", "/help"]
    conversation = dict(groups)[CATEGORY_CONVERSATION]
    assert [command.name for command in conversation] == [
        "/delete",
        "/new",
        "/threads",
    ]


def test_grouped_places_unknown_categories_last():
    groups = grouped([*COMMANDS, _command("/custom", "Advanced")])

    assert groups[-1][0] == "Advanced"


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("/", ["/exit", "/help", "/delete", "/new", "/threads"]),
        ("/th", ["/threads"]),
        ("/del", ["/delete"]),
        ("/HELP", ["/help"]),
    ],
)
def test_suggest_filters_by_prefix(prefix, expected):
    assert [command.name for command in suggest(COMMANDS, prefix)] == expected


def test_suggest_returns_empty_without_slash():
    assert suggest(COMMANDS, "th") == []


def test_suggest_falls_back_to_fuzzy_matches():
    assert [command.name for command in suggest(COMMANDS, "/threds")] == ["/threads"]


def test_suggest_returns_empty_when_nothing_is_close():
    assert suggest(COMMANDS, "/zzzzz") == []


def test_similar_commands_respects_limit():
    assert len(similar_commands(COMMANDS, "/h", limit=1)) <= 1


def test_similar_commands_handles_blank_name():
    assert similar_commands(COMMANDS, "") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/delete abc", ("/delete", "abc")),
        ("/help", ("/help", "")),
        ("  /rename   my chat  ", ("/rename", "my chat")),
        ("hello", ("hello", "")),
        ("   ", ("", "")),
    ],
)
def test_split_input_separates_command_and_argument(text, expected):
    assert split_input(text) == expected


def test_completion_record_defaults_to_empty_description():
    assert Completion("value").description == ""
