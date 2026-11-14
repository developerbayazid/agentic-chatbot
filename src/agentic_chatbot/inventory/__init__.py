"""Inventory domain: JSON persistence, validation, service, and tools.

This package is additive. It keeps the JSON dataset, business rules, and tool
definitions separate, following the project's existing layering.
"""

from agentic_chatbot.inventory.data_access import (
    InventoryDataNotFoundError,
    InventoryStore,
    InventoryStoreError,
)
from agentic_chatbot.inventory.validation import (
    DatasetValidationError,
    ValidationReport,
    validate_dataset,
)

__all__ = [
    "DatasetValidationError",
    "InventoryDataNotFoundError",
    "InventoryStore",
    "InventoryStoreError",
    "ValidationReport",
    "validate_dataset",
]
