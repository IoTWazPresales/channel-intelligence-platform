"""CPOR A2-04 support norms + A2-05 comparable-case ranking.

Norms: trailing N quarters (tenant config default 4) — absolute support (USD + ZAR)
and unit support-% of SRP. Quarters from line ``pod_quarter`` (normalized) with
case ``window_start`` fallback.

Comparable: ranked never filtered — customer → BU → promo type → quarter proximity → volume.
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.cpor import CporCase
from app.models.dimensions import DimCustomer, DimProduct
from app.services.commercial_tenant_profile import (
    SUPPORT_NORMS_TRAILING_QUARTERS as TENANT_NORMS_DEFAULT,
    support_norms_trailing_quarters,
)
from app.services.cpor.pivot import _line_ttl_support_usd, is_voided_line
from app.services.cpor.portfolio_intelligence import _line_ttl_support_zar

_Q_RE = re.compile(r"^(?:20)?(\d{2})Q([1-4])$", re.IGNORECASE)


def _window_provenance(*, query_override: int | None, n: int) -> dict[str, Any]:
    """Prove whether trailing window came from tenant profile vs env/query."""
    env_raw = os.environ.get("SUPPORT_NORMS_TRAILING_QUARTERS")
    env_set = bool(env_raw and str(env_raw).strip())
    if query_override is not None:
        source = "query_param"
    elif env_set:
        source = "env_override"
    else:
        source = "commercial_tenant_profile"
    return {
        "window_source": source,
        "env_override_active": bool(env_set and query_override is None),
        "tenant_profile_default": int(TENANT_NORMS_DEFAULT),
        "trailing_quarters": n,
    }


def normalize_quarter_label(raw: str | None, *, fallback: date | None = None) -> str | None:
    """Normalize ``2025Q2`` / ``25Q2`` / ``26Q1`` → ``2025Q2``-style YYYYQn."""
    if raw and str(raw).strip():
        m = _Q_RE.match(str(raw).strip().upper().replace(" ", ""))
        if m:
            yy = int(m.group(1))
            year = 2000 + yy if yy < 100 else yy
            return f"{year}Q{m.group(2)}"
    if fallback is not None:
        q = (fallback.month - 1) // 3 + 1
        return f"{fallback.year}Q{q}"
    return None


def quarter_index(label: str) -> int | None:
    m = _Q_RE.match(label.strip().upper())
    if not m:
        return None
    yy = int(m.group(1))
    year = 2000 + yy if yy < 100 else yy
    return year * 4 + int(m.group(2))


def trailing_quarter_labels(latest: str, n: int) -> list[str]:
    idx = quarter_index(latest)
    if idx is None or n <= 0:
        return []
    out: list[str] = []
    for i in range(n):
        cur = idx - i
        year = (cur - 1) // 4
        q = ((cur - 1) % 4) + 1
        out.append(f"{year}Q{q}")
    return out


def _load_cases(session: Session) -> list[CporCase]:
    return list(
        session.scalars(
            select(CporCase)
            .where(CporCase.superseded_by_case_id.is_(None))
            .options(joinedload(CporCase.lines))
        )
        .unique()
        .all()
    )


def _product_bu_map(session: Session, product_ids: set[int]) -> dict[int, str]:
    if not product_ids:
        return {}
    rows = session.execute(
        select(DimProduct.id, DimProduct.product_line).where(DimProduct.id.in_(product_ids))
    ).all()
    return {
        int(r[0]): (str(r[1]).strip() if r[1] else None) or "(unassigned)" for r in rows
    }


def build_support_norms(
    session: Session,
    *,
    trailing_quarters: int | None = None,
) -> dict[str, Any]:
    """A2-04 — per-customer norms over trailing quarters."""
    query_override = trailing_quarters
    tenant_n = support_norms_trailing_quarters()
    n = int(trailing_quarters) if trailing_quarters is not None else tenant_n
    if n <= 0:
        n = tenant_n
    provenance = _window_provenance(query_override=query_override, n=n)

    cases = _load_cases(session)

    # (customer_id, quarter) → accumulators
    cq: dict[tuple[int, str], dict[str, float]] = defaultdict(
        lambda: {
            "support_usd": 0.0,
            "support_zar": 0.0,
            "estimate_qty": 0.0,
            "result_qty": 0.0,
            "support_pct_sum": 0.0,
            "support_pct_n": 0.0,
        }
    )
    all_quarters: set[str] = set()

    for case in cases:
        cid = int(case.customer_id)
        for line in case.lines or []:
            if is_voided_line(line):
                continue
            try:
                est = float(line.estimate_qty or 0)
            except (TypeError, ValueError):
                est = 0.0
            if est <= 0:
                continue
            q_label = normalize_quarter_label(
                getattr(line, "pod_quarter", None),
                fallback=case.window_start,
            )
            if not q_label:
                continue
            all_quarters.add(q_label)
            usd = _line_ttl_support_usd(line)
            zar = _line_ttl_support_zar(line)
            bucket = cq[(cid, q_label)]
            bucket["support_usd"] += float(usd) if usd is not None else 0.0
            bucket["support_zar"] += float(zar) if zar is not None else 0.0
            bucket["estimate_qty"] += est
            if line.result_qty is not None:
                bucket["result_qty"] += float(line.result_qty)
            try:
                srp = float(line.srp or 0)
                su = float(line.support_unit) if line.support_unit is not None else None
            except (TypeError, ValueError):
                srp, su = 0.0, None
            if su is not None and srp > 0:
                bucket["support_pct_sum"] += su / srp
                bucket["support_pct_n"] += 1.0

    if not all_quarters:
        return {
            "trailing_quarters": n,
            "window_quarters": [],
            "anchor_quarter": None,
            "by_customer": [],
            "currency_compute": "USD",
            "currency_display_secondary": "ZAR",
            **provenance,
        }

    # Latest quarter by index
    latest = max(all_quarters, key=lambda q: quarter_index(q) or 0)
    window_list = trailing_quarter_labels(latest, n)
    window = set(window_list)

    cust_ids = {cid for (cid, q) in cq if q in window}
    cust_meta: dict[int, tuple[str | None, str | None]] = {}
    if cust_ids:
        rows = session.execute(
            select(DimCustomer.id, DimCustomer.code, DimCustomer.name).where(
                DimCustomer.id.in_(cust_ids)
            )
        ).all()
        cust_meta = {int(r[0]): (r[1], r[2]) for r in rows}

    by_customer_out: list[dict[str, Any]] = []
    for cid in sorted(cust_ids):
        q_rows = []
        abs_usd = 0.0
        abs_zar = 0.0
        pct_sum = 0.0
        pct_n = 0.0
        quarters_present = 0
        for q in window_list:
            b = cq.get((cid, q))
            if not b or b["support_usd"] == 0 and b["estimate_qty"] == 0:
                q_rows.append(
                    {
                        "quarter": q,
                        "support_usd": 0.0,
                        "support_zar": 0.0,
                        "support_pct_of_srp": None,
                        "present": False,
                    }
                )
                continue
            quarters_present += 1
            abs_usd += b["support_usd"]
            abs_zar += b["support_zar"]
            pct = (b["support_pct_sum"] / b["support_pct_n"]) if b["support_pct_n"] else None
            if pct is not None:
                pct_sum += pct
                pct_n += 1
            q_rows.append(
                {
                    "quarter": q,
                    "support_usd": round(b["support_usd"], 4),
                    "support_zar": round(b["support_zar"], 4),
                    "support_pct_of_srp": pct,
                    "present": True,
                }
            )
        denom = max(quarters_present, 1)
        code, name = cust_meta.get(cid, (None, None))
        by_customer_out.append(
            {
                "customer_id": cid,
                "customer_code": code,
                "customer_name": name,
                "quarters_present": quarters_present,
                "absolute_support_usd_avg": round(abs_usd / denom, 4),
                "absolute_support_zar_avg": round(abs_zar / denom, 4),
                "absolute_support_usd_total": round(abs_usd, 4),
                "absolute_support_zar_total": round(abs_zar, 4),
                "support_pct_of_srp_avg": (pct_sum / pct_n) if pct_n else None,
                "quarters": q_rows,
            }
        )

    by_customer_out.sort(key=lambda r: -r["absolute_support_usd_total"])
    return {
        "trailing_quarters": n,
        "window_quarters": window_list,
        "anchor_quarter": latest,
        "by_customer": by_customer_out,
        "currency_compute": "USD",
        "currency_display_secondary": "ZAR",
        "pct_definition": (
            "mean(support_unit / srp) over non-voided lines with srp > 0 "
            "(§4.3 case-value % = unit support vs SRP)"
        ),
        "absolute_definition": (
            f"sum of line ttl_support_(usd|zar) in window, avg over quarters_present "
            f"(trailing {n} from {latest})"
        ),
        **provenance,
    }


def build_comparable_cases(
    session: Session,
    *,
    case_id: int,
    limit: int = 25,
) -> dict[str, Any]:
    """A2-05 — ranked comparable cases (never filtered to empty)."""
    cases = _load_cases(session)
    seed = next((c for c in cases if int(c.id) == int(case_id)), None)
    if seed is None:
        # May be superseded — try load directly
        seed = session.get(CporCase, int(case_id))
        if seed is None:
            return {"case_id": case_id, "error": "case_not_found", "items": []}

    product_ids: set[int] = set()
    for case in cases:
        for line in case.lines or []:
            if line.product_id is not None:
                product_ids.add(int(line.product_id))
    if seed.lines:
        for line in seed.lines:
            if line.product_id is not None:
                product_ids.add(int(line.product_id))
    bu_by_product = _product_bu_map(session, product_ids)

    def case_features(case: CporCase) -> dict[str, Any]:
        bus: set[str] = set()
        est = 0.0
        quarters: list[str] = []
        for line in case.lines or []:
            if is_voided_line(line):
                continue
            try:
                e = float(line.estimate_qty or 0)
            except (TypeError, ValueError):
                e = 0.0
            if e <= 0:
                continue
            est += e
            if line.product_id is not None:
                bus.add(bu_by_product.get(int(line.product_id), "(unassigned)"))
            q = normalize_quarter_label(getattr(line, "pod_quarter", None), fallback=case.window_start)
            if q:
                quarters.append(q)
        # modal quarter
        q_seed = None
        if quarters:
            q_seed = max(set(quarters), key=quarters.count)
        elif case.window_start:
            q_seed = normalize_quarter_label(None, fallback=case.window_start)
        return {
            "customer_id": int(case.customer_id) if case.customer_id else None,
            "promotion_type": (case.promotion_type or "").strip(),
            "bus": bus,
            "estimate_qty": est,
            "quarter": q_seed,
            "q_idx": quarter_index(q_seed) if q_seed else None,
        }

    seed_f = case_features(seed)
    cust_ids = {int(c.customer_id) for c in cases if c.customer_id is not None}
    cust_ids.add(int(seed.customer_id))
    cust_meta: dict[int, tuple[str | None, str | None]] = {}
    if cust_ids:
        rows = session.execute(
            select(DimCustomer.id, DimCustomer.code, DimCustomer.name).where(
                DimCustomer.id.in_(cust_ids)
            )
        ).all()
        cust_meta = {int(r[0]): (r[1], r[2]) for r in rows}

    ranked: list[dict[str, Any]] = []
    for case in cases:
        if int(case.id) == int(seed.id):
            continue
        f = case_features(case)
        # Scores — higher is better; axes ordered per semantics
        same_customer = 1 if f["customer_id"] == seed_f["customer_id"] else 0
        bu_overlap = len(f["bus"] & seed_f["bus"])
        bu_union = len(f["bus"] | seed_f["bus"]) or 1
        bu_score = bu_overlap / bu_union
        same_promo = 1 if f["promotion_type"] == seed_f["promotion_type"] else 0
        if f["q_idx"] is not None and seed_f["q_idx"] is not None:
            q_prox = 1.0 / (1.0 + abs(f["q_idx"] - seed_f["q_idx"]))
        else:
            q_prox = 0.0
        # volume similarity: 1 - relative abs diff, floored at 0
        a, b = f["estimate_qty"], seed_f["estimate_qty"]
        if a <= 0 and b <= 0:
            vol = 1.0
        elif max(a, b) <= 0:
            vol = 0.0
        else:
            vol = max(0.0, 1.0 - abs(a - b) / max(a, b))

        # Lexicographic-ish composite preserving axis priority
        composite = (
            same_customer * 1_000_000
            + bu_score * 100_000
            + same_promo * 10_000
            + q_prox * 1_000
            + vol * 100
        )
        code, name = cust_meta.get(int(case.customer_id), (None, None)) if case.customer_id else (None, None)
        ranked.append(
            {
                "case_id": int(case.id),
                "case_code": case.case_code,
                "customer_id": int(case.customer_id) if case.customer_id else None,
                "customer_code": code,
                "customer_name": name,
                "promotion_type": case.promotion_type,
                "status": case.status,
                "window_start": case.window_start.isoformat() if case.window_start else None,
                "window_end": case.window_end.isoformat() if case.window_end else None,
                "quarter": f["quarter"],
                "estimate_qty": round(f["estimate_qty"], 4),
                "bus": sorted(f["bus"]),
                "rank_axes": {
                    "same_customer": bool(same_customer),
                    "bu_overlap_ratio": round(bu_score, 4),
                    "same_promotion_type": bool(same_promo),
                    "quarter_proximity": round(q_prox, 4),
                    "volume_similarity": round(vol, 4),
                },
                "score": round(composite, 4),
            }
        )

    ranked.sort(key=lambda r: (-r["score"], r["case_code"] or ""))
    lim = max(1, min(int(limit), 200))
    seed_code, seed_name = cust_meta.get(int(seed.customer_id), (None, None))
    return {
        "case_id": int(seed.id),
        "case_code": seed.case_code,
        "seed": {
            "customer_id": int(seed.customer_id) if seed.customer_id else None,
            "customer_code": seed_code,
            "customer_name": seed_name,
            "promotion_type": seed.promotion_type,
            "quarter": seed_f["quarter"],
            "estimate_qty": round(seed_f["estimate_qty"], 4),
            "bus": sorted(seed_f["bus"]),
        },
        "rank_order": ["customer", "bu", "promotion_type", "quarter_proximity", "volume"],
        "total_candidates": len(ranked),
        "items": ranked[:lim],
    }
