"""CST D1 steward surfaces — key accounts, report config, slots, article aliases.

No schema. FLAG ≠ BLOCK. No auto-create of master records (config upsert is steward-owned).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import Role, require_roles
from app.db.session_sync import SessionLocal
from app.models.customer_article_alias import CustomerArticleAlias
from app.models.customer_cst_report_slot import CustomerCstReportSlot
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.services.imports.cst_article_alias_import import (
    confirm_scm_unique_proposed,
    import_article_alias_rows,
    parse_article_alias_workbook,
)
from app.services.imports.cst_d1 import (
    advance_cst_report_slots,
    confirm_customer_article_alias,
    list_cst_report_worklist_slots,
    reject_customer_article_alias,
)
from app.services.imports.cst_p4_customer_bootstrap import bootstrap_p4_customer_configs
from app.utils.json_safe import to_jsonable

router = APIRouter()


def _actor(x_user_id: str | None) -> str | None:
    return x_user_id


def _config_json(
    cfg: CustomerReportConfig | None,
    *,
    customer: DimCustomer,
) -> dict[str, Any]:
    return {
        "id": cfg.id if cfg else None,
        "customer_id": customer.id,
        "customer_code": customer.code,
        "customer_name": customer.name,
        "is_key_account": bool(customer.is_key_account),
        "reports_expected": bool(cfg.reports_expected) if cfg else False,
        "expected_cadence": cfg.expected_cadence if cfg else "weekly",
        "report_structure_type": cfg.report_structure_type if cfg else None,
        "last_report_received": cfg.last_report_received.isoformat()
        if cfg and cfg.last_report_received
        else None,
        "overdue_threshold_days": int(cfg.overdue_threshold_days) if cfg else 10,
        "notes": cfg.notes if cfg else None,
        "feed_profile_json": cfg.feed_profile_json if cfg else None,
    }


def article_alias_q_match(q: str):
    """ILIKE over retailer article + Product Master identity + customer name/code.

    Sales model is not stored on customer_article_alias — join DimProduct.
    """
    needle = f"%{q.strip()}%"
    return or_(
        CustomerArticleAlias.article_no_normalized.ilike(needle),
        DimProduct.sku.ilike(needle),
        DimProduct.sales_model_name.ilike(needle),
        DimProduct.name.ilike(needle),
        DimCustomer.name.ilike(needle),
        DimCustomer.code.ilike(needle),
    )


def _alias_json(row: CustomerArticleAlias, customer: DimCustomer | None, product: DimProduct | None) -> dict:
    evidence = row.evidence_json if isinstance(row.evidence_json, dict) else {}
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "customer_code": customer.code if customer else None,
        "customer_name": customer.name if customer else None,
        "article_no_normalized": row.article_no_normalized,
        "product_id": row.product_id,
        "product_sku": product.sku if product else None,
        "product_name": product.name if product else None,
        "sales_model_name": product.sales_model_name if product else None,
        "status": row.status,
        "sku_twin_flag": bool(evidence.get("sku_twin_flag")),
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        "evidence_json": row.evidence_json,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _slot_json(slot: CustomerCstReportSlot, customer: DimCustomer | None) -> dict:
    return {
        "id": slot.id,
        "customer_id": slot.customer_id,
        "customer_code": customer.code if customer else None,
        "customer_name": customer.name if customer else None,
        "week_start_date": slot.week_start_date.isoformat() if slot.week_start_date else None,
        "status": slot.status,
        "due_at": slot.due_at.isoformat() if slot.due_at else None,
        "late_at": slot.late_at.isoformat() if slot.late_at else None,
        "received_at": slot.received_at.isoformat() if slot.received_at else None,
        "import_job_id": slot.import_job_id,
        "cadence_snapshot": slot.cadence_snapshot,
    }


_STRUCTURE_TYPES = {"flat", "pivoted", "multi_sheet", "mtd_delta", "wide_extract"}


class KeyAccountPatch(BaseModel):
    is_key_account: bool | None = None
    reports_expected: bool | None = None
    expected_cadence: str | None = Field(default=None, max_length=16)
    report_structure_type: str | None = Field(default=None, max_length=16)
    overdue_threshold_days: int | None = Field(default=None, ge=0, le=365)
    notes: str | None = Field(default=None, max_length=512)
    feed_profile_json: dict[str, Any] | None = None
    feed_profile_raw: str | None = None  # optional JSON text from UI editor

    @field_validator("expected_cadence")
    @classmethod
    def cadence_ok(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"weekly", "monthly", "adhoc"}
        if v.strip().lower() not in allowed:
            raise ValueError(f"expected_cadence must be one of {sorted(allowed)}")
        return v.strip().lower()

    @field_validator("report_structure_type")
    @classmethod
    def structure_ok(cls, v: str | None) -> str | None:
        if v is None:
            return v
        cleaned = v.strip().lower()
        if cleaned == "":
            return None
        if cleaned not in _STRUCTURE_TYPES:
            raise ValueError(f"report_structure_type must be one of {sorted(_STRUCTURE_TYPES)}")
        return cleaned


class AliasRejectBody(BaseModel):
    reason: str | None = None


class AliasPatchBody(BaseModel):
    product_id: int | None = Field(default=None, ge=1)
    status: str | None = Field(default=None, max_length=32)
    valid_from: date | None = None
    valid_to: date | None = None
    clear_valid_from: bool = False
    clear_valid_to: bool = False

    @field_validator("status")
    @classmethod
    def status_ok(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = {"proposed", "confirmed", "rejected", "active"}
        if v.strip().lower() not in allowed:
            raise ValueError(f"status must be one of {sorted(allowed)}")
        return v.strip().lower()


class AliasImportConfirmBody(BaseModel):
    alias_ids: list[int] = Field(default_factory=list)


class SlotAdvanceBody(BaseModel):
    as_of: date | None = None


@router.get("/key-accounts")
def list_key_account_steward(
    q: str | None = Query(default=None),
    key_only: bool = Query(default=False),
):
    """Steward grid: customers with key-account flag + report config (upserted on edit)."""
    with SessionLocal() as session:
        stmt = (
            select(DimCustomer, CustomerReportConfig)
            .outerjoin(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
            .order_by(DimCustomer.name.asc(), DimCustomer.id.asc())
        )
        if key_only:
            stmt = stmt.where(DimCustomer.is_key_account.is_(True))
        if q and q.strip():
            needle = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(DimCustomer.code.ilike(needle), DimCustomer.name.ilike(needle))
            )
        rows = session.execute(stmt.limit(500)).all()
        return [_config_json(cfg, customer=cust) for cust, cfg in rows]


@router.get("/key-accounts/{customer_id}")
def get_key_account_steward(customer_id: int):
    with SessionLocal() as session:
        cust = session.get(DimCustomer, customer_id)
        if not cust:
            raise HTTPException(status_code=404, detail="Customer not found")
        cfg = session.scalar(
            select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id)
        )
        return _config_json(cfg, customer=cust)


@router.patch("/key-accounts/{customer_id}")
def patch_key_account_steward(
    customer_id: int,
    body: KeyAccountPatch,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Toggle is_key_account and upsert customer_report_config (steward-owned)."""
    _ = _actor(x_user_id)
    data = body.model_dump(exclude_unset=True)
    if "feed_profile_raw" in data and data["feed_profile_raw"] is not None:
        raw = str(data.pop("feed_profile_raw") or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"feed_profile_json invalid: {exc}") from exc
            if not isinstance(parsed, dict):
                raise HTTPException(status_code=400, detail="feed_profile_json must be a JSON object")
            data["feed_profile_json"] = parsed
        else:
            data["feed_profile_json"] = None
    data.pop("feed_profile_raw", None)

    with SessionLocal() as session:
        cust = session.get(DimCustomer, customer_id)
        if not cust:
            raise HTTPException(status_code=404, detail="Customer not found")
        if "is_key_account" in data and data["is_key_account"] is not None:
            cust.is_key_account = bool(data["is_key_account"])
            session.add(cust)

        cfg = session.scalar(
            select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id)
        )
        needs_config = any(
            k in data
            for k in (
                "reports_expected",
                "expected_cadence",
                "report_structure_type",
                "overdue_threshold_days",
                "notes",
                "feed_profile_json",
            )
        )
        if cfg is None and needs_config:
            cfg = CustomerReportConfig(customer_id=customer_id)
            session.add(cfg)
            session.flush()
        if cfg is not None:
            if "reports_expected" in data and data["reports_expected"] is not None:
                cfg.reports_expected = bool(data["reports_expected"])
            if "expected_cadence" in data and data["expected_cadence"] is not None:
                cfg.expected_cadence = str(data["expected_cadence"])
            if "report_structure_type" in data:
                cfg.report_structure_type = data["report_structure_type"]
            if "overdue_threshold_days" in data and data["overdue_threshold_days"] is not None:
                cfg.overdue_threshold_days = int(data["overdue_threshold_days"])
            if "notes" in data:
                cfg.notes = data["notes"]
            if "feed_profile_json" in data:
                cfg.feed_profile_json = to_jsonable(data["feed_profile_json"]) if data["feed_profile_json"] else None
            session.add(cfg)

        session.commit()
        session.refresh(cust)
        if cfg is not None:
            session.refresh(cfg)
        else:
            cfg = session.scalar(
                select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id)
            )
        return _config_json(cfg, customer=cust)


