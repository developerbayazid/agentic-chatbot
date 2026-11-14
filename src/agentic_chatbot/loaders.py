"""Turn supported files into text sections for retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".rst"}
PDF_SUFFIXES = {".pdf"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | PDF_SUFFIXES

_BLANK_RUN = re.compile(r"\n{3,}")


class DocumentLoadError(Exception):
    """Raised when a file cannot be turned into text."""


@dataclass(frozen=True)
class Section:
    page: int | None
    text: str


@dataclass(frozen=True)
class LoadResult:
    sections: list[Section] = field(default_factory=list)
    truncated: bool = False


def load_file(path: Path, *, max_pdf_pages: int = 200) -> LoadResult:
    suffix = path.suffix.lower()

    if suffix in TEXT_SUFFIXES:
        return LoadResult(sections=[Section(page=None, text=_read_text(path))])

    if suffix in PDF_SUFFIXES:
        return _read_pdf(path, max_pdf_pages=max_pdf_pages)

    raise DocumentLoadError(f"unsupported file type: {suffix or '(none)'}")


def _read_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise DocumentLoadError(str(exc)) from exc

    text = _normalize(text)

    if not text:
        raise DocumentLoadError("file contains no text")

    return text


def _read_pdf(path: Path, *, max_pdf_pages: int) -> LoadResult:
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise DocumentLoadError(f"cannot read PDF: {exc}") from exc

    if reader.is_encrypted and not reader.decrypt(""):
        raise DocumentLoadError("encrypted PDF; decrypt it before ingesting")

    sections: list[Section] = []
    truncated = False

    for number, page in enumerate(reader.pages, start=1):
        if number > max_pdf_pages:
            truncated = True
            break

        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise DocumentLoadError(f"page {number}: {exc}") from exc

        text = _normalize(text)

        if text:
            sections.append(Section(page=number, text=text))

    if not sections:
        raise DocumentLoadError(
            "no extractable text (scanned PDF? OCR is not supported)"
        )

    return LoadResult(sections=sections, truncated=truncated)


def _normalize(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return _BLANK_RUN.sub("\n\n", text).strip()
