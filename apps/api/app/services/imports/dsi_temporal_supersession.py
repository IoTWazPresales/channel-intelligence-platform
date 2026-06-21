"""Temporal supersession disambiguation for product-ambiguous DSI rows (post-receipt tier).

Per-line resolution using shipment windows keyed by ``product_id``. Feasibility is
**per-distributor** only when that distributor has volume-shipped evidence for the SKU.
Global (any-distributor) windows are attached for transition ordering explainability only —
never used to assert a distributor received a SKU it has no evidence for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.imports.provisional_entity_identity import canonical_provisional_entity_name_key

REASON_TEMPORAL_SUPERSESSION = "temporal_supersession"

STATUS_RESOLVED = "resolved_temporal_supersession"
STATUS_FIFO_CANDIDATE = "fifo_candidate"


@dataclass(frozen=True, slots=True)
class ShipmentWindow:
    """Inclusive ship-date window for one product at one scope."""

    product_id: int
    first_ship: date
    last_ship: date


@dataclass(frozen=True, slots=True)
class TemporalSupersessionResult:
    product_id: int | None
    resolve_reason: str | None
    evidence: dict[str, Any] | None = None


class ProductShipmentWindowIndex:
    """Volume-shipped windows by canonical distributor × product_id, plus global ordering."""

    __slots__ = ("_by_dist", "_global")

    def __init__(self) -> None:
        self._by_dist: dict[tuple[str, int], ShipmentWindow] = {}
        self._global: dict[int, ShipmentWindow] = {}

    @classmethod
    def load(cls, db: Session, dist_id_to_canonical: dict[int, str]) -> "ProductShipmentWindowIndex":
        idx = cls()
        rows = db.execute(
            text(
                """
                SELECT
                    distributor_id,
                    product_id,
                    MIN(COALESCE(ship_confirm_date, schedule_ship_date, promise_date))::date AS first_ship,
                    MAX(COALESCE(ship_confirm_date, schedule_ship_date, promise_date))::date AS last_ship
                FROM shipment_evidence_line
                WHERE product_resolution_status IN ('resolved', 'resolved_unique')
                  AND product_id IS NOT NULL
                  AND distributor_id IS NOT NULL
                  AND line_state = 'shipped'
                  AND COALESCE(quantity, 0) > 1
                  AND btrim(coalesce(sales_model_name, '')) <> ''
                  AND lower(btrim(coalesce(sales_model_name, ''))) NOT LIKE '%-demo'
                  AND lower(btrim(coalesce(sales_model_name, ''))) NOT LIKE '%-dem'
                  AND COALESCE(ship_confirm_date, schedule_ship_date, promise_date) IS NOT NULL
                GROUP BY distributor_id, product_id
                """
            )
        ).fetchall()
        global_first: dict[int, date] = {}
        global_last: dict[int, date] = {}
        for dist_id, pid, first_ship, last_ship in rows:
            if pid is None or first_ship is None or last_ship is None:
                continue
            p = int(pid)
            fs = first_ship if isinstance(first_ship, date) else first_ship
            ls = last_ship if isinstance(last_ship, date) else last_ship
            canon = dist_id_to_canonical.get(int(dist_id)) if dist_id is not None else ""
            if not canon:
                continue
            idx._by_dist[(canon, p)] = ShipmentWindow(product_id=p, first_ship=fs, last_ship=ls)
            if p not in global_first or fs < global_first[p]:
                global_first[p] = fs
            if p not in global_last or ls > global_last[p]:
                global_last[p] = ls
        for p in global_first:
            idx._global[p] = ShipmentWindow(
                product_id=p,
                first_ship=global_first[p],
                last_ship=global_last[p],
            )
        return idx

    @classmethod
    def from_windows(
        cls,
        *,
        distributor_windows: dict[tuple[str, int], ShipmentWindow],
        global_windows: dict[int, ShipmentWindow] | None = None,
    ) -> "ProductShipmentWindowIndex":
        """Test helper — build an index without a database."""
        idx = cls()
        idx._by_dist = dict(distributor_windows)
        idx._global = dict(global_windows or {})
        for (canon, pid), win in distributor_windows.items():
            g = idx._global.get(int(pid))
            if g is None:
                idx._global[int(pid)] = win
            else:
                idx._global[int(pid)] = ShipmentWindow(
                    product_id=int(pid),
                    first_ship=min(g.first_ship, win.first_ship),
                    last_ship=max(g.last_ship, win.last_ship),
                )
        return idx

    def distributor_window(self, canonical_distributor_key: str, product_id: int) -> ShipmentWindow | None:
        return self._by_dist.get((canonical_distributor_key, int(product_id)))

    def global_window(self, product_id: int) -> ShipmentWindow | None:
        return self._global.get(int(product_id))


def _serialize_window(win: ShipmentWindow, *, scope: str) -> dict[str, Any]:
    return {
        "product_id": int(win.product_id),
        "first_ship": win.first_ship.isoformat(),
        "last_ship": win.last_ship.isoformat(),
        "scope": scope,
    }


def _feasible_at_distributor(
    eligible_product_ids: list[int],
    *,
    canonical_distributor_key: str,
    evidence_date: date,
    window_index: ProductShipmentWindowIndex,
) -> tuple[list[int], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (feasible_ids, distributor_windows, global_ordering_windows) for eligible survivors."""
    dist_windows: list[dict[str, Any]] = []
    global_windows: list[dict[str, Any]] = []
    feasible: list[int] = []
    for pid in sorted({int(x) for x in eligible_product_ids if int(x) > 0}):
        gw = window_index.global_window(pid)
        if gw is not None:
            global_windows.append(_serialize_window(gw, scope="global_ordering"))
        dw = window_index.distributor_window(canonical_distributor_key, pid)
        if dw is None:
            continue
        dist_windows.append(_serialize_window(dw, scope="distributor"))
        if dw.first_ship <= evidence_date:
            feasible.append(int(pid))
    return feasible, dist_windows, global_windows


