"""Central design system: the single source of truth for CLI colour and type.

Every surface in ``agentic_chatbot.cli`` imports its styles from here. Nothing
else should hardcode a hex value or a colour name, so the brand can change in
one place and the whole interface follows.

Brand: ``#10B981`` (emerald green), RGB ``(16, 185, 129)``.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.color import Color
from rich.style import Style
from rich.theme import Theme


# --- palette -----------------------------------------------------------------

BRAND_HEX = "#10B981"
BRAND_RGB = (16, 185, 129)

# Type ramp. The brand is an accent: it labels identity, never body copy, so
# long assistant answers keep a white-on-dark contrast ratio.
PRIMARY = BRAND_HEX
PRIMARY_DIM = "#047857"
TEXT = "#E6F4EE"
TEXT_STRONG = "#FFFFFF"
MUTED = "#9CAFA5"
FAINT = "#64786D"
RULE = "#263B30"

SUCCESS = "#34D399"
WARNING = "#FBBF24"
ERROR = "#FB7185"

USER_LABEL = "#FFFFFF"
ASSISTANT_LABEL = BRAND_HEX

# Surfaces and the emerald-grid background. The grid is a very dark green so it
# reads as texture behind content, never as foreground noise. Node and glow add
# the neural-network accent sparingly.
BACKGROUND = "#080F0C"
SURFACE = "#101B15"
SURFACE_ALT = "#15241C"
GRID_COLOR = "#14251D"
NODE_COLOR = "#10B981"
GLOW_COLOR = "#064E3B"

# --- spacing -----------------------------------------------------------------

# Left gutter for the whole transcript. One value keeps every row aligned.
GUTTER = 2
# Blank line between top-level blocks (welcome, a turn, a command result).
BLOCK_GAP = 1


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    colour = Color.parse(hex_colour).get_truecolor()
    return (colour.red, colour.green, colour.blue)


@dataclass(frozen=True)
class Palette:
    """Resolved colours plus the Rich styles built from them."""

    primary: str = PRIMARY
    primary_dim: str = PRIMARY_DIM
    text: str = TEXT
    text_strong: str = TEXT_STRONG
    muted: str = MUTED
    faint: str = FAINT
    rule: str = RULE
    success: str = SUCCESS
    warning: str = WARNING
    error: str = ERROR

    # Surfaces + emerald-grid background.
    background: str = BACKGROUND
    surface: str = SURFACE
    surface_alt: str = SURFACE_ALT
    grid: str = GRID_COLOR
    node: str = NODE_COLOR
    glow: str = GLOW_COLOR

    @property
    def rgb(self) -> tuple[int, int, int]:
        return _rgb(self.primary)

    # Typography roles -------------------------------------------------------

    @property
    def title(self) -> Style:
        return Style(color=self.primary, bold=True)

    @property
    def label(self) -> Style:
        return Style(color=self.primary, bold=True)

    @property
    def user(self) -> Style:
        return Style(color=USER_LABEL, bold=True)

    @property
    def body(self) -> Style:
        return Style(color=self.text)

    @property
    def strong(self) -> Style:
        return Style(color=self.text_strong, bold=True)

    @property
    def subtle(self) -> Style:
        return Style(color=self.muted)

    @property
    def very_subtle(self) -> Style:
        return Style(color=self.faint)

    @property
    def command(self) -> Style:
        return Style(color=self.primary)

    @property
    def selected(self) -> Style:
        return Style(bgcolor=self.primary, color="#FFFFFF", bold=True)

    @property
    def ok(self) -> Style:
        return Style(color=self.success)

    @property
    def warn(self) -> Style:
        return Style(color=self.warning)

    @property
    def danger(self) -> Style:
        return Style(color=self.error)


PALETTE = Palette()

# Markup names so any Rich string can say ``[brand]…[/]`` instead of a hex.
RICH_THEME = Theme(
    {
        "brand": PRIMARY,
        "brand.bold": f"bold {PRIMARY}",
        "brand.dim": PRIMARY_DIM,
        "text": TEXT,
        "text.strong": TEXT_STRONG,
        "muted": MUTED,
        "faint": FAINT,
        "rule": RULE,
        "ok": SUCCESS,
        "warn": WARNING,
        "err": ERROR,
        "grid": GRID_COLOR,
        "node": NODE_COLOR,
        "surface": SURFACE,
        "bg": BACKGROUND,
    }
)


def markup(name: str) -> str:
    """Return a Rich markup tag body for a palette role, e.g. ``brand``."""
    return f"{name}"


__all__ = [
    "ASSISTANT_LABEL",
    "BACKGROUND",
    "BLOCK_GAP",
    "BRAND_HEX",
    "BRAND_RGB",
    "GRID_COLOR",
    "GLOW_COLOR",
    "GUTTER",
    "NODE_COLOR",
    "PALETTE",
    "Palette",
    "RICH_THEME",
    "SURFACE",
    "SURFACE_ALT",
    "USER_LABEL",
    "markup",
]