@router.get("/report-slots/worklist")
def report_slot_worklist(
    status: str | None = Query(default=None, description="due|late|missing or comma-list"),
):
    with SessionLocal() as session:
        if status and status.strip():
            statuses = tuple(s.strip() for s in status.split(",") if s.strip())
        else:
            statuses = ("due", "late", "missing")
        for s in statuses:
            if s not in ("due", "late", "missing", "received"):
                raise HTTPException(status_code=400, detail=f"Unknown slot status={s}")
        slots = list_cst_report_worklist_slots(session, statuses=statuses)
        cust_ids = {int(s.customer_id) for s in slots}
        cmap: dict[int, DimCustomer] = {}
        if cust_ids:
            for c in session.scalars(select(DimCustomer).where(DimCustomer.id.in_(cust_ids))).all():
                cmap[int(c.id)] = c
        grouped: dict[str, list[dict]] = {"due": [], "late": [], "missing": [], "received": []}
        for slot in slots:
            item = _slot_json(slot, cmap.get(int(slot.customer_id)))
            grouped.setdefault(slot.status, []).append(item)
        return {
            "as_of": date.today().isoformat(),
            "counts": {k: len(v) for k, v in grouped.items()},
            "groups": grouped,
            "items": [item for items in grouped.values() for item in items],
        }


