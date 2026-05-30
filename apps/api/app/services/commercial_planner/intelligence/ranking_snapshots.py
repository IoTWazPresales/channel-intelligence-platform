"""In-process ranking snapshots (audit replay within API worker; not cross-process durable)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_SNAPSHOTS: dict[str, dict[str, Any]] = {}


def _key(plan_id: int, customer_id: int, distributor_id: int) -> str:
    return f"{plan_id}:{customer_id}:{distributor_id}"


def store_ranking_snapshot(
    *,
    plan_id: int,
    customer_id: int,
    distributor_id: int,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    key = _key(plan_id, customer_id, distributor_id)
    payload = {
        "plan_id": plan_id,
        "customer_id": customer_id,
        "distributor_id": distributor_id,
        "stored_at": datetime.now(timezone.utc).isoformat(),
        "item_count": len(items),
        "items": items,
    }
    _SNAPSHOTS[key] = payload
    return payload


def get_ranking_snapshot(*, plan_id: int, customer_id: int, distributor_id: int) -> dict[str, Any] | None:
    return _SNAPSHOTS.get(_key(plan_id, customer_id, distributor_id))


def list_ranking_snapshots_for_plan(plan_id: int) -> list[dict[str, Any]]:
    prefix = f"{plan_id}:"
    return [v for k, v in _SNAPSHOTS.items() if k.startswith(prefix)]
