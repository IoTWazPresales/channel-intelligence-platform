"""Async apply: staging → cpor_case / cpor_case_line upsert (H2).

Locks:
- origin='historical_import'; never overwrite native cases (blocked earlier)
- frozen Result totals from sheet (no waterfall rewrite)
- no cpor_claim_evidence_line writes
- FLAG→BLOCK per case: unresolved / collision / duplicate grain stay staged
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.models.cpor import CporCase, CporCaseEvent, CporCaseLine
from app.models.cpor_historical import ImportCporHistoricalStagingLine
from app.models.ingestion import ImportJob
from app.services.cpor.historical_import.resolve import case_apply_blockers
from app.services.imports.import_job_background_metadata import persist_clear_background_task_metadata
from app.utils.json_safe import to_jsonable

ProgressFn = Callable[[str, str, int, int], None]
STAGE_LOADED = "loaded"
STAGE_FAILED = "failed"
TEMPLATE_SLUG = "cpor_historical_cases"


def _num(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(Decimal(str(val)))
    except Exception:
        return default


def run_cpor_historical_apply_sync(
    job_id: int,
    *,
    on_progress: ProgressFn | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    def _emit(phase: str, label: str, current: int, total: int) -> None:
        if on_progress is not None:
            try:
                on_progress(phase, label, current, total)
            except Exception:
                pass

    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        if job is None or (job.template_slug or "") != TEMPLATE_SLUG:
            return {"id": job_id, "outcome": "not_found"}

        rows = list(
            db.scalars(
                select(ImportCporHistoricalStagingLine).where(
                    ImportCporHistoricalStagingLine.import_job_id == job_id,
                    ImportCporHistoricalStagingLine.skip_apply.is_(False),
                )
            ).all()
        )
        by_case: dict[str, list[ImportCporHistoricalStagingLine]] = defaultdict(list)
        for row in rows:
            code = (row.case_code or "").strip()
            if code:
                by_case[code].append(row)

        case_codes = sorted(by_case.keys())
        total = len(case_codes)
        applied = 0
        blocked = 0
        blocked_detail: dict[str, list[str]] = {}
        file_hash = ((job.staged_metadata or {}).get("cpor_historical") or {}).get("file_sha256")

        _emit("applying_cases", "Applying historical CPOR cases", 0, total)

        for idx, case_code in enumerate(case_codes):
            case_rows = by_case[case_code]
            blockers: set[str] = set()
            for r in case_rows:
                blockers.update(case_apply_blockers(r))
            if blockers:
                blocked += 1
                blocked_detail[case_code] = sorted(blockers)
                _emit("applying_cases", "Applying historical CPOR cases", idx + 1, total)
                continue

            try:
                with db.begin_nested():
                    _apply_one_case(
                        db,
                        case_code=case_code,
                        case_rows=case_rows,
                        job_id=job_id,
                        file_hash=file_hash,
                        actor=actor,
                    )
                applied += 1
            except Exception as exc:
                blocked += 1
                blocked_detail[case_code] = [f"apply_error:{type(exc).__name__}:{exc}"][:1]
            _emit("applying_cases", "Applying historical CPOR cases", idx + 1, total)

        job = db.get(ImportJob, job_id)
        assert job is not None
        meta = dict(job.staged_metadata or {})
        hist = dict(meta.get("cpor_historical") or {})
        hist["apply"] = {
            "applied_cases": applied,
            "blocked_cases": blocked,
            "blocked_detail": blocked_detail,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        meta["cpor_historical"] = hist
        job.staged_metadata = to_jsonable(meta)
        job.stage = STAGE_LOADED if applied > 0 else job.stage
        job.status = "completed" if blocked == 0 else "completed_with_errors"
        if applied == 0 and blocked > 0:
            job.status = "completed_with_errors"
            job.error_summary = f"{blocked} case(s) blocked; 0 applied"[0:2000]
        job.completed_at = datetime.now(timezone.utc)
        persist_clear_background_task_metadata(db, job)
        db.commit()
        _emit("loaded", "Historical CPOR apply complete", total, total)
        return {
            "id": job_id,
            "outcome": "applied",
            "applied_cases": applied,
            "blocked_cases": blocked,
            "blocked_detail": blocked_detail,
        }


def _apply_one_case(
    db: Session,
    *,
    case_code: str,
    case_rows: list[ImportCporHistoricalStagingLine],
    job_id: int,
    file_hash: str | None,
    actor: str | None,
) -> None:
    head = case_rows[0]
    customer_id = int(head.resolved_customer_id)  # type: ignore[arg-type]
    # Prefer a shared customer if all lines agree
    cust_ids = {int(r.resolved_customer_id) for r in case_rows if r.resolved_customer_id}
    if len(cust_ids) == 1:
        customer_id = next(iter(cust_ids))

    window_start = head.window_start
    window_end = head.window_end
    for r in case_rows:
        if r.window_start and (window_start is None or r.window_start < window_start):
            window_start = r.window_start
        if r.window_end and (window_end is None or r.window_end > window_end):
            window_end = r.window_end
    assert window_start is not None and window_end is not None

    status = (head.lifecycle_status or "settled").strip() or "settled"
    promo = (head.promotion_type or head.promotion_type_raw or "historical").strip() or "historical"
    channel = (head.channel or "reseller").strip() or "reseller"
    roe = head.roe_snapshot

    existing = db.scalar(select(CporCase).where(CporCase.case_code == case_code))
    if existing is not None and (existing.origin or "native") != "historical_import":
        raise RuntimeError("native_collision")

    if existing is None:
        case = CporCase(
            case_code=case_code,
            case_name=head.case_name,
            customer_id=customer_id,
            promotion_type=promo[:128],
            window_start=window_start,
            window_end=window_end,
            status=status[:32],
            roe_snapshot=roe,
            currency_code="ZAR",
            channel=channel[:32],
            origin="historical_import",
            notes=f"Imported via historical job {job_id}",
            created_by=actor or "historical_import",
            workflow_status=status[:32],
        )
        db.add(case)
        db.flush()
    else:
        existing.case_name = head.case_name
        existing.customer_id = customer_id
        existing.promotion_type = promo[:128]
        existing.window_start = window_start
        existing.window_end = window_end
        existing.status = status[:32]
        existing.roe_snapshot = roe
        existing.channel = channel[:32]
        existing.workflow_status = status[:32]
        existing.notes = f"Imported via historical job {job_id}"
        case = existing
        db.flush()

    case_id = int(case.id)

    # Dedup lines by DB grain within this apply batch
    grain_rows: dict[tuple[Any, ...], ImportCporHistoricalStagingLine] = {}
    for r in case_rows:
        grain = (
            case_id,
            int(r.resolved_product_id),  # type: ignore[arg-type]
            int(r.resolved_distributor_id) if r.resolved_distributor_id is not None else None,
            (r.pod_quarter or None),
        )
        grain_rows[grain] = r

    for grain, r in grain_rows.items():
        _upsert_line(db, case_id=case_id, row=r)

    db.add(
        CporCaseEvent(
            case_id=case_id,
            event_type="historical_import",
            actor=actor or "historical_import",
            payload_json=to_jsonable(
                {
                    "import_job_id": job_id,
                    "file_sha256": file_hash,
                    "line_count": len(grain_rows),
                    "channel": channel,
                }
            ),
        )
    )
    db.flush()


def _upsert_line(db: Session, *, case_id: int, row: ImportCporHistoricalStagingLine) -> None:
    product_id = int(row.resolved_product_id)  # type: ignore[arg-type]
    distributor_id = int(row.resolved_distributor_id) if row.resolved_distributor_id is not None else None
    pod = row.pod_quarter
    values = {
        "case_id": case_id,
        "product_id": product_id,
        "distributor_id": distributor_id,
        "pod_quarter": pod,
        "srp": _num(row.srp, 0.0),
        "vat_rate": _num(row.vat_rate, 0.15),
        "dealer_margin_pct": _num(row.dealer_margin_pct, 0.0),
        "margin_source": "historical_import",
        "cost_basis": row.cost_basis,
        "cost_source": "historical_import" if row.cost_basis is not None else None,
        "estimate_qty": _num(row.estimate_qty, 0.0),
        "soh_snapshot": row.soh_snapshot,
        "dealer_price": row.dealer_price,
        "support_unit": row.support_unit,
        "ttl_support": row.ttl_support,
        "support_usd": row.support_usd,
        "result_qty": row.result_qty,
        "ttl_result": row.ttl_result,
        "ttl_support_usd": row.ttl_support_usd,
        "ttl_result_usd": row.ttl_result_usd,
        "remark": row.remark,
        "source_snapshot_json": to_jsonable(
            {
                **(row.source_snapshot_json or {}),
                "flags": (row.flags_json or {}).get("flags") or [],
                "staging_source_key": row.source_key,
            }
        ),
    }
    stmt = pg_insert(CporCaseLine).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_cpor_case_line_grain",
        set_={
            "srp": stmt.excluded.srp,
            "vat_rate": stmt.excluded.vat_rate,
            "dealer_margin_pct": stmt.excluded.dealer_margin_pct,
            "margin_source": stmt.excluded.margin_source,
            "cost_basis": stmt.excluded.cost_basis,
            "cost_source": stmt.excluded.cost_source,
            "estimate_qty": stmt.excluded.estimate_qty,
            "soh_snapshot": stmt.excluded.soh_snapshot,
            "dealer_price": stmt.excluded.dealer_price,
            "support_unit": stmt.excluded.support_unit,
            "ttl_support": stmt.excluded.ttl_support,
            "support_usd": stmt.excluded.support_usd,
            "result_qty": stmt.excluded.result_qty,
            "ttl_result": stmt.excluded.ttl_result,
            "ttl_support_usd": stmt.excluded.ttl_support_usd,
            "ttl_result_usd": stmt.excluded.ttl_result_usd,
            "remark": stmt.excluded.remark,
            "source_snapshot_json": stmt.excluded.source_snapshot_json,
        },
    )
    db.execute(stmt)
