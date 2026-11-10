"""Welcome header, theme, and status output."""

import io

import pytest
from rich.console import Console

from agentic_chatbot.cli import console as ui
from agentic_chatbot.cli import theme

SHORTCUTS = (("/help", "commands"), ("/threads", "conversations"))


def _status(**overrides):
    values = {
        "model": "gpt-4o-mini",
        "database_path": "chatbot_memory.db",
        "database_ok": True,
        "graph_ok": True,
        "tracing_enabled": True,
        "thread_id": "03679327-b818-4d73-a03d-a3eda5c2c0e3",
        "thread_count": 4,
        "tool_count": 36,
    }
    values.update(overrides)
    return ui.StatusSnapshot(**values)


def render(width=100, status="default", **kwargs) -> str:
    console = Console(
        width=width, record=True, force_terminal=False, theme=theme.RICH_THEME
    )
    kwargs.setdefault("shortcuts", SHORTCUTS)
    kwargs.setdefault("version", "0.1.0")
    resolved = _status() if status == "default" else status
    ui.show_welcome(console, resolved, **kwargs)
    return console.export_text()


def lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


# --- theme -------------------------------------------------------------------


def test_brand_colour_is_emerald_green():
    assert theme.BRAND_HEX == "#10B981"
    assert theme.PRIMARY == "#10B981"


def test_brand_rgb_is_the_exact_triplet():
    assert theme.BRAND_RGB == (16, 185, 129)
    assert theme.PALETTE.rgb == (16, 185, 129)


def test_no_legacy_cyan_remains_in_the_palette():
    palette = theme.Palette()

    for value in vars(palette).values():
        if isinstance(value, str) and value.startswith("#"):
            assert value.lower() not in {"#00ffff", "#0ff", "#5fd7d7", "#22d3ee"}


def test_primary_role_styles_use_the_brand_colour():
    palette = theme.PALETTE

    for style in (palette.title, palette.label, palette.command, palette.selected):
        assert str(style).lower().find("#10b981") >= 0 or "rgb(16,185,129)" in str(style).lower().replace(" ", "")


def test_body_text_is_not_the_brand_colour():
    # The brand labels identity; body copy must stay high-contrast.
    assert theme.PALETTE.body.color != theme.PALETTE.primary


def test_brand_is_emitted_as_exact_truecolor_ansi():
    """The brand must reach a truecolor terminal as 24-bit 16;185;129 — not a
    downgraded approximation of the colour."""
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        width=80,
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
    )

    ui.show_welcome(console, None, version="1.0")

    assert "\x1b[1;38;2;16;185;129m" in buffer.getvalue()


def test_brand_degrades_gracefully_without_truecolor():
    """On a 16-colour terminal the brand falls back instead of raising."""
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        width=80,
        force_terminal=True,
        color_system="standard",
    )

    ui.show_welcome(console, None, version="1.0")

    assert ui.APP_NAME in buffer.getvalue()


def test_no_cyan_appears_in_rendered_output():
    text = render()

    assert "cyan" not in text.lower()


# --- welcome layout ----------------------------------------------------------


@pytest.mark.parametrize("width", [60, 80, 100, 120])
def test_welcome_fits_within_the_terminal(width):
    for line in lines(render(width=width)):
        assert len(line) <= width, line


@pytest.mark.parametrize("width", [80, 120])
def test_welcome_has_no_trailing_whitespace(width):
    for line in lines(render(width=width)):
        assert line == line.rstrip(), repr(line)


def test_welcome_is_compact():
    # The framed hero is richer than a bare banner but must still leave room to
    # chat rather than filling the screen like a dashboard.
    assert len(lines(render())) <= 16


def test_welcome_shows_identity_and_tagline():
    text = render()

    assert ui.APP_NAME in text
    assert ui.APP_SUBTITLE in text
    assert ui.APP_TAGLINE in text


def test_welcome_shows_version_when_given():
    assert "v0.1.0" in render()


def test_welcome_omits_version_when_not_given():
    assert "v0.1.0" not in render(version="")


def test_welcome_shows_runtime_facts():
    text = render()

    for fragment in ("MODEL", "gpt-4o-mini", "STORAGE", "SQLite", "GRAPH", "TRACING"):
        assert fragment in text


def test_welcome_reports_graph_state():
    assert "ready" in render()
    assert "unavailable" in render(status=_status(graph_ok=False))


def test_welcome_reports_tracing_state():
    assert "on" in render()
    assert "off" in render(status=_status(tracing_enabled=False))


def test_welcome_reports_database_health():
    assert "connected" in render()
    assert "unreachable" in render(status=_status(database_ok=False))


def test_welcome_shortens_the_session_id():
    text = render()

    assert "0367932" in text
    assert "03679327-b818-4d73-a03d-a3eda5c2c0e3" not in text


def test_welcome_never_shows_the_database_path():
    text = render(status=_status(database_path="secret/place.db"))

    assert "secret/place.db" not in text
    assert "DATABASE" not in text


def test_welcome_lists_shortcuts():
    text = render()

    for command, description in SHORTCUTS:
        assert command in text
        assert description in text


def test_welcome_omits_shortcut_block_when_empty():
    text = render(shortcuts=())

    assert ui.APP_NAME in text
    assert "/exit" in text


def test_welcome_renders_without_status():
    text = render(status=None)

    assert ui.APP_NAME in text


def test_welcome_frames_the_identity_in_a_subtle_box():
    text = render()

    # The brand lockup sits inside a framed hero. Corners degrade with Unicode
    # support (rounded -> square -> ASCII), so accept the corner set Rich emits.
    assert any(corner in text for corner in "╭┌+")
    assert any(rail in text for rail in "│|")


# --- status command ----------------------------------------------------------


def status_output(**overrides) -> str:
    console = Console(
        width=120, record=True, force_terminal=False, theme=theme.RICH_THEME
    )
    ui.show_status_banner(console, _status(**overrides))
    return console.export_text()


def test_status_shows_the_database_path():
    assert "chatbot_memory.db" in status_output()


def test_status_can_hide_the_database():
    console = Console(width=120, record=True, force_terminal=False)
    ui.show_status_banner(console, _status(), show_database=False)

    assert "DATABASE" not in console.export_text()


def test_status_reports_tool_and_thread_counts():
    text = status_output()

    assert "36" in text
    assert "THREADS" in text


def test_status_shows_the_full_session_id():
    assert "03679327-b818-4d73-a03d-a3eda5c2c0e3" in status_output()


@pytest.mark.parametrize("width", [60, 80, 120])
def test_status_fits_the_terminal(width):
    console = Console(width=width, record=True, force_terminal=False)
    ui.show_status_banner(console, _status())

    for line in lines(console.export_text()):
        assert len(line) <= width, line