def try_temporal_supersession_product(
    window_index: ProductShipmentWindowIndex | None,
    *,
    distributor_id: int | None,
    dist_id_to_canonical: dict[int, str],
    eligible_product_ids: list[int],
    evidence_date: date | None,
    ambiguous_eligible: dict[str, Any] | None,
) -> TemporalSupersessionResult:
    """Residue tier after receipt disambiguation. Per-line date feasibility at distributor scope."""
    if window_index is None or not eligible_product_ids or ambiguous_eligible is None:
        return TemporalSupersessionResult(None, None)
    if distributor_id is None or evidence_date is None:
        return TemporalSupersessionResult(None, None)

    elig = sorted({int(x) for x in eligible_product_ids if int(x) > 0})
    if len(elig) < 2:
        return TemporalSupersessionResult(None, None)

    canon = dist_id_to_canonical.get(int(distributor_id)) or canonical_provisional_entity_name_key(
        str(distributor_id)
    )
    if not canon:
        return TemporalSupersessionResult(None, None)

    feasible, dist_windows, global_windows = _feasible_at_distributor(
        elig,
        canonical_distributor_key=canon,
        evidence_date=evidence_date,
        window_index=window_index,
    )
    if not dist_windows:
        return TemporalSupersessionResult(None, None)

    base_ev: dict[str, Any] = {
        "match_reason": REASON_TEMPORAL_SUPERSESSION,
        "canonical_distributor_key": canon,
        "evidence_date": evidence_date.isoformat(),
        "eligible_product_ids": elig,
        "distributor_ship_windows": dist_windows,
        "global_ordering_windows": global_windows,
    }

    if len(feasible) == 1:
        pick = int(feasible[0])
        return TemporalSupersessionResult(
            pick,
            REASON_TEMPORAL_SUPERSESSION,
            evidence={
                **base_ev,
                "status": STATUS_RESOLVED,
                "resolved_product_id": pick,
                "feasible_product_ids": feasible,
                "fifo_candidate": False,
                "feasibility_basis": "distributor_first_ship_lte_evidence_date",
            },
        )

    if len(feasible) >= 2:
        return TemporalSupersessionResult(
            None,
            None,
            evidence={
                **base_ev,
                "status": STATUS_FIFO_CANDIDATE,
                "feasible_product_ids": feasible,
                "fifo_candidate": True,
                "summary": (
                    "Multiple volume-shipped SKUs are date-feasible at this distributor; "
                    "no silent FIFO — steward or opt-in pass required."
                ),
            },
        )

    return TemporalSupersessionResult(None, None)
