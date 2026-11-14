"""Validated, server-named document uploads.

The client supplies bytes and a display name, nothing else. The path that is
actually ingested is generated here:

    <upload root>/.incoming/<uuid><ext>   scratch, always removed
    <upload root>/<subject>/<sha256[:16]><ext>   stored

The stored name derives from the content, so re-uploading identical bytes is
naturally deduplicated by the service's existing ``(namespace, source)`` and
``content_hash`` check.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from agentic_chatbot.loaders import PDF_SUFFIXES, SUPPORTED_SUFFIXES

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024
MAX_DISPLAY_NAME = 120
_PDF_MAGIC = b"%PDF-"


class UploadError(Exception):
    """Rejected before or during ingestion, with a client-safe message."""

    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class StoredUpload:
    path: Path
    title: str
    size_bytes: int
    chunks_created: int
    skipped: bool


def safe_display_name(filename: str | None, suffix: str) -> str:
    """A title for the response — never a path the server will use."""
    name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    name = "".join(character for character in name if character.isprintable())

    if not name:
        return f"upload{suffix}"

    return name[:MAX_DISPLAY_NAME]


def _suffix_of(filename: str | None) -> str:
    name = (filename or "").lower()

    for suffix in sorted(SUPPORTED_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            return suffix

    raise UploadError(
        "UNSUPPORTED_FILE_TYPE",
        "Only Markdown, text, reStructuredText, and PDF files are accepted.",
        415,
    )


def _verify_content(probe: bytes, suffix: str) -> None:
    """Check the bytes, not the extension.

    A ``.pdf`` must actually start with the PDF magic number, and a text file must
    decode as UTF-8 without NUL bytes. A renamed executable or a binary blob is
    refused here rather than by a downstream parser.
    """
    if suffix in PDF_SUFFIXES:
        if not probe.startswith(_PDF_MAGIC):
            raise UploadError(
                "UNSUPPORTED_FILE_TYPE",
                "The uploaded file is not a valid PDF.",
                415,
            )
        return

    if b"\x00" in probe:
        raise UploadError(
            "UNSUPPORTED_FILE_TYPE",
            "The uploaded text file contains binary data.",
            415,
        )

    try:
        probe.decode("utf-8")
    except UnicodeDecodeError as error:
        raise UploadError(
            "UNSUPPORTED_FILE_TYPE",
            "The uploaded text file is not valid UTF-8.",
            415,
        ) from error


def _ingest_lock(container, subject: str, namespace: str):
    """Serialize ingestion for one owner, so duplicate uploads cannot race."""
    return container.thread_lock(f"ingest:{subject}:{namespace}")


def store_upload(
    *,
    container,
    subject: str,
    namespace: str,
    filename: str | None,
    read_chunk,
    max_bytes: int,
) -> StoredUpload:
    """Receive one upload in chunks, verify it, and ingest it.

    ``read_chunk`` is a callable returning the next bytes (``b""`` at EOF), so
    the size limit is enforced *while* receiving rather than after buffering
    something unbounded in memory.
    """
    suffix = _suffix_of(filename)
    title = safe_display_name(filename, suffix)
    root = Path(container.settings.api_upload_path)
    incoming = root / ".incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    scratch = incoming / f"{uuid.uuid4().hex}{suffix}"
    digest = hashlib.sha256()
    size = 0
    probe = b""

    try:
        with scratch.open("wb") as target:
            while True:
                chunk = read_chunk()

                if not chunk:
                    break

                size += len(chunk)

                if size > max_bytes:
                    raise UploadError(
                        "FILE_TOO_LARGE",
                        "The uploaded file exceeds the size limit.",
                        413,
                    )

                if len(probe) < 1024:
                    probe += chunk[: 1024 - len(probe)]

                digest.update(chunk)
                target.write(chunk)

            target.flush()
            os.fsync(target.fileno())

        if size == 0:
            raise UploadError(
                "EMPTY_FILE", "The uploaded file is empty.", 415
            )

        _verify_content(probe, suffix)

        stored_dir = root / subject
        stored_dir.mkdir(parents=True, exist_ok=True)
        stored = stored_dir / f"{digest.hexdigest()[:16]}{suffix}"
        os.replace(scratch, stored)

        try:
            with _ingest_lock(container, subject, namespace):
                chunks_created, skipped, _ = container.document_service.ingest_file(
                    stored, namespace, owner_id=subject
                )
        except Exception:
            logger.exception("ingestion failed for %s", stored.name)
            stored.unlink(missing_ok=True)
            raise UploadError(
                "INGEST_FAILED",
                "The document could not be indexed.",
                422,
            ) from None

        return StoredUpload(
            path=stored,
            title=title,
            size_bytes=size,
            chunks_created=chunks_created,
            skipped=skipped,
        )
    finally:
        scratch.unlink(missing_ok=True)
