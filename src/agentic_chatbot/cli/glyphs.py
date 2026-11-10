"""Render glyphs that degrade gracefully on non-UTF-8 terminals.

Rich downgrades box-drawing characters itself, but literal glyphs in our own
strings (bullets, checkmarks, arrows) would raise ``UnicodeEncodeError`` on a
legacy Windows console. Selecting a glyph set up front keeps the UI polished on
modern terminals and safe everywhere else.
"""

from __future__ import annotations

import sys
from functools import lru_cache

_UNICODE_SAMPLE = "●✓✗❯·"


@lru_cache(maxsize=1)
def unicode_ok() -> bool:
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"

    try:
        _UNICODE_SAMPLE.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        return False

    return True


def glyphs() -> dict[str, str]:
    """Symbols actually used by the interface."""
    if unicode_ok():
        return {
            "active": "●",
            "prompt": "❯",
            "done": "✓",
            "fail": "✗",
            "dot": "·",
        }

    return {
        "active": "*",
        "prompt": ">",
        "done": "+",
        "fail": "x",
        "dot": "-",
    }


def g(name: str) -> str:
    return glyphs().get(name, "")
