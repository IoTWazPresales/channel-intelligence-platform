"""Audit and optionally delete test-fixture dim_customer rows on cip.

Usage:
  python scripts/ops/cleanup_test_fixture_customers.py           # preview only
  python scripts/ops/cleanup_test_fixture_customers.py --confirm  # execute delete
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer
from app.services.customer_duplicate_groups import _CustomerRow, build_duplicate_groups
from app.services.customer_fk_discovery import discover_customer_fk_columns, extra_customer_ref_specs

# Heuristic: referencing rows that look like pytest/integration-test artifacts.
_FIXTURE_SOURCE_KEY_RE = re.compile(
    r"^(test-|test_full_merge|test-sellout-alias-merge|test-full-merge)",
    re.I,
)
_ACME_HEX_NAME_RE = re.compile(r"^Acme Retail [0-9a-f]{8}(\b|\s|\()", re.I)


def _is_fixture_customer(code: str, name: str) -> bool:
    if code.startswith("C-ALIAS-") or code.startswith("C-FULL-"):
        return True
    prefixes = (
        "Abort Merge",
        "Merge Test",
        "Term Dedup",
        "Bulk Preview",
        "Alias Customer ",
    )
    if any(name.startswith(p) for p in prefixes):
        return True
    if _ACME_HEX_NAME_RE.match(name):
        return True
    # Test pairs without hex in name but C-FULL code already caught; Acme without hex from tests:
    if name.startswith("Acme Retail ") and code.startswith("C-FULL-"):
        return True
    return False


def _load_fixture_ids(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(
        select(
            DimCustomer.id,
            DimCustomer.code,
            DimCustomer.name,
            DimCustomer.customer_status,
            DimCustomer.created_at,
            DimCustomer.merged_into_customer_id,
        ).order_by(DimCustomer.id)
    ).all()
    out = []
    for r in rows:
        code, name = str(r.code), str(r.name)
        if _is_fixture_customer(code, name):
            out.append(
                {
                    "id": int(r.id),
                    "code": code,
                    "name": name,
                    "customer_status": str(r.customer_status),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "merged_into_customer_id": int(r.merged_into_customer_id)
                    if r.merged_into_customer_id is not None
                    else None,
                    "import_job_id": None,  # dim_customer has no import_job_id column
                }
            )
    return out


def _alias_import_hints(db: Session, customer_ids: list[int]) -> dict[int, list[int]]:
    if not customer_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT customer_id, source_definition_id
            FROM customer_source_token_alias
            WHERE customer_id = ANY(:ids)
            """
        ),
        {"ids": customer_ids},
    ).all()
    hints: dict[int, set[int]] = defaultdict(set)
    for cid, sd in rows:
        if sd is not None:
            hints[int(cid)].add(int(sd))
    return {k: sorted(v) for k, v in hints.items()}


def _row_is_fixture_ref(table: str, row: dict[str, Any], fixture_id_set: set[int]) -> tuple[bool, str]:
    """Return (is_fixture, reason)."""
    if table == "fact_sales_sellout":
        sk = str(row.get("source_key") or "")
        if _FIXTURE_SOURCE_KEY_RE.match(sk):
            return True, f"source_key={sk!r}"
        return False, f"source_key={sk!r} (not test-prefixed)"

    if table == "commercial_customer_term":
        cid = int(row.get("customer_id") or 0)
        if cid in fixture_id_set:
            return True, "term on fixture customer"
        return False, "term on non-fixture customer"

    if table == "dim_customer" and "merged_into_customer_id" in row:
        mid = row.get("merged_into_customer_id")
        if mid is not None and int(mid) in fixture_id_set:
            return True, f"merged_into fixture {mid}"
        if mid is not None:
            return False, f"merged_into non-fixture {mid}"
        return True, "dim_customer row is fixture"

    if table == "customer_source_token_alias":
        tok = str(row.get("raw_token") or row.get("normalized_token") or "")
        if "acme dealer" in tok.lower() or tok.startswith("test"):
            return True, f"token={tok[:60]!r}"
        # alias-scope tests use random hex tokens — if customer is fixture, alias is fixture
        cid = int(row.get("customer_id") or 0)
        if cid in fixture_id_set:
            return True, "alias on fixture customer"
        return False, f"alias token={tok[:60]!r}"

    if table.startswith("import_") or table.endswith("_staging_line"):
        return True, "staging/import row on fixture customer"

    if table in {
        "commercial_lineup_line",
        "commercial_plan_line",
        "fact_inbound_shipment",
        "shipment_evidence_line",
        "historical_lineup_import_header",
    }:
        return False, f"production-path table {table}"

    # Default: if only fixture customers involved, treat as fixture
    cid = row.get("customer_id") or row.get("resolved_customer_id") or row.get("linked_customer_id")
    if cid is not None and int(cid) in fixture_id_set:
        return True, "references fixture customer only"
    return False, "unclassified — treat as real until inspected"


