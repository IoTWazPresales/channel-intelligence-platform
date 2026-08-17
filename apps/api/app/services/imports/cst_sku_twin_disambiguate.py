"""SKU-twin pick for one CST sales-model name that hits multiple dim_product rows.

CST article-alias import used unique-match-or-skip, so these ASINs never became
rows. DSI already has temporal supersession; this is the CST-alias grain of the
same idea: lifecycle filter, then inbound POD windows. Propose only — never
silent-confirm. FLAG ≠ BLOCK: a tied pick still writes a proposed alias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.dimensions import DimProduct

_LIFECYCLE_RANK: dict[str, int] = {
    "published": 0,
    "standby": 1,
    "disabled": 2,
    "discarded": 3,
}


@dataclass(frozen=True, slots=True)
class ProductLite:
    product_id: int
    sku: str
    lifecycle_status: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class InboundWindow:
    product_id: int
    first_pod: date | None
    last_pod: date | None
    qty: float
    scope: str  # customer | global | none


@dataclass(frozen=True, slots=True)
class SkuTwinPick:
    product_id: int
    reason: str
    flag: bool
    candidates: tuple[ProductLite, ...]
    windows: tuple[InboundWindow, ...]
    as_of: date | None
    shipping_scope: str

    def as_evidence(self) -> dict[str, Any]:
        return {
            "sku_twin": True,
            "sku_twin_flag": bool(self.flag),
            "sku_twin_pick_reason": self.reason,
            "sku_twin_shipping_scope": self.shipping_scope,
            "sku_twin_as_of": self.as_of.isoformat() if self.as_of else None,
            "unique_pm_match": False,
            "sku_twin_candidates": [
                {
                    "product_id": c.product_id,
                    "sku": c.sku,
                    "lifecycle_status": c.lifecycle_status,
                }
                for c in self.candidates
            ],
            "sku_twin_windows": [
                {
                    "product_id": w.product_id,
                    "first_pod": w.first_pod.isoformat() if w.first_pod else None,
                    "last_pod": w.last_pod.isoformat() if w.last_pod else None,
                    "qty": w.qty,
                    "scope": w.scope,
                }
                for w in self.windows
            ],
        }


def lifecycle_rank(status: str | None) -> int:
    key = (status or "").strip().lower()
    return _LIFECYCLE_RANK.get(key, 99)


def filter_by_best_lifecycle(rows: list[ProductLite]) -> list[ProductLite]:
    if not rows:
        return []
    best = min(lifecycle_rank(r.lifecycle_status) for r in rows)
    return [r for r in rows if lifecycle_rank(r.lifecycle_status) == best]


def window_in_channel(window: InboundWindow, as_of: date) -> bool:
    """DSI-style: first inbound on or before as_of (SKU already in channel)."""
    if window.first_pod is None:
        return False
    return window.first_pod <= as_of


def pick_sku_twin(
    survivors: list[ProductLite],
    windows_by_id: dict[int, InboundWindow],
    *,
    as_of: date,
    shipping_scope: str,
) -> SkuTwinPick | None:
    if not survivors:
        return None
    all_windows = tuple(windows_by_id[int(p.product_id)] for p in survivors if int(p.product_id) in windows_by_id)
    if len(survivors) == 1:
        only = survivors[0]
        return SkuTwinPick(
            product_id=int(only.product_id),
            reason="lifecycle_filter",
            flag=False,
            candidates=tuple(survivors),
            windows=all_windows,
            as_of=as_of,
            shipping_scope=shipping_scope,
        )

    shipped = [p for p in survivors if (windows_by_id.get(int(p.product_id)) or InboundWindow(
        int(p.product_id), None, None, 0.0, "none"
    )).first_pod is not None]
    if len(shipped) == 1:
        pick = shipped[0]
        return SkuTwinPick(
            product_id=int(pick.product_id),
            reason="shipping_unique",
            flag=False,
            candidates=tuple(survivors),
            windows=all_windows,
            as_of=as_of,
            shipping_scope=shipping_scope,
        )

    feasible = [
        p
        for p in survivors
        if window_in_channel(
            windows_by_id.get(int(p.product_id))
            or InboundWindow(int(p.product_id), None, None, 0.0, "none"),
            as_of,
        )
    ]
    if len(feasible) == 1:
        pick = feasible[0]
        return SkuTwinPick(
            product_id=int(pick.product_id),
            reason="shipping_as_of",
            flag=False,
            candidates=tuple(survivors),
            windows=all_windows,
            as_of=as_of,
            shipping_scope=shipping_scope,
        )

    pool = feasible or shipped or survivors

    def _tie_key(p: ProductLite) -> tuple:
        w = windows_by_id.get(int(p.product_id)) or InboundWindow(
            int(p.product_id), None, None, 0.0, "none"
        )
        last = w.last_pod or date.min
        return (last, w.qty, -int(p.product_id))

    prefill = max(pool, key=_tie_key)
    reason = "tied_prefill" if len(pool) > 1 else "no_shipping_prefill"
    return SkuTwinPick(
        product_id=int(prefill.product_id),
        reason=reason,
        flag=True,
        candidates=tuple(survivors),
        windows=all_windows,
        as_of=as_of,
        shipping_scope=shipping_scope,
    )


def _load_products(session: Session, product_ids: list[int]) -> list[ProductLite]:
    ids = sorted({int(x) for x in product_ids if int(x) > 0})
    if not ids:
        return []
    rows = list(session.scalars(select(DimProduct).where(DimProduct.id.in_(ids))).all())
    return [
        ProductLite(
            product_id=int(r.id),
            sku=str(r.sku or ""),
            lifecycle_status=str(r.lifecycle_status) if r.lifecycle_status else None,
            is_active=bool(r.is_active),
        )
        for r in rows
    ]


def _fetch_windows(
    session: Session,
    product_ids: list[int],
    *,
    customer_id: int | None,
) -> dict[int, InboundWindow]:
    ids = sorted({int(x) for x in product_ids if int(x) > 0})
    empty = {
        i: InboundWindow(product_id=i, first_pod=None, last_pod=None, qty=0.0, scope="none")
        for i in ids
    }
    if not ids:
        return empty

    def _run(scope: str, cid: int | None) -> dict[int, InboundWindow]:
        sql = """
            SELECT
                product_id,
                min(pod_date) FILTER (WHERE pod_date IS NOT NULL) AS min_pod,
                max(pod_date) FILTER (WHERE pod_date IS NOT NULL) AS max_pod,
                min(ship_confirm_date) FILTER (WHERE ship_confirm_date IS NOT NULL) AS min_ship,
                max(ship_confirm_date) FILTER (WHERE ship_confirm_date IS NOT NULL) AS max_ship,
                coalesce(sum(quantity), 0) AS qty
            FROM fact_inbound_shipment
            WHERE product_id = ANY(:ids)
        """
        params: dict[str, Any] = {"ids": ids}
        if cid is not None:
            sql += " AND resolved_customer_id = :cid"
            params["cid"] = int(cid)
        sql += " GROUP BY product_id"
        out: dict[int, InboundWindow] = {}
        for row in session.execute(text(sql), params).mappings():
            pid = int(row["product_id"])
            min_pod = row["min_pod"]
            max_pod = row["max_pod"]
            min_ship = row["min_ship"]
            max_ship = row["max_ship"]
            first = min_pod or min_ship
            last = max_pod or max_ship
            qty = float(row["qty"] or 0)
            out[pid] = InboundWindow(
                product_id=pid,
                first_pod=first,
                last_pod=last,
                qty=qty,
                scope=scope if first is not None else "none",
            )
        return out

    if customer_id is not None:
        scoped = _run("customer", int(customer_id))
        if any(w.first_pod is not None for w in scoped.values()):
            merged = dict(empty)
            merged.update(scoped)
            return merged
    glob = _run("global", None)
    merged = dict(empty)
    merged.update(glob)
    return merged


def disambiguate_sales_model_sku_twins(
    session: Session,
    *,
    product_ids: list[int],
    customer_id: int | None,
    as_of: date | None = None,
) -> SkuTwinPick | None:
    """Pick one product_id among SKU twins. None only when no dim_product rows exist."""
    products = _load_products(session, product_ids)
    survivors = filter_by_best_lifecycle(products)
    if not survivors:
        return None
    day = as_of or date.today()
    windows = _fetch_windows(session, [p.product_id for p in survivors], customer_id=customer_id)
    scope = "none"
    if any(w.scope == "customer" for w in windows.values()):
        scope = "customer"
    elif any(w.scope == "global" for w in windows.values()):
        scope = "global"
    return pick_sku_twin(survivors, windows, as_of=day, shipping_scope=scope)


def sku_twin_blocks_auto_confirm(evidence: dict[str, Any] | None) -> bool:
    if not isinstance(evidence, dict):
        return False
    return bool(evidence.get("sku_twin"))
