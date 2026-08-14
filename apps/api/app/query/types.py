"""P3-2 query engine request/result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

QueryStatus = Literal["ok", "not_implemented", "refused"]


@dataclass
class CacheMeta:
    hit: bool
    ttl_seconds: int
    key: str

    def as_dict(self) -> dict[str, Any]:
        return {"hit": self.hit, "ttl_seconds": self.ttl_seconds, "key": self.key}


@dataclass
class QueryRequest:
    metric: str
    grains: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)
    tenant_id: str = "default"
    period_grain: str | None = None


@dataclass
class HandlerResult:
    """Payload produced by a metric handler (pre-envelope)."""

    status: QueryStatus
    invariants_applied: list[str] = field(default_factory=list)
    data_vintage: dict[str, Any] | None = None
    value: Any = None
    rows: list[dict[str, Any]] | None = None
    series: list[dict[str, Any]] | None = None
    scorecard: dict[str, Any] | None = None
    explain: dict[str, Any] | None = None
    message: str | None = None

    def as_payload(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status,
            "invariants_applied": list(self.invariants_applied),
            "data_vintage": self.data_vintage,
            "value": self.value,
            "rows": self.rows,
            "series": self.series,
            "scorecard": self.scorecard,
            "message": self.message,
        }
        if self.explain is not None:
            out["explain"] = self.explain
        return out


@dataclass
class QueryResult:
    ok: bool
    status: QueryStatus
    metric_id: str | None
    metric_key: str | None
    grains: list[str]
    filters: dict[str, Any]
    validation: dict[str, Any]
    invariants_applied: list[str] = field(default_factory=list)
    data_vintage: dict[str, Any] | None = None
    value: Any = None
    rows: list[dict[str, Any]] | None = None
    series: list[dict[str, Any]] | None = None
    scorecard: dict[str, Any] | None = None
    cache: CacheMeta | None = None
    message: str | None = None
    handler: str | None = None
    explain: dict[str, Any] | None = None
    period_grain: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "metric_id": self.metric_id,
            "metric_key": self.metric_key,
            "grains": list(self.grains),
            "filters": dict(self.filters),
            "period_grain": self.period_grain,
            "validation": self.validation,
            "invariants_applied": list(self.invariants_applied),
            "data_vintage": self.data_vintage,
            "value": self.value,
            "rows": self.rows,
            "series": self.series,
            "scorecard": self.scorecard,
            "cache": self.cache.as_dict() if self.cache else None,
            "message": self.message,
            "handler": self.handler,
            "explain": self.explain,
        }