def _fetch_refs(db: Session, fixture_ids: list[int]) -> dict[str, list[dict[str, Any]]]:
    ids = fixture_ids
    fixture_set = set(ids)
    refs: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for table, column in discover_customer_fk_columns(db):
        if table == "dim_customer" and column == "merged_into_customer_id":
            sql = f"""
                SELECT id AS row_id, code, name, merged_into_customer_id, customer_status, created_at
                FROM dim_customer WHERE merged_into_customer_id = ANY(:ids)
            """
        else:
            sql = f"SELECT * FROM {table} WHERE {column} = ANY(:ids)"
        try:
            rows = db.execute(text(sql), {"ids": ids}).mappings().all()
        except Exception as exc:
            refs[f"{table}.{column}"].append({"error": str(exc)})
            continue
        for row in rows:
            d = dict(row)
            d["_ref_table"] = table
            d["_ref_column"] = column
            is_fix, reason = _row_is_fixture_ref(table, d, fixture_set)
            d["_fixture_ref"] = is_fix
            d["_fixture_reason"] = reason
            refs[f"{table}.{column}"].append(d)

    for table, column, where_extra in extra_customer_ref_specs():
        sql = f"SELECT * FROM {table} WHERE {column} = ANY(:ids) AND ({where_extra})"
        rows = db.execute(text(sql), {"ids": ids}).mappings().all()
        for row in rows:
            d = dict(row)
            d["_ref_table"] = table
            d["_ref_column"] = column
            is_fix, reason = _row_is_fixture_ref(table, d, fixture_set)
            d["_fixture_ref"] = is_fix
            d["_fixture_reason"] = reason
            refs[f"{table}.{column}"].append(d)

    return refs


def _delete_plan(refs: dict[str, list[dict[str, Any]]], fixture_ids: list[int]) -> dict[str, int]:
    plan: dict[str, int] = defaultdict(int)
    for key, rows in refs.items():
        table = key.split(".", 1)[0]
        for row in rows:
            if row.get("error"):
                continue
            plan[table] += 1
    plan["dim_customer"] = len(fixture_ids)
    return dict(sorted(plan.items()))


