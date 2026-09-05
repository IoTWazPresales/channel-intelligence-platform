"""Apply payment staging → cpor_payment_evidence (+ optional shell cases).

Case status from file is evidence-only — never overwrites cpor_case.status.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseEvent
from app.models.cpor_payment import CporPaymentEvidence, ImportCporPaymentStagingLine


def _default_promo(raw: str | None) -> str:
    s = (raw or "").strip()
    if not s:
        return "Sell out PP"
    # ASUS often prefixes "PR02 - Stock PP (Indirect)"
    if " - " in s:
        s = s.split(" - ", 1)[-1].strip()
    return s[:128] or "Sell out PP"


def _ensure_shell_case(
    db: Session,
    *,
    line: ImportCporPaymentStagingLine,
    tenant_id: str,
    actor: str | None,
) -> int | None:
    if line.linked_case_id is not None:
        return line.linked_case_id
    if not line.create_shell_case:
        return None
    if line.resolved_customer_id is None:
        return None
    existing = db.scalar(select(CporCase).where(CporCase.case_code == line.external_case_code))
    if existing is not None:
        line.linked_case_id = existing.id
        return existing.id

    ws = line.window_start or line.payment_date or date.today()
    we = line.window_end or ws
    case = CporCase(
        case_code=line.external_case_code,
        case_name=(line.description or line.external_case_code)[:256],
        tenant_id=tenant_id,
        customer_id=line.resolved_customer_id,
        promotion_type=_default_promo(line.promotion_type_raw),
        window_start=ws,
        window_end=we,
        status="draft",
        currency_code=(line.currency_code or "ZAR")[:8],
        channel="reseller",
        origin="payment_evidence",
        notes=(
            "Shell case created from payment/CN evidence import. "
            f"File case_status_raw={line.case_status_raw!r} stored on evidence only."
        ),
        created_by=actor or "payment_evidence",
        workflow_status="imported",
    )
    db.add(case)
    db.flush()
    db.add(
        CporCaseEvent(
            case_id=case.id,
            event_type="shell_from_payment_evidence",
            actor=actor or "payment_evidence",
            payload_json={
                "external_case_code": line.external_case_code,
                "credit_note_id": line.credit_note_id,
                "case_status_raw": line.case_status_raw,
            },
        )
    )
    line.linked_case_id = case.id
    return case.id


def run_cpor_payment_apply_sync(
    db: Session,
    *,
    import_job_id: int,
    tenant_id: str = "default",
    actor: str | None = None,
) -> dict[str, Any]:
    lines = list(
        db.scalars(
            select(ImportCporPaymentStagingLine).where(
                ImportCporPaymentStagingLine.import_job_id == import_job_id,
                ImportCporPaymentStagingLine.skip_apply.is_(False),
            )
        ).all()
    )
    shells = 0
    for ln in lines:
        before = ln.linked_case_id
        cid = _ensure_shell_case(db, line=ln, tenant_id=tenant_id, actor=actor)
        if cid is not None and before is None:
            shells += 1

    # De-dupe source_key within apply batch
    by_key: dict[str, ImportCporPaymentStagingLine] = {}
    for ln in lines:
        by_key[ln.source_key] = ln

    payloads = []
    for ln in by_key.values():
        payloads.append(
            {
                "tenant_id": tenant_id,
                "source_key": ln.source_key,
                "import_job_id": import_job_id,
                "external_case_code": ln.external_case_code,
                "credit_note_id": ln.credit_note_id,
                "case_status_raw": ln.case_status_raw,
                "payment_status_raw": ln.payment_status_raw,
                "payment_status": ln.payment_status,
                "payment_date": ln.payment_date,
                "amount": ln.amount,
                "currency_code": (ln.currency_code or "ZAR")[:8],
                "customer_token": ln.customer_token,
                "distributor_token": ln.distributor_token,
                "description": ln.description,
                "customer_id": ln.resolved_customer_id,
                "distributor_id": ln.resolved_distributor_id,
                "case_id": ln.linked_case_id,
                "evidence_json": {
                    "window_start": ln.window_start.isoformat() if ln.window_start else None,
                    "window_end": ln.window_end.isoformat() if ln.window_end else None,
                    "promotion_type_raw": ln.promotion_type_raw,
                    "flags": ln.flags_json or {},
                    "owed_amount_file": (ln.flags_json or {}).get("owed_amount_file"),
                    "latest_comment": (ln.flags_json or {}).get("latest_comment"),
                    "deduction_no": (ln.flags_json or {}).get("deduction_no"),
                    "cn_status_raw": (ln.flags_json or {}).get("cn_status_raw"),
                    "cn_closed_date": (ln.flags_json or {}).get("cn_closed_date"),
                },
                "raw_source_row": ln.raw_source_row or {},
                "applied_at": datetime.now(timezone.utc),
            }
        )

    upserted = 0
    chunk = 500
    update_cols = (
        "import_job_id",
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
        "customer_id",
        "distributor_id",
        "case_id",
        "evidence_json",
        "raw_source_row",
        "applied_at",
    )
    for i in range(0, len(payloads), chunk):
        batch = payloads[i : i + chunk]
        stmt = insert(CporPaymentEvidence).values(batch)
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=["source_key"],
                set_={c: getattr(stmt.excluded, c) for c in update_cols},
            )
        )
        upserted += len(batch)

    db.flush()
    return {
        "upserted": upserted,
        "shell_cases_created": shells,
        "import_job_id": import_job_id,
    }
