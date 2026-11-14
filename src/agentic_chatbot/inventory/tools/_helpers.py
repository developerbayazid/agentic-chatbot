"""Shared helpers for inventory tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain_core.runnables import RunnableConfig

from agentic_chatbot.inventory.service import InventoryError


def as_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def call(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """Run a service method and always return a model-readable string."""
    try:
        return as_json(fn(*args, **kwargs))
    except (InventoryError, ValueError, KeyError) as error:
        return f"Error: {error}"
    except Exception as error:  # noqa: BLE001 - tools report, never crash the loop
        return f"Error: unexpected failure: {error}"


def operation_id(config: RunnableConfig | None) -> str | None:
    if not config:
        return None
    configurable = config.get("configurable") or {}
    value = configurable.get("inventory_operation_id")
    return str(value) if value else None
