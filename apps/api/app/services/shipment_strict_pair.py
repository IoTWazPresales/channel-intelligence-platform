"""An open shipment line counts only for what its shipped twin has not shipped yet.

The pair is tenant + operating unit + order number + item code (trimmed, lower
case). A looser order-number join is not a pair. Blank order or item never pairs.
Fact rows are never rewritten; readers decide what to count.

Two decisions (Warren 2026-10-07):

- D-0057: an open line whose strict shipped twin exists does not count again.
- D-0065: partial shipments count the remainder. The shipped quantity of every
  shipped twin of the key is summed. When the open quantity is above that total,
  the open line still counts as one open line and its quantity is
  ``open - shipped``. When the open quantity is at or below it, the open line is
  skipped, as in D-0057. Shipped and arrived rows are never adjusted.
- Value of a partly shipped open line (N-0071, 2026-10-07): pro-rata,
  ``amount x remainder / open quantity``. A covered (skipped) line counts 0; a line
  with no shipped twin counts its stored amount.

Readers use :func:`keep_counted_line` (line counts and row lists) and
:func:`twin_remainder` (``counted_quantity`` for quantity totals and weights,
``counted_amount`` for money totals). Raw SQL readers use
:data:`OPEN_TWIN_REMAINDER_SQL` with :data:`TWIN_KEPT_SQL`,
:data:`TWIN_COUNTED_QTY_SQL` and :data:`TWIN_COUNTED_AMOUNT_SQL`.

The older D-0057 helpers (:func:`exclude_open_when_shipped_twin`,
:func:`open_has_shipped_twin`, :data:`OPEN_HAS_SHIPPED_TWIN_SQL`) skip the whole
open line, partial or not. Since N-0071 round 3 no product reader uses them; they
are kept for the tests that pin D-0057 and for read-only probes.

Performance (N-0071, cip under N-0065 row security, which makes the planner
estimate about 25-50 rows for any scan of this table): every form here is
uncorrelated and computed once per statement.

- The D-0065 forms read the table once with a window over the strict key. A
  self-join of open rows to shipped totals became a 21 s nested loop.
- ``keep_counted_line`` is ``id NOT IN (...)``, a hashed subplan (~0.5 s).
- ``twin_remainder`` is a MATERIALIZED CTE; as a plain subquery a selective outer
  filter re-ran it per outer row (20.7 s for the current-incoming KPI).
- A correlated ``EXISTS`` re-scanned the table for each open row (> 2 minutes).
- Do not put ``open_has_shipped_twin`` alone in a positive ``WHERE``
  (``WHERE open AND open_has_shipped_twin``): that was a 35 s plan. Use it under
  ``NOT`` / ``OR`` / ``FILTER``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, case, func, literal_column, or_, select, tuple_
from sqlalchemy.orm import aliased

# --- D-0065: remainder ---------------------------------------------------------------------

OPEN_TWIN_REMAINDER_SQL = """
SELECT
  keyed.fact_id,
  CASE
    WHEN keyed.open_qty > keyed.shipped_qty THEN keyed.open_qty - keyed.shipped_qty
    ELSE 0
  END AS counted_qty
FROM (
  SELECT
    id AS fact_id,
    lower(line_state) AS state,
    coalesce(quantity, 0) AS open_qty,
    sum(CASE WHEN lower(line_state) = 'shipped' THEN coalesce(quantity, 0) ELSE 0 END)
      OVER key_window AS shipped_qty,
    sum(CASE WHEN lower(line_state) = 'shipped' THEN 1 ELSE 0 END) OVER key_window AS n_shipped
  FROM fact_inbound_shipment
  WHERE order_no IS NOT NULL
    AND item_code IS NOT NULL
    AND trim(order_no) <> ''
    AND trim(item_code) <> ''
    AND lower(line_state) IN ('shipped', 'open_order')
  WINDOW key_window AS (
    PARTITION BY
      tenant_id,
      lower(trim(coalesce(operating_unit, ''))),
      lower(trim(order_no)),
      lower(trim(item_code))
  )
) keyed
WHERE keyed.state = 'open_order'
  AND keyed.n_shipped > 0
"""
"""One row per open_order line that has a strict shipped twin: ``fact_id`` and ``counted_qty``.

``counted_qty`` is the open quantity above the summed shipped total, never below 0.
Use it as ``WITH twin_rem AS MATERIALIZED (...)`` and
``LEFT JOIN twin_rem ON twin_rem.fact_id = fact_inbound_shipment.id``; it has at most
one row per fact id. MATERIALIZED stops a selective outer filter from re-running it
per row in a nested loop.

