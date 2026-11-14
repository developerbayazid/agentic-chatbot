"""JSON data access for the inventory demo.

One JSON document is the system of record. Every mutation runs inside a
read-modify-write transaction guarded by a process lock, is validated as a
whole, and is persisted with a temporary file plus :func:`os.replace`, so a
crash cannot leave a half-written file behind.

This is intentionally not a database: it favours inspectability and a small
surface over concurrency or scale.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from agentic_chatbot.inventory.validation import (
    COLLECTIONS,
    DatasetValidationError,
    ValidationReport,
    validate_dataset,
)

DHAKA = ZoneInfo("Asia/Dhaka")


class InventoryStoreError(RuntimeError):
    """Raised for filesystem or dataset shape problems."""


class InventoryDataNotFoundError(InventoryStoreError):
    """Raised when the dataset file is missing (the app may run without it)."""


class InventoryStore:
    """Load, query, and atomically update the inventory JSON document."""

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._data: dict[str, Any] = self._load_and_validate()

    @property
    def path(self) -> Path:
        return self._path

    def metadata(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data.get("metadata", {}))

    def snapshot(self) -> dict[str, Any]:
        """Return a deep copy of the whole dataset."""
        with self._lock:
            return copy.deepcopy(self._data)

    def collection(self, name: str) -> list[dict[str, Any]]:
        """Return a deep copy of one entity collection."""
        return self.find(name)

    def find(self, name: str, **criteria: Any) -> list[dict[str, Any]]:
        """Return rows matching every criterion, as a deep copy."""
        with self._lock:
            rows = self._data.get(name)
            if not isinstance(rows, list):
                raise InventoryStoreError(f"Unknown collection: {name}")

            if not criteria:
                return copy.deepcopy(rows)

            return copy.deepcopy(
                [
                    row
                    for row in rows
                    if all(row.get(key) == value for key, value in criteria.items())
                ]
            )

    def get(self, name: str, id_field: str, value: str) -> dict[str, Any] | None:
        with self._lock:
            for row in self._data.get(name, []):
                if row.get(id_field) == value:
                    return copy.deepcopy(row)
            return None

    def search(
        self,
        name: str,
        query: str,
        fields: tuple[str, ...],
        *,
        predicate=None,
    ) -> list[dict[str, Any]]:
        """Case-insensitive substring search across the named fields."""
        needle = query.strip().lower()
        with self._lock:
            results = []
            for row in self._data.get(name, []):
                if predicate is not None and not predicate(row):
                    continue
                haystack = " ".join(str(row.get(field, "")) for field in fields).lower()
                if not needle or needle in haystack:
                    results.append(copy.deepcopy(row))
            return results

    @contextmanager
    def transaction(self) -> Iterator[dict[str, Any]]:
        """Read the latest file, yield a mutable copy, validate, and save.

        The yield happens outside the lock only in name: the lock is held for
        the whole read-modify-write cycle, so two threads cannot interleave and
        lose an update. Raising inside the block aborts the write.
        """
        with self._lock:
            data = self._load_from_disk()
            yield data
            data.setdefault("metadata", {})["last_updated"] = _now_timestamp()
            report = validate_dataset(data)
            if not report.ok:
                raise DatasetValidationError(report)
            self._write(data)
            self._data = data

    def next_id(
        self,
        data: dict[str, Any],
        collection: str,
        id_field: str,
        prefix: str,
        width: int = 3,
    ) -> str:
        """Generate the next sequential ID without colliding with existing rows."""
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
        highest = 0
        for row in data.get(collection, []):
            match = pattern.match(str(row.get(id_field, "")))
            if match:
                highest = max(highest, int(match.group(1)))
        return f"{prefix}-{highest + 1:0{width}d}"

    def validate(self) -> ValidationReport:
        with self._lock:
            return validate_dataset(self._data)

    # --- persistence --------------------------------------------------------

    def _load_and_validate(self) -> dict[str, Any]:
        data = self._load_from_disk()
        report = validate_dataset(data)
        if not report.ok:
            raise DatasetValidationError(report)
        return data

    def _load_from_disk(self) -> dict[str, Any]:
        if not self._path.is_file():
            raise InventoryDataNotFoundError(
                f"Inventory dataset not found: {self._path}. "
                "Restore inventory-data/inventory/inventory_data.json."
            )
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as error:
            raise InventoryStoreError(
                f"Inventory dataset is not valid JSON ({self._path}): {error}"
            ) from error
        except OSError as error:
            raise InventoryStoreError(
                f"Cannot read inventory dataset ({self._path}): {error}"
            ) from error

        if not isinstance(data, dict):
            raise InventoryStoreError("Inventory dataset root must be a JSON object.")

        for name in COLLECTIONS:
            data.setdefault(name, [])

        return data

    def _write(self, data: dict[str, Any]) -> None:
        """Atomically replace the dataset, preserving readable JSON formatting."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary = tempfile.mkstemp(
            prefix=f"{self._path.name}.",
            suffix=".tmp",
            dir=str(self._path.parent),
        )
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


def _now_timestamp() -> str:
    return datetime.now(DHAKA).isoformat(timespec="seconds")
