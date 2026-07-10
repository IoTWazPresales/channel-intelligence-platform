#!/usr/bin/env python3
"""READ-ONLY diagnosis: 1H split quantities, Makro planned inflation, reconciliation grain."""
from __future__ import annotations

import json
import sys

from sqlalchemy import func, select, text

from app.db.session_sync import SessionLocal
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.dimensions import DimCustomer
from app.services.commercial_planner.lineup_period_canonical import active_lineup_case_filters


def main() -> int:
    with SessionLocal() as db:
        dbname = db.scalar(text("SELECT current_database()"))
        if dbname != "cip":
            print(f"STOP: current_database()={dbname!r}", file=sys.stderr)
            return 2

        report: dict = {"database": dbname}

        # (a) 1H NB 2026 Q1/Q2 split quantity semantics
        nb_cases = list(
            db.scalars(
                select(CommercialLineupCase)
                .where(
                    CommercialLineupCase.file_name.ilike("%2026%1H%NB%")
                    | CommercialLineupCase.file_name.ilike("%2026 1H NB%")
                    | (
                        (CommercialLineupCase.product_line.ilike("NB"))
                        & (CommercialLineupCase.period_label.in_(("26Q1", "26Q2")))
                        & (CommercialLineupCase.file_name.ilike("%2026%"))
                    )
                )
                .order_by(CommercialLineupCase.id)
            ).all()
        )
        if not nb_cases:
            nb_cases = list(
                db.scalars(
                    select(CommercialLineupCase)
                    .where(
                        CommercialLineupCase.business_unit.ilike("NB"),
                        CommercialLineupCase.inferred_period_start.isnot(None),
                        func.extract("year", CommercialLineupCase.inferred_period_start) == 2026,
                    )
                    .order_by(CommercialLineupCase.inferred_period_start, CommercialLineupCase.id)
                    .limit(20)
                ).all()
            )

        case_ids = [int(c.id) for c in nb_cases]
        lines_by_case: dict[int, list] = {}
        if case_ids:
            for ln in db.scalars(
                select(CommercialLineupLine).where(CommercialLineupLine.case_id.in_(case_ids))
            ).all():
                lines_by_case.setdefault(int(ln.case_id), []).append(ln)

        q1_case = next((c for c in nb_cases if (c.period_label or "").startswith("26Q1")), None)
        q2_case = next((c for c in nb_cases if (c.period_label or "").startswith("26Q2")), None)
        sample_lines = []
        if q1_case and q2_case:
            q1_by_prod = {
                int(l.product_id): l
                for l in lines_by_case.get(int(q1_case.id), [])
                if l.product_id is not None
            }
            q2_by_prod = {
                int(l.product_id): l
                for l in lines_by_case.get(int(q2_case.id), [])
                if l.product_id is not None
            }
            common = sorted(set(q1_by_prod) & set(q2_by_prod))[:3]
            for pid in common:
                l1, l2 = q1_by_prod[pid], q2_by_prod[pid]
                raw = (l1.raw_row_payload or {}) if isinstance(l1.raw_row_payload, dict) else {}
                month_cols = [k for k in raw.keys() if any(m in str(k).lower() for m in ("apr", "may", "jun", "jan", "feb", "mar"))]
                sample_lines.append(
                    {
                        "product_id": pid,
                        "sku_raw": l1.sku_raw or l2.sku_raw,
                        "q1_case_id": int(q1_case.id),
                        "q1_qty": float(l1.quantity_units or 0),
                        "q2_case_id": int(q2_case.id),
                        "q2_qty": float(l2.quantity_units or 0),
                        "identical_qty": abs(float(l1.quantity_units or 0) - float(l2.quantity_units or 0)) < 1e-6,
                        "month_phasing_columns_in_raw": month_cols[:12],
                    }
                )

        has_month_phasing = any(s.get("month_phasing_columns_in_raw") for s in sample_lines)
        report["a_1h_nb_split"] = {
            "q1_case": {"id": int(q1_case.id), "file_name": q1_case.file_name, "period": q1_case.period_label}
            if q1_case
            else None,
            "q2_case": {"id": int(q2_case.id), "file_name": q2_case.file_name, "period": q2_case.period_label}
            if q2_case
            else None,
            "sample_lines": sample_lines,
            "interpretation": (
                "Q1/Q2 cases carry identical full line quantities (duplication)"
                if sample_lines and all(s["identical_qty"] for s in sample_lines)
                else "mixed or insufficient paired lines"
            ),
            "source_has_month_phasing_columns": has_month_phasing,
        }

        # (b) Makro 2026 Q1 planned inflation + duplicate active slots
        makro = db.scalar(
            select(DimCustomer.id).where(func.lower(DimCustomer.name).like("%makro%")).limit(1)
        )
        makro_cases = []
        if makro:
            makro_cases = list(
                db.scalars(
                    select(CommercialLineupCase)
                    .where(
                        *active_lineup_case_filters(),
                        CommercialLineupCase.inferred_period_start.isnot(None),
                        func.extract("year", CommercialLineupCase.inferred_period_start) == 2026,
                        func.extract("quarter", CommercialLineupCase.inferred_period_start) == 1,
                        CommercialLineupCase.id.in_(
                            select(CommercialLineupLine.case_id).where(
                                CommercialLineupLine.customer_id == int(makro)
                            )
                        ),
                    )
                    .order_by(CommercialLineupCase.id)
                ).all()
            )
        makro_planned = []
        for c in makro_cases:
            total = db.scalar(
                select(func.coalesce(func.sum(CommercialLineupLine.quantity_units), 0)).where(
                    CommercialLineupLine.case_id == int(c.id),
                    CommercialLineupLine.customer_id == int(makro) if makro else True,
                )
            )
            makro_planned.append(
                {
                    "case_id": int(c.id),
                    "file_name": c.file_name,
                    "period_label": c.period_label,
                    "product_line": c.product_line,
                    "planned_units": float(total or 0),
                }
            )

        dup_slots = db.execute(
            text(
                """
                SELECT inferred_period_start, product_line, business_unit, count(*)::int AS active_cases
                FROM commercial_lineup_case
                WHERE superseded_by_case_id IS NULL
                  AND commercial_status NOT IN ('cancelled', 'superseded')
                  AND inferred_period_start IS NOT NULL
                GROUP BY inferred_period_start, product_line, business_unit
                HAVING count(*) > 1
                ORDER BY count(*) DESC
                """
            )
        ).all()

        report["b_makro_q1_planned"] = {
            "makro_customer_id": int(makro) if makro else None,
            "active_cases": makro_planned,
            "makro_planned_total": sum(x["planned_units"] for x in makro_planned),
            "duplicate_active_slot_groups": len(dup_slots),
            "duplicate_active_slot_samples": [
                {
                    "inferred_period_start": str(r[0]),
                    "product_line": r[1],
                    "business_unit": r[2],
                    "active_cases": int(r[3]),
                }
                for r in dup_slots[:15]
            ],
        }

        # (c) Reconciliation grain citations
        report["c_reconciliation_grain"] = {
            "period_chips": {
                "module": "apps/api/app/services/commercial_planner/po_management.py",
                "function": "backlog",
                "grain": "Sums reconcile_case().summary per linked case_id for each period×product_line group",
            },
            "per_case_reconciliation": {
                "module": "apps/api/app/services/commercial_planner/lineup_po_reconciliation.py",
                "function": "reconcile_case",
                "grain": "Per case_id × product_id: planned_units from all lineup lines on case; shipped from evidence for case POs",
            },
            "proposal_planned_column": {
                "module": "apps/api/app/services/commercial_planner/lineup_po_auto_link.py",
                "function": "build_po_auto_link_proposals",
                "grain": "planned_by_case_customer_product[(case_id, customer_id, product_id)] — matched products only for proposal customer",
            },
            "ui_label_recommendation": "Period plan for matched products (customer-scoped)",
        }

        print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
