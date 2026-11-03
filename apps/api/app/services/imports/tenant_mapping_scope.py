"""Tenant scope for column-mapping memory (source_definition) and steward alias tables (M5c / D-0149)."""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy.orm import InstrumentedAttribute

from app.models.ingestion import SourceDefinition

DEFAULT_TENANT_ID = "default"

_M = TypeVar("_M")


def effective_tenant_id(tenant_id: str | None) -> str:
    tid = (tenant_id or "").strip()
    return tid or DEFAULT_TENANT_ID


def tenant_scope_predicate(model: type[_M], tenant_id: str | None) -> Any:
    """SQLAlchemy filter: ``model.tenant_id == effective_tenant_id(tenant_id)``."""
    col: InstrumentedAttribute = model.tenant_id  # type: ignore[attr-defined]
    return col == effective_tenant_id(tenant_id)


def source_memory_visible(source: SourceDefinition | None, tenant_id: str | None) -> SourceDefinition | None:
    """Return source only when its tenant matches the job tenant; else no memory (no cross-tenant leak)."""
    if source is None:
        return None
    if effective_tenant_id(getattr(source, "tenant_id", None)) != effective_tenant_id(tenant_id):
        return None
    return source


def assert_source_tenant(source: SourceDefinition | None, tenant_id: str | None) -> bool:
    return source_memory_visible(source, tenant_id) is not None
