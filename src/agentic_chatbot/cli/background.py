"""Emerald grid + neural-network decoration.

A persistent full-screen background is not practical on top of Rich +
prompt_toolkit (both own the cursor and redraw freely), so the "intelligent
digital environment" is rendered as *decorative grids* around framed surfaces
such as the welcome hero and section rules. Everything here is static text: no
animation, no per-token redraw cost, no global state.

The pattern combines a sparse geometric grid with occasional emerald nodes so it
reads like a neural network laid over a circuit lattice. Grid strokes use a very
dark green so they behave as texture, and per the design rules background
characters are never drawn over active text: stamped rows are cleared first.
"""

from __future__ import annotations

import sys
from functools import lru_cache

from rich.text import Text

from agentic_chatbot.cli import theme

# Grid geometry: sparse and stable so the decoration is quiet and predictable at
# any terminal width. One horizontal line every few rows, one vertical every few
# columns keeps visual density minimal.
_ROW_SPACING = 3
_COL_SPACING = 8

_GRID_SAMPLE = "\u2500\u2502\u253c\u25cf\u00b7"


@lru_cache(maxsize=1)
def grid_unicode_ok() -> bool:
    """True when the terminal can encode the grid's box/node characters."""
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"

    try:
        _GRID_SAMPLE.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False

    return True


def _grid_chars() -> dict[str, str]:
    if grid_unicode_ok():
        return {"h": "\u2500", "v": "\u2502", "x": "\u253c", "node": "\u25cf"}
    return {"h": "-", "v": "|", "x": "+", "node": "*"}


def _is_node(row: int, col: int, seed: int) -> bool:
    """Deterministic, seed-stable sparse node placement (roughly 1 in 6)."""
    value = (row * 2654435761 + col * 40503 + seed * 97 + 1) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 2246822519) & 0xFFFFFFFF
    value ^= value >> 13
    return (value % 6) == 0


def grid_lines(width: int, rows: int, *, seed: int = 0) -> list[Text]:
    """Return ``rows`` Rich lines of emerald grid with sparse neural nodes.

    Every line is exactly ``width`` columns wide. Grid strokes use the dark
    ``grid`` colour; the occasional node is highlighted in emerald so the
    network points stand out without flooding the surface.
    """
    if width <= 0 or rows <= 0:
        return []

    chars = _grid_chars()
    grid_style = theme.PALETTE.grid
    node_style = theme.PALETTE.node
    lines: list[Text] = []

    for row in range(rows):
        cells: list[str] = []
        nodes: list[int] = []
        on_grid_row = row % _ROW_SPACING == 0

        for col in range(width):
            on_grid_col = col % _COL_SPACING == 0

            if on_grid_row and on_grid_col:
                if _is_node(row, col, seed):
                    cells.append(chars["node"])
                    nodes.append(col)
                else:
                    cells.append(chars["x"])
            elif on_grid_row:
                cells.append(chars["h"])
            elif on_grid_col:
                cells.append(chars["v"])
            else:
                cells.append(" ")

        line = Text("".join(cells), style=grid_style)
        for col in nodes:
            line.stylize(node_style, col, col + 1)
        lines.append(line)

    return lines


def _clean_center(overlay: Text, width: int, style) -> Text:
    """Return a fully blank ``width``-column row with ``overlay`` centred.

    The row is cleared before the text is stamped so background grid strokes are
    never drawn over active content, keeping titles readable at every width. An
    overlay wider than the row is truncated rather than allowed to wrap.
    """
    fit = overlay if overlay.cell_len <= width else overlay[:width]
    overlay_width = fit.cell_len
    start = (width - overlay_width) // 2

    out = Text(style=style)
    out.append(" " * start)
    out.append_text(fit)
    out.append(" " * (width - start - overlay_width))
    return out


def stamp_center(
    lines: list[Text],
    overlays: list[Text],
    width: int,
) -> list[Text]:
    """Return a copy of ``lines`` with ``overlays`` stamped on clean centre rows.

    The overlay block is placed on the vertical middle rows. Each stamped row is
    cleared first, so a title floats cleanly over the surrounding grid texture
    and the grid is never layered behind the characters themselves.
    """
    if not overlays:
        return list(lines)

    result = list(lines)
    start_row = max((len(result) - len(overlays)) // 2, 0)

    for offset, overlay in enumerate(overlays):
        index = start_row + offset
        if 0 <= index < len(result):
            result[index] = _clean_center(overlay, width, result[index].style)

    return result


def banner(
    width: int,
    rows: int,
    overlays: list[Text] | None = None,
    *,
    seed: int = 0,
) -> list[Text]:
    """Convenience: a grid banner with optional centred overlays stamped in."""
    base = grid_lines(width, rows, seed=seed)
    return stamp_center(base, overlays or [], width)


__all__ = [
    "banner",
    "grid_lines",
    "grid_unicode_ok",
    "stamp_center",
]
