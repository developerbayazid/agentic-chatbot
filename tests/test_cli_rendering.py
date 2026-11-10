"""New rendering pieces: the emerald grid, background palette, framed input,
and timed tool feedback."""

import io
import sys

import pytest
from rich.color import Color
from rich.console import Console
from rich.text import Text

from agentic_chatbot.cli import background, glyphs, input as input_module
from agentic_chatbot.cli import console as ui
from agentic_chatbot.cli import theme


@pytest.fixture
def unicode_render(monkeypatch):
    monkeypatch.setattr(background, "grid_unicode_ok", lambda: True)
    monkeypatch.setattr(glyphs, "unicode_ok", lambda: True)
    monkeypatch.setattr(input_module, "unicode_ok", lambda: True)


@pytest.fixture
def ascii_render(monkeypatch):
    monkeypatch.setattr(background, "grid_unicode_ok", lambda: False)
    monkeypatch.setattr(glyphs, "unicode_ok", lambda: False)
    monkeypatch.setattr(input_module, "unicode_ok", lambda: False)


# --- theme background palette -------------------------------------------------


def test_background_colours_are_centralised():
    assert theme.BACKGROUND == "#080F0C"
    assert theme.SURFACE == "#101B15"
    assert theme.SURFACE_ALT == "#15241C"
    assert theme.GRID_COLOR == "#14251D"
    assert theme.NODE_COLOR == "#10B981"
    assert theme.GLOW_COLOR == "#064E3B"


def test_palette_exposes_the_background_roles():
    palette = theme.PALETTE
    assert palette.background == theme.BACKGROUND
    assert palette.surface == theme.SURFACE
    assert palette.grid == theme.GRID_COLOR
    assert palette.node == theme.NODE_COLOR


def test_grid_is_distinct_from_the_node_accent():
    assert theme.PALETTE.grid != theme.PALETTE.node
    assert theme.PALETTE.node == theme.BRAND_HEX


def test_grid_colour_is_very_dark_so_it_reads_as_texture():
    grid = Color.parse(theme.GRID_COLOR).get_truecolor()
    assert grid.green > grid.red and grid.green > grid.blue
    assert grid.green < 60


# --- emerald grid renderer ----------------------------------------------------


@pytest.mark.parametrize(("width", "rows"), [(40, 5), (60, 3), (20, 1), (80, 0), (0, 4)])
def test_grid_matches_the_requested_dimensions(width, rows):
    lines = background.grid_lines(width, rows, seed=1)
    if width <= 0 or rows <= 0:
        assert lines == []
    else:
        assert len(lines) == rows
        assert all(line.cell_len == width for line in lines)


def test_grid_with_no_area_returns_nothing():
    assert background.grid_lines(0, 5) == []
    assert background.grid_lines(40, 0) == []


def test_grid_is_deterministic_for_a_seed():
    first = [line.plain for line in background.grid_lines(50, 6, seed=9)]
    second = [line.plain for line in background.grid_lines(50, 6, seed=9)]
    assert first == second


def test_grid_uses_strokes_and_sparse_nodes(unicode_render):
    plain = "".join(line.plain for line in background.grid_lines(64, 6, seed=4))
    assert "\u2502" in plain and "\u2500" in plain  # vertical + horizontal strokes
    nodes = plain.count("\u25cf")
    assert 0 < nodes < len(plain) // 4  # nodes are accents, not a flood


def test_grid_falls_back_to_ascii(ascii_render):
    plain = "".join(line.plain for line in background.grid_lines(40, 3, seed=2))
    assert "\u2500" not in plain and "\u2502" not in plain
    assert "|" in plain and "-" in plain


def test_grid_unicode_detection_reports_true_for_utf8(monkeypatch):
    class Utf8Stdout:
        encoding = "utf-8"

    monkeypatch.setattr(sys, "stdout", Utf8Stdout())
    background.grid_unicode_ok.cache_clear()
    try:
        assert background.grid_unicode_ok() is True
    finally:
        background.grid_unicode_ok.cache_clear()


# --- centred stamping ---------------------------------------------------------


def test_stamped_row_is_clean_so_text_never_sits_on_the_grid(unicode_render):
    title = Text("BAYAZID", style="bold")
    rows = background.banner(40, 5, [title], seed=0)

    stamped = [row.plain for row in rows if "BAYAZID" in row.plain]
    assert len(stamped) == 1
    assert stamped[0].strip() == "BAYAZID"


def test_stamp_centres_the_overlay(unicode_render):
    title = Text("AB", style="bold")
    rows = background.stamp_center(background.grid_lines(20, 3, seed=0), [title], 20)

    stamped = [row.plain for row in rows if "AB" in row.plain][0]
    assert stamped.index("AB") == (20 - 2) // 2


def test_banner_without_overlays_is_plain_grid(unicode_render):
    grid = background.grid_lines(30, 4, seed=0)
    banner = background.banner(30, 4, [], seed=0)
    assert [line.plain for line in grid] == [line.plain for line in banner]


# --- framed input -------------------------------------------------------------


def test_framed_message_draws_a_rule_and_the_prompt(unicode_render):
    fragments = input_module.framed_message()()
    joined = "".join(text for _, text in fragments)

    assert "\u2500" in joined  # top rule
    assert "\u2502" in joined  # left rail
    assert glyphs.g("prompt") in joined


def test_framed_message_is_accepted_by_prompt_toolkit(unicode_render):
    from prompt_toolkit.formatted_text import to_formatted_text

    fragments = to_formatted_text(input_module.framed_message())
    assert any(text for _, text in fragments)


def test_framed_message_falls_back_to_ascii(ascii_render):
    joined = "".join(text for _, text in input_module.framed_message()())
    assert "-" in joined and "|" in joined
    assert "\u2500" not in joined


# --- timed tool feedback ------------------------------------------------------


def _console():
    return Console(width=100, record=True)


def test_tool_result_shows_measured_elapsed():
    console = _console()
    ui.tool_result(console, "tool", "ok", 0.42)
    text = console.export_text()

    assert "Completed" in text
    assert "0.4s" in text


def test_tool_result_omits_timing_when_unknown():
    console = _console()
    ui.tool_result(console, "tool", "ok")
    text = console.export_text()

    assert "Completed" in text
    assert "0." not in text


def test_tool_call_names_the_tool_and_running_state():
    console = _console()
    ui.tool_call(console, "calculator", "{}")

    text = console.export_text()
    assert "Executing tool" in text
    assert "calculator" in text
    assert "running" in text
