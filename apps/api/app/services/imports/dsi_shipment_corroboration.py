"""Read-only shipment_evidence_line corroboration for DSI (signal-only; no auto-resolve).

Two execution modes:

1. **Per-row DB queries** (original): each call to ``shipment_corroboration_for_product`` /
   ``shipment_corroboration_for_customer`` issues 2-4 queries against
   ``shipment_evidence_line``. Correct for single-row steward refresh.

2. **Pre-loaded cache** (bulk validation): call
   ``ShipmentCorroborationCache.load(db, evidence_months)`` once before the row
   loop, then use ``cache.product_corroboration(...)`` /
   ``cache.customer_corroboration(...)`` for pure in-memory lookups.
   Reduces N×6 DB round-trips to 2 batch queries regardless of file size.

``process_distributor_sales_inventory`` pre-loads the cache before its row loop.
The per-row DB functions remain available for single-row steward refresh paths.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import Date, and_, func, literal, or_, select, text
from sqlalchemy.orm import Session

from app.models.shipment_evidence import ShipmentEvidenceLine

logger = logging.getLogger(__name__)

# Steward apply sets ``resolved``; import-time product auto-resolve uses ``resolved_unique``.
_CUSTOMER_CORROBORATION_STATUSES = ("resolved", "resolved_unique")


# ---------------------------------------------------------------------------
# Helpers shared by both DB-query path and in-memory cache path
# ---------------------------------------------------------------------------

def _same_calendar_month_as_evidence(evidence_date: date) -> Any:
    co = func.coalesce(
        ShipmentEvidenceLine.ship_confirm_date,
        ShipmentEvidenceLine.schedule_ship_date,
        ShipmentEvidenceLine.promise_date,
    )
    return and_(
        co.isnot(None),
        func.date_trunc("month", co) == func.date_trunc("month", literal(evidence_date, type_=Date())),
    )


# ---------------------------------------------------------------------------
# Pre-loaded in-memory cache — used by process_distributor_sales_inventory
# ---------------------------------------------------------------------------

class ShipmentCorroborationCache:
    """In-memory cache of resolved shipment evidence rows for fast DSI corroboration.

    Replaces N×6 per-row DB queries with 2 batch queries at the start of a
    DSI validate job.  Pre-load via ``ShipmentCorroborationCache.load()``.

    Data structures:
    - ``_prod[(distributor_id, "YYYY-MM")]`` → list of
      ``(product_id, item_key, ean_key, upc_key, sm_key)`` tuples
    - ``_prod_cross["YYYY-MM"]`` → same list but ignoring distributor (for
      cross-distributor fallback)
    - ``_cust[(distributor_id, "YYYY-MM")]`` → list of
      ``(customer_id, cust_token_key, bill_to_lower, ship_to_lower)`` tuples
    """

    __slots__ = ("_prod", "_prod_cross", "_cust")

    def __init__(self) -> None:
        self._prod: dict[tuple[int | None, str], list[tuple[int, str, str, str, str]]] = defaultdict(list)
        self._prod_cross: dict[str, list[tuple[int, str, str, str, str]]] = defaultdict(list)
        self._cust: dict[tuple[int | None, str], list[tuple[int, str, str, str]]] = defaultdict(list)

    @classmethod
    def load(cls, db: Session, evidence_months: set[str]) -> "ShipmentCorroborationCache":
        """Pre-load resolved shipment evidence for the given evidence months.

        Runs 2 batch queries regardless of file row count.  ``evidence_months``
        is a set of "YYYY-MM" strings derived from the DSI file's date columns.

        Returns an empty cache when ``evidence_months`` is empty.
        """
        cache = cls()
        if not evidence_months:
            logger.debug("ShipmentCorroborationCache: no evidence months — returning empty cache")
            return cache

        month_list = sorted(evidence_months)
        logger.info(
            "ShipmentCorroborationCache.load: pre-loading evidence for %d months: %s",
            len(month_list),
            month_list,
        )

        # --- product corroboration rows ---
        # Filter by product_resolution_status='resolved_unique' (has an index).
        # date_trunc + to_char are applied inside DB to avoid loading every row.
        prod_rows = db.execute(
            text("""
                SELECT
                    distributor_id,
                    product_id,
                    to_char(
                        date_trunc('month',
                            COALESCE(ship_confirm_date, schedule_ship_date, promise_date)),
                        'YYYY-MM'
                    ) AS ev_month,
                    lower(btrim(coalesce(item_code,        ''))) AS item_key,
                    lower(btrim(coalesce(ean_code,         ''))) AS ean_key,
                    lower(btrim(coalesce(upc_code,         ''))) AS upc_key,
                    lower(btrim(coalesce(sales_model_name, ''))) AS sm_key
                FROM shipment_evidence_line
                WHERE product_resolution_status = 'resolved_unique'
                  AND product_id IS NOT NULL
                  AND COALESCE(ship_confirm_date, schedule_ship_date, promise_date) IS NOT NULL
            """)
        ).fetchall()

        # Filter to only the months we need (done in Python to avoid the
        # un-indexed date_trunc scan being used as a WHERE filter).
        month_set = set(month_list)
        for r in prod_rows:
            em: str = r[2] or ""
            if em not in month_set:
                continue
            dist_id: int | None = r[0]
            pid = int(r[1])
            item_k, ean_k, upc_k, sm_k = (r[3] or ""), (r[4] or ""), (r[5] or ""), (r[6] or "")
            entry: tuple[int, str, str, str, str] = (pid, item_k, ean_k, upc_k, sm_k)
            cache._prod[(dist_id, em)].append(entry)
            cache._prod_cross[em].append(entry)

        logger.info(
            "ShipmentCorroborationCache: loaded %d product evidence rows (%d relevant months)",
            len(prod_rows),
            len(month_set),
        )

        # --- customer corroboration rows ---
        # Restrict to distributor-resolved rows that also have customer_id.
        cust_rows = db.execute(
            text("""
                SELECT
                    distributor_id,
                    customer_id,
                    to_char(
                        date_trunc('month',
                            COALESCE(ship_confirm_date, schedule_ship_date, promise_date)),
                        'YYYY-MM'
                    ) AS ev_month,
                    lower(btrim(coalesce(customer_dealer_token, ''))) AS cust_token_key,
                    lower(coalesce(bill_to_raw,  '')) AS bill_to_lower,
                    lower(coalesce(ship_to_raw,  '')) AS ship_to_lower
                FROM shipment_evidence_line
                WHERE customer_id IS NOT NULL
                  AND customer_resolution_status IN ('resolved', 'resolved_unique')
                  AND distributor_id IS NOT NULL
                  AND COALESCE(ship_confirm_date, schedule_ship_date, promise_date) IS NOT NULL
            """)
        ).fetchall()

        for r in cust_rows:
            em = r[2] or ""
            if em not in month_set:
                continue
            dist_id = r[0]
            cid = int(r[1])
            cust_k = r[3] or ""
            bill_l = r[4] or ""
            ship_l = r[5] or ""
            cache._cust[(dist_id, em)].append((cid, cust_k, bill_l, ship_l))

        logger.info(
            "ShipmentCorroborationCache: loaded %d customer evidence rows",
            len(cust_rows),
        )

        return cache

    # ------------------------------------------------------------------
    # Lookup methods (mirrors the DB-query functions below)
    # ------------------------------------------------------------------

    def product_corroboration(
        self,
        distributor_id: int,
        evidence_date: date,
        *,
        raw_product_token: str | None = None,
        resolved_product_id: int | None = None,
    ) -> dict[str, Any] | None:
        """In-memory equivalent of ``shipment_corroboration_for_product``."""
        em = evidence_date.strftime("%Y-%m")
        dist_entries = self._prod.get((distributor_id, em), [])

        if resolved_product_id is not None:
            matches = [e for e in dist_entries if e[0] == resolved_product_id]
            if not matches:
                return None
            return {
                "kind": "shipment_evidence_product",
                "match_count": len(matches),
                "mode": "resolved_product_id",
                "distributor_id": int(distributor_id),
                "evidence_month": em,
                "distinct_resolved_product_ids": sorted({e[0] for e in matches})[:32],
                "distinct_ids_scope": "distributor_specific",
            }

        # raw-token path — needs _product_token_key; lazy import to break circular
        from app.services.imports.distributor_sales_inventory import _product_token_key

        pk = _product_token_key(raw_product_token)
        if not pk:
            return None

        # Distributor-specific
        dist_tok_matches = [e for e in dist_entries if pk in (e[1], e[2], e[3], e[4])]
        if dist_tok_matches:
            dist_ids = sorted({e[0] for e in dist_tok_matches})[:32]
            return {
                "kind": "shipment_evidence_product",
                "match_count": len(dist_tok_matches),
                "mode": "raw_product_token_tiers",
                "distributor_id": int(distributor_id),
                "evidence_month": em,
                "distinct_resolved_product_ids": dist_ids,
                "distinct_ids_scope": "distributor_specific",
            }

        # Cross-distributor fallback
        cross_entries = self._prod_cross.get(em, [])
        cross_tok_matches = [e for e in cross_entries if pk in (e[1], e[2], e[3], e[4])]
        if not cross_tok_matches:
            return None
        cross_ids = sorted({e[0] for e in cross_tok_matches})[:32]
        if len(cross_ids) != 1:
            return None
        return {
            "kind": "shipment_evidence_product",
            "match_count": len(cross_tok_matches),
            "mode": "raw_product_token_tiers",
            "distributor_id": int(distributor_id),
            "evidence_month": em,
            "distinct_resolved_product_ids": cross_ids,
            "distinct_ids_scope": "cross_distributor",
        }

    def customer_corroboration(
        self,
        distributor_id: int,
        evidence_date: date,
        *,
        customer_primary_raw: str | None = None,
        dealer_group_raw: str | None = None,
        resolved_customer_id: int | None = None,
    ) -> dict[str, Any] | None:
        """In-memory equivalent of ``shipment_corroboration_for_customer``."""
        em = evidence_date.strftime("%Y-%m")
        dist_entries = self._cust.get((distributor_id, em), [])

        if resolved_customer_id is not None:
            matches = [e for e in dist_entries if e[0] == resolved_customer_id]
            if not matches:
                return None
            return {
                "kind": "shipment_evidence_customer",
                "match_count": len(matches),
                "mode": "resolved_customer_id",
                "distributor_id": int(distributor_id),
                "evidence_month": em,
            }

        from app.services.imports.distributor_sales_inventory import _norm_key

        nk = _norm_key(customer_primary_raw or "")
        dg = (dealer_group_raw or "").strip()[:512].lower() if dealer_group_raw else ""
        if not nk and not dg:
            return None

        matches_out: list[tuple] = []
        for e in dist_entries:
            _cid, cust_k, bill_l, ship_l = e
            matched = False
            if nk and cust_k == nk:
                matched = True
            if not matched and dg and (dg in bill_l or dg in ship_l):
                matched = True
            if matched:
                matches_out.append(e)

        if not matches_out:
            return None
        return {
            "kind": "shipment_evidence_customer",
            "match_count": len(matches_out),
            "mode": "raw_token_fuzzy",
            "distributor_id": int(distributor_id),
            "evidence_month": em,
        }


# ---------------------------------------------------------------------------
# Per-row DB-query functions (used by steward single-row refresh paths)
# ---------------------------------------------------------------------------

def shipment_corroboration_for_product(
    db: Session,
    *,
    distributor_id: int,
    evidence_date: date | None,
    raw_product_token: str | None,
    resolved_product_id: int | None,
) -> dict[str, Any] | None:
    """Return JSON-serializable corroboration dict, or None when lookup is not applicable.

    Includes ``distinct_resolved_product_ids``: distinct ``ShipmentEvidenceLine.product_id`` values
    among matching **resolved_unique** lines in the evidence month (used to break DSI ambiguity).

    For raw-token matching, rows are first limited to the DSI **distributor_id**. If that scope yields
    no distinct product ids, the same token + month match is retried **across all distributors**; when
    that broader set contains exactly one distinct ``product_id``, it is returned and
    ``distinct_ids_scope`` is ``cross_distributor``. Otherwise ``distinct_ids_scope`` is
    ``distributor_specific`` when the distributor-scoped set is non-empty.
    """
    if not distributor_id or evidence_date is None:
        return None
    base_where = (
        ShipmentEvidenceLine.distributor_id == int(distributor_id),
        ShipmentEvidenceLine.product_resolution_status == "resolved_unique",
        ShipmentEvidenceLine.product_id.isnot(None),
        _same_calendar_month_as_evidence(evidence_date),
    )
    base_count = select(func.count()).select_from(ShipmentEvidenceLine).where(*base_where)
    if resolved_product_id is not None:
        n = db.scalar(base_count.where(ShipmentEvidenceLine.product_id == int(resolved_product_id)))
        mode = "resolved_product_id"
        ids_stmt = (
            select(ShipmentEvidenceLine.product_id)
            .where(*base_where, ShipmentEvidenceLine.product_id == int(resolved_product_id))
            .distinct()
        )
        cnt = int(n or 0)
        if cnt <= 0:
            return None
        raw_ids = list(db.scalars(ids_stmt).all())
        distinct_ids = sorted({int(x) for x in raw_ids if x is not None})[:32]
        return {
            "kind": "shipment_evidence_product",
            "match_count": cnt,
            "mode": mode,
            "distributor_id": int(distributor_id),
            "evidence_month": evidence_date.isoformat()[:7],
            "distinct_resolved_product_ids": distinct_ids,
            "distinct_ids_scope": "distributor_specific",
        }

    from app.services.imports.distributor_sales_inventory import _product_token_key

    pk = _product_token_key(raw_product_token)
    if not pk:
        return None
    token_match = or_(
        func.lower(func.btrim(func.coalesce(ShipmentEvidenceLine.item_code, ""))) == literal(pk),
        func.lower(func.btrim(func.coalesce(ShipmentEvidenceLine.ean_code, ""))) == literal(pk),
        func.lower(func.btrim(func.coalesce(ShipmentEvidenceLine.upc_code, ""))) == literal(pk),
        func.lower(func.btrim(func.coalesce(ShipmentEvidenceLine.sales_model_name, ""))) == literal(pk),
    )
    mode = "raw_product_token_tiers"

    n_dist = db.scalar(base_count.where(token_match))
    ids_dist_stmt = select(ShipmentEvidenceLine.product_id).where(*base_where, token_match).distinct()
    distinct_dist: list[int] = []
    if n_dist and int(n_dist) > 0:
        raw_d = list(db.scalars(ids_dist_stmt).all())
        distinct_dist = sorted({int(x) for x in raw_d if x is not None})[:32]

    if distinct_dist:
        return {
            "kind": "shipment_evidence_product",
            "match_count": int(n_dist or 0),
            "mode": mode,
            "distributor_id": int(distributor_id),
            "evidence_month": evidence_date.isoformat()[:7],
            "distinct_resolved_product_ids": distinct_dist,
            "distinct_ids_scope": "distributor_specific",
        }

    cross_where = (
        ShipmentEvidenceLine.product_resolution_status == "resolved_unique",
        ShipmentEvidenceLine.product_id.isnot(None),
        _same_calendar_month_as_evidence(evidence_date),
        token_match,
    )
    cross_count = select(func.count()).select_from(ShipmentEvidenceLine).where(*cross_where)
    n_cross = db.scalar(cross_count)
    if not n_cross or int(n_cross) <= 0:
        return None
    ids_cross_stmt = select(ShipmentEvidenceLine.product_id).where(*cross_where).distinct()
    raw_c = list(db.scalars(ids_cross_stmt).all())
    distinct_cross = sorted({int(x) for x in raw_c if x is not None})[:32]
    if len(distinct_cross) != 1:
        return None
    return {
        "kind": "shipment_evidence_product",
        "match_count": int(n_cross or 0),
        "mode": mode,
        "distributor_id": int(distributor_id),
        "evidence_month": evidence_date.isoformat()[:7],
        "distinct_resolved_product_ids": distinct_cross,
        "distinct_ids_scope": "cross_distributor",
    }


def shipment_corroboration_for_customer(
    db: Session,
    *,
    distributor_id: int,
    evidence_date: date | None,
    customer_primary_raw: str | None,
    dealer_group_raw: str | None,
    resolved_customer_id: int | None,
) -> dict[str, Any] | None:
    if not distributor_id or evidence_date is None:
        return None
    base = (
        select(func.count())
        .select_from(ShipmentEvidenceLine)
        .where(
            ShipmentEvidenceLine.distributor_id == int(distributor_id),
            ShipmentEvidenceLine.customer_id.isnot(None),
            ShipmentEvidenceLine.customer_resolution_status.in_(_CUSTOMER_CORROBORATION_STATUSES),
            _same_calendar_month_as_evidence(evidence_date),
        )
    )
    if resolved_customer_id is not None:
        n = db.scalar(base.where(ShipmentEvidenceLine.customer_id == int(resolved_customer_id)))
        mode = "resolved_customer_id"
    else:
        from app.services.imports.distributor_sales_inventory import _norm_key

        nk = _norm_key(customer_primary_raw or "")
        dg = (dealer_group_raw or "").strip()[:512].lower() if dealer_group_raw else ""
        if not nk and not dg:
            return None
        conds = []
        if nk:
            tok = func.nullif(func.btrim(ShipmentEvidenceLine.customer_dealer_token), "")
            conds.append(func.lower(tok) == literal(nk))
        if dg:
            esc = dg.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pat = f"%{esc}%"
            conds.append(
                or_(
                    ShipmentEvidenceLine.bill_to_raw.ilike(literal(pat), escape="\\"),
                    ShipmentEvidenceLine.ship_to_raw.ilike(literal(pat), escape="\\"),
                )
            )
        if not conds:
            return None
        n = db.scalar(base.where(or_(*conds)))
        mode = "raw_token_fuzzy"
    cnt = int(n or 0)
    if cnt <= 0:
        return None
    return {
        "kind": "shipment_evidence_customer",
        "match_count": cnt,
        "mode": mode,
        "distributor_id": int(distributor_id),
        "evidence_month": evidence_date.isoformat()[:7],
    }