def _execute_delete(db: Session, refs: dict[str, list[dict[str, Any]]], fixture_ids: list[int]) -> None:
    ids = list(fixture_ids)
    # Break tombstone chains among fixtures.
    db.execute(
        text("UPDATE dim_customer SET merged_into_customer_id = NULL WHERE id = ANY(:ids)"),
        {"ids": ids},
    )
    db.execute(
        text("UPDATE dim_customer SET merged_into_customer_id = NULL WHERE merged_into_customer_id = ANY(:ids)"),
        {"ids": ids},
    )
    db.flush()

    # Delete only tables that actually hold referencing rows (avoids permission errors on empty tables).
    tables_with_refs: set[tuple[str, str]] = set()
    for key in refs:
        if not refs[key] or refs[key][0].get("error"):
            continue
        table, column = key.split(".", 1)
        if table == "dim_customer" and column == "merged_into_customer_id":
            continue  # handled via UPDATE NULL above
        tables_with_refs.add((table, column))

    for table, column in sorted(tables_with_refs):
        db.execute(text(f"DELETE FROM {table} WHERE {column} = ANY(:ids)"), {"ids": ids})

    db.execute(text("DELETE FROM dim_customer WHERE id = ANY(:ids)"), {"ids": ids})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true", help="Execute delete after clean preview")
    args = parser.parse_args()

    with SessionLocal() as db:
        db_name = db.execute(text("SELECT current_database()")).scalar()
        if db_name != "cip":
            print(json.dumps({"error": f"refusing: database={db_name!r}"}))
            return 1

        before_customers = int(db.execute(text("SELECT count(*) FROM dim_customer")).scalar() or 0)
        before_groups = len(
            build_duplicate_groups(
                [
                    _CustomerRow(int(r.id), str(r.code), str(r.name), str(r.customer_status or ""), r.created_at)
                    for r in db.execute(
                        select(
                            DimCustomer.id,
                            DimCustomer.code,
                            DimCustomer.name,
                            DimCustomer.customer_status,
                            DimCustomer.created_at,
                        )
                    ).all()
                ]
            )
        )

        fixtures = _load_fixture_ids(db)
        fixture_ids = [f["id"] for f in fixtures]
        alias_hints = _alias_import_hints(db, fixture_ids)
        for f in fixtures:
            f["source_definition_ids_from_aliases"] = alias_hints.get(f["id"], [])

        per_customer_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        refs = _fetch_refs(db, fixture_ids)

        entangled: list[dict[str, Any]] = []
        for key, rows in refs.items():
            for row in rows:
                if row.get("error"):
                    entangled.append({"table": key, "error": row["error"]})
                    continue
                cid = (
                    row.get("customer_id")
                    or row.get("resolved_customer_id")
                    or row.get("linked_customer_id")
                    or row.get("merged_into_customer_id")
                )
                if cid is not None:
                    per_customer_counts[int(cid)][key] += 1
                if not row.get("_fixture_ref", True):
                    entangled.append(
                        {
                            "table": key,
                            "row_id": row.get("id") or row.get("row_id"),
                            "reason": row.get("_fixture_reason"),
                            "sample": {k: row[k] for k in list(row.keys())[:8] if not k.startswith("_")},
                        }
                    )

        summary_counts: dict[str, int] = defaultdict(int)
        fixture_ref_counts: dict[str, int] = defaultdict(int)
        real_ref_counts: dict[str, int] = defaultdict(int)
        for key, rows in refs.items():
            for row in rows:
                if row.get("error"):
                    continue
                summary_counts[key] += 1
                if row.get("_fixture_ref"):
                    fixture_ref_counts[key] += 1
                else:
                    real_ref_counts[key] += 1

        plan = _delete_plan(refs, fixture_ids)
        report: dict[str, Any] = {
            "database": db_name,
            "fixture_customer_count": len(fixtures),
            "fixtures": fixtures,
            "per_customer_fk_counts": {str(k): dict(v) for k, v in sorted(per_customer_counts.items())},
            "total_refs_by_table": dict(summary_counts),
            "fixture_refs_by_table": dict(fixture_ref_counts),
            "real_refs_by_table": dict(real_ref_counts),
            "entangled_real_refs": entangled,
            "delete_plan_counts": plan,
            "before": {"dim_customer_count": before_customers, "name_similarity_groups": before_groups},
        }

        if entangled:
            report["status"] = "STOP — real data entangled with fixtures"
            print(json.dumps(report, indent=2, default=str))
            return 2

        report["status"] = "clean — all references are fixture-or-zero"
        print(json.dumps(report, indent=2, default=str))

        if not args.confirm:
            print("\nPreview only. Re-run with --confirm to execute delete.", file=sys.stderr)
            return 0

        try:
            _execute_delete(db, refs, fixture_ids)
            db.commit()
        except Exception as exc:
            db.rollback()
            print(json.dumps({"status": "DELETE_FAILED", "error": str(exc)}))
            return 3

        after_customers = int(db.execute(text("SELECT count(*) FROM dim_customer")).scalar() or 0)
        after_groups = len(
            build_duplicate_groups(
                [
                    _CustomerRow(int(r.id), str(r.code), str(r.name), str(r.customer_status or ""), r.created_at)
                    for r in db.execute(
                        select(
                            DimCustomer.id,
                            DimCustomer.code,
                            DimCustomer.name,
                            DimCustomer.customer_status,
                            DimCustomer.created_at,
                        )
                    ).all()
                ]
            )
        )
        print(
            json.dumps(
                {
                    "status": "DELETED",
                    "after": {
                        "dim_customer_count": after_customers,
                        "name_similarity_groups": after_groups,
                        "removed_customers": before_customers - after_customers,
                        "removed_groups": before_groups - after_groups,
                    },
                },
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
