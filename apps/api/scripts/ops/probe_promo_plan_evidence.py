"""Read-only NUMBER RULE probe for promotion-plan evidence on live cip.

Prints current_database() first. No writes.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session_sync import SessionLocal


QUERIES = [
    ("cpor_case by status", """
        SELECT status, count(*) FROM cpor_case GROUP BY status ORDER BY count(*) DESC
    """),
    ("cpor_case_line", "SELECT count(*) FROM cpor_case_line"),
    ("cpor_case distinct customers", "SELECT count(DISTINCT customer_id) FROM cpor_case"),
    ("ended cases with result qty", """
        SELECT count(DISTINCT c.id)
        FROM cpor_case c
        JOIN cpor_case_line l ON l.case_id = c.id
        WHERE c.status = 'ended' AND l.result_qty IS NOT NULL AND l.result_qty > 0
    """),
    ("claim evidence rows", "SELECT count(*) FROM cpor_claim_evidence_line"),
    ("ended cases with claim evidence", """
        SELECT count(DISTINCT c.id)
        FROM cpor_case c
        JOIN cpor_claim_evidence_line e ON e.case_id = c.id
        WHERE c.status = 'ended'
    """),
    ("fact_demand_forecast", """
        SELECT count(*), min(period_start), max(period_start), count(DISTINCT customer_id), count(DISTINCT product_id)
        FROM fact_demand_forecast
    """),
    ("commercial_customer_term", "SELECT count(*), count(target_cover_weeks) FROM commercial_customer_term"),
    ("commercial_sku_assumption", "SELECT count(*) FROM commercial_sku_assumption"),
    ("fact_lineup_plan_item", """
        SELECT count(*), count(DISTINCT customer_id), count(DISTINCT period_label)
        FROM fact_lineup_plan_item
    """),
    ("fact_lineup_plan_item periods", """
        SELECT period_label, count(*), count(DISTINCT customer_id)
        FROM fact_lineup_plan_item
        GROUP BY period_label
        ORDER BY count(*) DESC
        LIMIT 8
    """),
    ("commercial_lineup_case periods", """
        SELECT period_label, commercial_status, count(*)
        FROM commercial_lineup_case
        GROUP BY period_label, commercial_status
        ORDER BY count(*) DESC
        LIMIT 12
    """),
    ("commercial_lineup_line with product+customer", """
        SELECT count(*), count(DISTINCT customer_id), count(DISTINCT product_id)
        FROM commercial_lineup_line
        WHERE product_id IS NOT NULL AND customer_id IS NOT NULL
    """),
    ("customer_listing", "SELECT count(*), count(DISTINCT customer_id) FROM customer_listing"),
    ("listing_observation", "SELECT count(*) FROM listing_observation"),
    ("fact_competitor_price", "SELECT count(*) FROM fact_competitor_price"),
    ("weeks_of_cover_observation", "SELECT count(*) FROM weeks_of_cover_observation"),
    ("cpor_case sample windows", """
        SELECT id, case_code, customer_id, status, window_start, window_end, promotion_type
        FROM cpor_case
        ORDER BY id DESC
        LIMIT 8
    """),
    ("ttl_support_usd by status", """
        SELECT c.status, count(DISTINCT c.id), coalesce(sum(l.ttl_support_usd),0), coalesce(sum(l.ttl_support),0)
        FROM cpor_case c
        LEFT JOIN cpor_case_line l ON l.case_id = c.id
        GROUP BY c.status
        ORDER BY c.status
    """),
    ("customer 18 lineup products 2026Q2", """
        SELECT count(*), count(DISTINCT l.product_id),
               count(*) FILTER (WHERE coalesce(l.dap_evidence_local, l.msrp_local) > 0) AS with_srp
        FROM commercial_lineup_line l
        JOIN commercial_lineup_case c ON c.id = l.case_id
        WHERE l.customer_id = 18
          AND l.product_id IS NOT NULL
          AND c.superseded_by_case_id IS NULL
          AND c.commercial_status NOT IN ('cancelled', 'superseded')
          AND replace(upper(coalesce(c.period_label,'')), ' ', '') IN ('2026Q2','26Q2')
    """),
    ("customer 18 historical case products", """
        SELECT count(DISTINCT l.product_id), count(*)
        FROM cpor_case_line l
        JOIN cpor_case c ON c.id = l.case_id
        WHERE c.customer_id = 18 AND l.product_id IS NOT NULL
    """),
    ("listing customers", "SELECT customer_id, count(*) FROM customer_listing GROUP BY customer_id ORDER BY count(*) DESC"),
    ("cpor origin", "SELECT origin, count(*) FROM cpor_case GROUP BY origin"),

]


def main() -> None:
    with SessionLocal() as session:
        db = session.execute(text("SELECT current_database()")).scalar()
        print(f"FACT current_database()={db}")
        if db != "cip":
            raise SystemExit(f"refusing: expected cip, got {db}")
        for label, sql in QUERIES:
            print(f"\n=== {label} ===")
            rows = session.execute(text(sql)).all()
            for row in rows:
                print(tuple(row))
        from app.services.cpor.support_bias import build_support_bias

        bias = build_support_bias(session, limit_cases=500)
        t = bias.get("totals") or {}
        print("\n=== support_bias totals ===")
        print({k: t.get(k) for k in ("planned_usd", "actual_usd", "case_count", "line_count", "included_line_count")})
        if t.get("planned_usd"):
            print("ratio_pct", round((float(t.get("actual_usd") or 0) / float(t["planned_usd"])) * 100))

        from app.services.cpor.promo_plan_builder import build_promo_plan_draft

        draft = build_promo_plan_draft(session, customer_id=18, period_label="2026Q2")
        print("\n=== compose customer_id=18 period=2026Q2 ===")
        print("product_set_source", draft.get("product_set_source"))
        print("line_count", len(draft.get("lines") or []))
        print("window", draft.get("window_start"), draft.get("window_end"))
        print("same_customer_only", (draft.get("comparables") or {}).get("same_customer_only"))
        print("comparable_count", (draft.get("comparables") or {}).get("count"))
        cust_ids = {t.get("customer_id") for t in (draft.get("comparables") or {}).get("top") or []}
        print("comparable_customer_ids", cust_ids)
        print("uncovered", draft.get("uncovered"))


if __name__ == "__main__":
    main()
