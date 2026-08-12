"""Set-based staging upsert for payment-evidence import."""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.cpor_payment import ImportCporPaymentStagingLine

_UPSERT_COLS = (
    "import_job_id",
    "source_row_number",
    "sheet_name",
    "external_case_code",
    "credit_note_id",
    "case_status_raw",
    "payment_status_raw",
    "payment_status",
    "payment_date",
    "amount",
    "currency_code",
    "customer_token",
    "distributor_token",
    "description",
    "window_start",
    "window_end",
    "promotion_type_raw",
    "flags_json",
    "raw_source_row",
    "skip_apply",
    "create_shell_case",
    "resolved_customer_id",
    "resolved_distributor_id",
    "linked_case_id",
)


def upsert_payment_staging_lines(
    db: Session, *, import_job_id: int, rows: list[dict[str, Any]]
) -> int:
    if not rows:
        return 0
    # De-dupe by source_key within chunk (Postgres rejects same key twice in one INSERT)
    by_key: dict[str, dict[str, Any]] = {}
    for r in rows:
        by_key[str(r["source_key"])] = r
    payloads = []
    for key, r in by_key.items():
        payloads.append(
            {
                "source_key": key,
                "import_job_id": import_job_id,
                "source_row_number": int(r["source_row_number"]),
                "sheet_name": r["sheet_name"],
                "external_case_code": r["external_case_code"],
                "credit_note_id": r.get("credit_note_id"),
                "case_status_raw": r.get("case_status_raw"),
                "payment_status_raw": r.get("payment_status_raw"),
                "payment_status": r.get("payment_status"),
                "payment_date": r.get("payment_date"),
                "amount": r.get("amount"),
                "currency_code": r.get("currency_code"),
                "customer_token": r.get("customer_token"),
                "distributor_token": r.get("distributor_token"),
                "description": r.get("description"),
                "window_start": r.get("window_start"),
                "window_end": r.get("window_end"),
                "promotion_type_raw": r.get("promotion_type_raw"),
                "flags_json": r.get("flags_json") or {},
                "raw_source_row": r.get("raw_source_row") or {},
                "skip_apply": False,
                "create_shell_case": False,
                "resolved_customer_id": None,
                "resolved_distributor_id": None,
                "linked_case_id": None,
            }
        )

    chunk = 500
    total = 0
    for i in range(0, len(payloads), chunk):
        batch = payloads[i : i + chunk]
        stmt = insert(ImportCporPaymentStagingLine).values(batch)
        update = {c: getattr(stmt.excluded, c) for c in _UPSERT_COLS}
        db.execute(stmt.on_conflict_do_update(index_elements=["source_key"], set_=update))
        total += len(batch)
    db.flush()
    return total