@router.post("/report-slots/advance")
def advance_report_slots(
    body: SlotAdvanceBody | None = None,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Manual steward/dev trigger. Does not auto-run against cip from this batch."""
    _ = _actor(x_user_id)
    as_of = body.as_of if body else None
    with SessionLocal() as session:
        result = advance_cst_report_slots(session, as_of=as_of, now=datetime.now(timezone.utc))
        session.commit()
        return result


@router.post("/p4-bootstrap-configs")
def p4_bootstrap_configs(
    _admin: dict = Depends(require_roles(Role.ADMIN)),
):
    """P4 — upsert placeholder customer_report_config rows for the remaining pilot roster.

    Admin-only. Idempotent; never touches Takealot (customer_id=20) or any row that
    already has a richer config (see cst_p4_customer_bootstrap._has_richer_config).
    """
    with SessionLocal() as session:
        result = bootstrap_p4_customer_configs(session)
        session.commit()
        return result


@router.get("/article-aliases")
def list_article_aliases(
    status: str | None = Query(default="proposed"),
    customer_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
):
    with SessionLocal() as session:
        stmt = (
            select(CustomerArticleAlias)
            .outerjoin(DimProduct, DimProduct.id == CustomerArticleAlias.product_id)
            .outerjoin(DimCustomer, DimCustomer.id == CustomerArticleAlias.customer_id)
            .order_by(CustomerArticleAlias.id.desc())
        )
        if status and status.strip() and status.strip().lower() != "all":
            statuses = tuple(s.strip() for s in status.split(",") if s.strip())
            stmt = stmt.where(CustomerArticleAlias.status.in_(statuses))
        if customer_id is not None:
            stmt = stmt.where(CustomerArticleAlias.customer_id == customer_id)
        if q and q.strip():
            stmt = stmt.where(article_alias_q_match(q))
        rows = list(session.scalars(stmt.limit(2000)).unique().all())
        cust_ids = {int(r.customer_id) for r in rows}
        prod_ids = {int(r.product_id) for r in rows}
        cmap = {
            int(c.id): c
            for c in session.scalars(select(DimCustomer).where(DimCustomer.id.in_(cust_ids or {0}))).all()
        }
        pmap = {
            int(p.id): p
            for p in session.scalars(select(DimProduct).where(DimProduct.id.in_(prod_ids or {0}))).all()
        }
        return [
            _alias_json(r, cmap.get(int(r.customer_id)), pmap.get(int(r.product_id))) for r in rows
        ]


@router.post("/article-aliases/import")
async def import_article_aliases(
    file: UploadFile = File(...),
    confirm_unique: bool = Query(
        default=False,
        description="If true, confirm SCM unique-match rows after propose (steward-owned).",
    ),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Upload Customer|Article code|Sales Model name workbook → proposed aliases.

    Collisions / ambiguous / miss models are reported and not written. Confirmed
    aliases are never overwritten. Optional confirm_unique confirms only the
    unique-match ids from this upload.
    """
    actor = _actor(x_user_id)
    name = (file.filename or "").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Upload an .xlsx article map")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        rows = parse_article_alias_workbook(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not parse workbook: {exc}") from exc

    with SessionLocal() as session:
        summary = import_article_alias_rows(
            session,
            rows,
            source="scm_upload",
            actor=actor,
        )
        confirm_result = None
        if confirm_unique and summary.proposed_alias_ids:
            confirm_result = confirm_scm_unique_proposed(
                session,
                summary.proposed_alias_ids,
                actor=actor or "scm_import",
            )
        session.commit()
        payload = summary.to_dict()
        payload["confirm"] = confirm_result
        return payload