One scan and a window over the strict key, not a self-join: under N-0065 row
security the planner under-estimates both sides of a self-join and picks a nested
loop (21 s on cip). The window form sorts 15k rows once.
"""

TWIN_KEPT_SQL = "(twin_rem.fact_id IS NULL OR twin_rem.counted_qty > 0)"
"""The line counts: no shipped twin, or an open remainder above 0 (needs the ``twin_rem`` join)."""

TWIN_COUNTED_QTY_SQL = "coalesce(twin_rem.counted_qty, fact_inbound_shipment.quantity)"
"""Quantity to total: the remainder for an open twin line, else the stored quantity."""

TWIN_COUNTED_AMOUNT_SQL = (
    "CASE WHEN twin_rem.fact_id IS NULL THEN fact_inbound_shipment.amount "
    "WHEN twin_rem.counted_qty > 0 THEN fact_inbound_shipment.amount * twin_rem.counted_qty "
    "/ nullif(fact_inbound_shipment.quantity, 0) "
    "ELSE 0 END"
)
"""Value to total (pro-rata): the stored amount, or ``amount x remainder / open qty`` for a partly shipped line."""


_EMPTY = literal_column("''")


def _pair_key(model, *, with_tenant: bool):
    key = [
        func.lower(func.trim(func.coalesce(model.operating_unit, _EMPTY))),
        func.lower(func.trim(model.order_no)),
        func.lower(func.trim(model.item_code)),
    ]
    if with_tenant:
        key.insert(0, model.tenant_id)
    return key


def _with_tenant(model) -> bool:
    return "tenant_id" in model.__table__.c


def _keyed_open_and_shipped(model, *, row_filter: Callable[[Any], Any] | None = None):
    """Open and shipped rows with a usable key, each with its key's shipped total and count.

    Same window as :data:`OPEN_TWIN_REMAINDER_SQL`.
    """
    r = aliased(model)
    key = _pair_key(r, with_tenant=_with_tenant(model))
    is_shipped = func.lower(r.line_state) == "shipped"
    extra = row_filter(r) if row_filter is not None else None
    stmt = (
        select(
            r.id.label("fact_id"),
            func.lower(r.line_state).label("state"),
            func.coalesce(r.quantity, 0).label("open_qty"),
            func.sum(case((is_shipped, func.coalesce(r.quantity, 0)), else_=0))
            .over(partition_by=key)
            .label("shipped_qty"),
            func.sum(case((is_shipped, 1), else_=0)).over(partition_by=key).label("n_shipped"),
        )
        .where(
            r.order_no.is_not(None),
            r.item_code.is_not(None),
            func.trim(r.order_no) != _EMPTY,
            func.trim(r.item_code) != _EMPTY,
            func.lower(r.line_state).in_(("shipped", "open_order")),
        )
    )
    if extra is not None:
        stmt = stmt.where(extra)
    return stmt.subquery()


def _skipped_open_twin_ids(model):
    """Ids of open lines whose strict shipped twins shipped at least the open quantity."""
    w = _keyed_open_and_shipped(model)
    return select(w.c.fact_id).where(
        w.c.state == "open_order",
        w.c.n_shipped > 0,
        w.c.open_qty <= w.c.shipped_qty,
    )


def keep_counted_line(model):
    """SQLAlchemy filter (D-0065): drop an open line only when its shipped twins cover it.

    An open line with a positive remainder stays, as one line. ``id`` is the primary
    key, so ``NOT IN`` never turns NULL. Use it for line counts and row lists; for
    quantity totals use :func:`twin_remainder`.
    """
    return model.id.not_in(_skipped_open_twin_ids(model))


def skipped_open_twin_line(model):
    """SQLAlchemy predicate: this open line is skipped under D-0065 (for a FILTER count)."""
    return model.id.in_(_skipped_open_twin_ids(model))


@dataclass(frozen=True)
class TwinRemainder:
    """Outer-join pieces for quantity and value readers (D-0065 + pro-rata value).

    ``stmt.outerjoin(r.subquery, r.onclause).where(r.kept)``, then total
    ``r.counted_quantity`` (units) or ``r.counted_amount`` (money).
    """

    subquery: Any
    onclause: Any
    kept: Any
    counted_quantity: Any
    is_partial_twin: Any
    counted_amount: Any


def _counted_amount(model, counted_qty):
    """Pro-rata value (Warren 2026-10-07, N-0071): ``amount x remainder / open quantity``.

    ``counted_qty`` is the remainder column of the join (NULL when the row has no shipped
    twin). No twin: the stored amount. Partly shipped: the pro-rata share. Covered: 0.
    A zero open quantity gives NULL (nothing to pro-rate), which a SUM ignores.
    """
    return case(
        (counted_qty.is_(None), model.amount),
        (counted_qty > 0, model.amount * counted_qty / func.nullif(model.quantity, 0)),
        else_=0,
    )


def twin_remainder(model, *, row_filter: Callable[[Any], Any] | None = None) -> TwinRemainder:
    """Remainder join for ``model``.

    ``row_filter(alias)`` optionally limits the rows the shipped totals are summed over
    (for example the active-evidence predicate on ``shipment_evidence_line``, where
    superseded rows must not add to the shipped total); it returns a predicate or None.
    """
    w = _keyed_open_and_shipped(model, row_filter=row_filter)
    remainder = case((w.c.open_qty > w.c.shipped_qty, w.c.open_qty - w.c.shipped_qty), else_=0)
    # MATERIALIZED: computed once per statement. As a plain subquery, a selective outer
    # filter (e.g. the current-incoming KPI cohort) made the planner re-run the window
    # once per outer row in a nested loop (20.7 s on cip); the CTE keeps it to one pass.
    sub = (
        select(w.c.fact_id, remainder.label("counted_qty"))
        .where(w.c.state == "open_order", w.c.n_shipped > 0)
        .cte()
        .prefix_with("MATERIALIZED")
    )
    return TwinRemainder(
        subquery=sub,
        onclause=sub.c.fact_id == model.id,
        kept=or_(sub.c.fact_id.is_(None), sub.c.counted_qty > 0),
        counted_quantity=func.coalesce(sub.c.counted_qty, model.quantity),
        is_partial_twin=and_(sub.c.fact_id.is_not(None), sub.c.counted_qty > 0),
        counted_amount=_counted_amount(model, sub.c.counted_qty),
    )


def outerjoin_twin_remainder(
    stmt, model, *, row_filter: Callable[[Any], Any] | None = None
) -> tuple[Any, TwinRemainder]:
    """Add the remainder join and the kept-line filter to ``stmt``."""
    r = twin_remainder(model, row_filter=row_filter)
    return stmt.outerjoin(r.subquery, r.onclause).where(r.kept), r


# --- D-0057: whole-line skip (no product reader since N-0071 round 3) ----------------------

OPEN_HAS_SHIPPED_TWIN_SQL = """
(
  trim(coalesce(fact_inbound_shipment.order_no, '')) <> ''
  AND trim(coalesce(fact_inbound_shipment.item_code, '')) <> ''
  AND lower(fact_inbound_shipment.line_state) <> 'shipped'
  AND (
    fact_inbound_shipment.tenant_id,
    lower(trim(coalesce(fact_inbound_shipment.operating_unit, ''))),
    lower(trim(fact_inbound_shipment.order_no)),
    lower(trim(fact_inbound_shipment.item_code))
  ) IN (
    SELECT
      shipped_twin.tenant_id,
      lower(trim(coalesce(shipped_twin.operating_unit, ''))),
      lower(trim(shipped_twin.order_no)),
      lower(trim(shipped_twin.item_code))
    FROM fact_inbound_shipment shipped_twin
    WHERE lower(shipped_twin.line_state) = 'shipped'
      AND shipped_twin.order_no IS NOT NULL
      AND shipped_twin.item_code IS NOT NULL
  )
)
"""
"""SQL text for raw queries over ``fact_inbound_shipment``: true when an open row has a strict shipped twin.

Use as ``lower(line_state) = 'open_order' AND {OPEN_HAS_SHIPPED_TWIN_SQL}``. The
subquery never yields a NULL key, so ``NOT (...)`` is a clean true/false.
"""


def open_has_shipped_twin(model):
    """SQLAlchemy predicate: this row is not shipped and a strict shipped twin exists (any quantity)."""
    twin = aliased(model)
    with_tenant = _with_tenant(model)
    shipped_keys = select(*_pair_key(twin, with_tenant=with_tenant)).where(
        func.lower(twin.line_state) == "shipped",
        twin.order_no.is_not(None),
        twin.item_code.is_not(None),
    )
    return and_(
        func.trim(func.coalesce(model.order_no, "")) != "",
        func.trim(func.coalesce(model.item_code, "")) != "",
        func.lower(model.line_state) != "shipped",
        tuple_(*_pair_key(model, with_tenant=with_tenant)).in_(shipped_keys),
    )


def exclude_open_when_shipped_twin(model):
    """SQLAlchemy filter (D-0057): drop an open_order row that has a strict shipped twin, partial or not."""
    return or_(
        func.lower(model.line_state) != "open_order",
        ~open_has_shipped_twin(model),
    )
