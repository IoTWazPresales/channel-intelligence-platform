"""Extensions to the import pipeline handler registry (new modules register here)."""

from __future__ import annotations

from typing import Any, Callable

from app.services.imports.customer_sell_through import process_customer_sell_through

ImportPipelineHandler = Callable[..., int]


def register_customer_sell_through_handlers(handlers: dict[str, ImportPipelineHandler]) -> None:
    """Register customer sell-through (Phase 0 skeleton)."""
    handlers["customer_sell_through"] = process_customer_sell_through


def extend_import_pipeline_handlers(handlers: dict[str, ImportPipelineHandler]) -> None:
    """Apply all registry extensions to the base handler map."""
    register_customer_sell_through_handlers(handlers)