@router.post("/article-aliases/confirm-import")
def confirm_imported_article_aliases(
    body: AliasImportConfirmBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        result = confirm_scm_unique_proposed(
            session,
            list(body.alias_ids or []),
            actor=actor or "scm_import",
        )
        session.commit()
        return result


@router.patch("/article-aliases/{alias_id}")
def patch_article_alias(
    alias_id: int,
    body: AliasPatchBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Steward edit: retarget product_id, validity window, and optional status."""
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        row = session.get(CustomerArticleAlias, alias_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Alias not found")
        prod = session.get(DimProduct, int(body.product_id)) if body.product_id else session.get(
            DimProduct, int(row.product_id)
        )
        if body.product_id is not None:
            if prod is None:
                raise HTTPException(status_code=400, detail=f"product_id {body.product_id} not found")
            row.product_id = int(body.product_id)
        evidence = dict(row.evidence_json or {}) if isinstance(row.evidence_json, dict) else {}
        trail = list(evidence.get("steward_events") or [])
        trail.append(
            {
                "action": "patch",
                "actor": actor,
                "at": datetime.now(timezone.utc).isoformat(),
                "from_product_id": int(row.product_id),
                "to_product_id": int(body.product_id) if body.product_id else int(row.product_id),
                "from_status": row.status,
                "to_status": body.status or row.status,
                "valid_from": body.valid_from.isoformat() if body.valid_from else None,
                "valid_to": body.valid_to.isoformat() if body.valid_to else None,
            }
        )
        evidence["steward_events"] = trail
        if body.clear_valid_from:
            row.valid_from = None
        elif body.valid_from is not None:
            row.valid_from = body.valid_from
        if body.clear_valid_to:
            row.valid_to = None
        elif body.valid_to is not None:
            row.valid_to = body.valid_to
        if body.status:
            row.status = body.status
        row.evidence_json = to_jsonable(evidence)
        session.add(row)
        try:
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            raise HTTPException(status_code=400, detail=f"Alias patch failed (overlap?): {exc}") from exc
        session.refresh(row)
        cust = session.get(DimCustomer, row.customer_id)
        prod = session.get(DimProduct, row.product_id)
        return _alias_json(row, cust, prod)


@router.post("/article-aliases/derive-eras-from-shipping")
def derive_eras_from_shipping(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Propose dated eras for SCM multi-model articles using inbound POD clock.

    Re-reads Desktop Articles.xlsx when present; otherwise no-op with empty groups.
    Never confirms. Never rewrites applied facts.
    """
    from pathlib import Path

    from app.services.imports.cst_alias_era_derive import (
        collect_scm_multi_model_groups_from_rows,
        derive_alias_eras_from_shipping,
    )
    from app.services.imports.cst_article_alias_import import parse_article_alias_workbook

    actor = _actor(x_user_id)
    scm_path = Path(r"C:\Users\warren_eliason\OneDrive - ASUS\Desktop\Articles.xlsx")
    if not scm_path.is_file():
        raise HTTPException(status_code=400, detail=f"SCM file not found: {scm_path}")
    rows = parse_article_alias_workbook(scm_path.read_bytes())
    with SessionLocal() as session:
        groups = collect_scm_multi_model_groups_from_rows(session, rows)
        summary = derive_alias_eras_from_shipping(session, multi_model_groups=groups, actor=actor)
        session.commit()
        return summary.to_dict()


@router.post("/article-aliases/confirm-shipping-derived")
def confirm_shipping_derived_eras(
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Confirm proposed shipping_derive eras that have a non-steward clock_source.

    Skips steward_manual / equal_pod_sibling. Confirms in valid_from order per article.
    """
    actor = _actor(x_user_id) or "shipping_derive"
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(CustomerArticleAlias).where(CustomerArticleAlias.status == "proposed")
            ).all()
        )
        confirmable = []
        for r in rows:
            ev = r.evidence_json if isinstance(r.evidence_json, dict) else {}
            if ev.get("source") != "shipping_derive":
                continue
            clock = str(ev.get("clock_source") or "")
            if clock in ("steward_manual",) or ev.get("flag") == "equal_pod_sibling":
                continue
            confirmable.append(r)
        # Sort: open-start first, then by valid_from
        confirmable.sort(
            key=lambda r: (
                r.customer_id,
                r.article_no_normalized,
                r.valid_from is not None,
                r.valid_from or date.min,
            )
        )
        confirmed = 0
        failed = 0
        for r in confirmable:
            try:
                with session.begin_nested():
                    confirm_customer_article_alias(session, alias_id=int(r.id), actor=actor)
                    session.flush()
                confirmed += 1
            except Exception:  # noqa: BLE001
                failed += 1
        session.commit()
        return {"confirmed": confirmed, "failed": failed, "candidates": len(confirmable)}


@router.post("/article-aliases/reresolve-job-residuals")
def reresolve_job_residuals(
    job_id: int = Query(...),
    apply: bool = Query(default=False),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Re-resolve unresolved CST staging lines for a job using as-of aliases.

    Does not mutate already-applied fact rows. When apply=true, runs
    apply_customer_sellthrough_staging after re-resolve (new resolved lines only).
    """
    _ = _actor(x_user_id)
    from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
    from app.models.ingestion import ImportJob
    from app.services.imports.customer_sell_through import resolve_product_id_for_sellthrough
    from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging
    from app.services.imports.distributor_sales_inventory import _load_product_resolution_index

    with SessionLocal() as session:
        job = session.get(ImportJob, int(job_id))
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
        cid_raw = meta.get("customer_id")
        if cid_raw is None:
            raise HTTPException(status_code=400, detail="Job missing staged_metadata.customer_id")
        customer_id = int(cid_raw)
        idx = _load_product_resolution_index(session)
        lines = list(
            session.scalars(
                select(ImportCustomerSellthroughStagingLine).where(
                    ImportCustomerSellthroughStagingLine.import_job_id == int(job_id),
                    ImportCustomerSellthroughStagingLine.resolved_product_id.is_(None),
                )
            ).all()
        )
        newly = 0
        for line in lines:
            payload = line.raw_row_payload if isinstance(line.raw_row_payload, dict) else None
            pid = resolve_product_id_for_sellthrough(
                idx,
                line.raw_product_token,
                session=session,
                customer_id=customer_id,
                article_token=getattr(line, "raw_article_token", None),
                raw_row_payload=payload,
                as_of=line.period_start_date,
            )
            if pid is not None:
                line.resolved_product_id = int(pid)
                line.resolution_status = "resolved"
                session.add(line)
                newly += 1
        applied = None
        if apply and newly:
            session.flush()
            summary = apply_customer_sellthrough_staging(session, int(job_id))
            applied = {"applied": summary.applied, "skipped_unresolved": summary.skipped_unresolved}
        session.commit()
        return {
            "job_id": int(job_id),
            "unresolved_before": len(lines),
            "newly_resolved": newly,
            "apply": apply,
            "applied_summary": applied,
        }


@router.post("/article-aliases/{alias_id}/confirm")
def confirm_article_alias(
    alias_id: int,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        row = confirm_customer_article_alias(session, alias_id=alias_id, actor=actor)
        if row is None:
            raise HTTPException(status_code=404, detail="Alias not found")
        session.commit()
        session.refresh(row)
        cust = session.get(DimCustomer, row.customer_id)
        prod = session.get(DimProduct, row.product_id)
        return _alias_json(row, cust, prod)


@router.post("/article-aliases/{alias_id}/reject")
def reject_article_alias(
    alias_id: int,
    body: AliasRejectBody | None = None,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    actor = _actor(x_user_id)
    with SessionLocal() as session:
        row = reject_customer_article_alias(
            session,
            alias_id=alias_id,
            actor=actor,
            reason=(body.reason if body else None),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Alias not found")
        session.commit()
        session.refresh(row)
        cust = session.get(DimCustomer, row.customer_id)
        prod = session.get(DimProduct, row.product_id)
        return _alias_json(row, cust, prod)
