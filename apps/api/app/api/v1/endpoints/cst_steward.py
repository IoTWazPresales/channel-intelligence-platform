"""CST D1 steward surfaces — key accounts, report config, slots, article aliases.

No schema. FLAG ≠ BLOCK. No auto-create of master records (config upsert is steward-owned).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.session_sync import SessionLocal
from app.models.customer_article_alias import CustomerArticleAlias
from app.models.customer_cst_report_slot import CustomerCstReportSlot
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer, DimProduct
from app.services.imports.cst_d1 import (
    advance_cst_report_slots,
    confirm_customer_article_alias,
    reject_customer_article_alias,
)
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


def _alias_json(row: CustomerArticleAlias, customer: DimCustomer | None, product: DimProduct | None) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "customer_code": customer.code if customer else None,
        "customer_name": customer.name if customer else None,
        "article_no_normalized": row.article_no_normalized,
        "product_id": row.product_id,
        "product_sku": product.sku if product else None,
        "product_name": product.name if product else None,
        "status": row.status,
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


class KeyAccountPatch(BaseModel):
    is_key_account: bool | None = None
    reports_expected: bool | None = None
    expected_cadence: str | None = Field(default=None, max_length=16)
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


class AliasRejectBody(BaseModel):
    reason: str | None = None


class SlotAdvanceBody(BaseModel):
    as_of: date | None = None


@router.get("/key-accounts")
def list_key_account_steward(
    q: str | None = Query(default=None),
    key_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Steward grid: customers with key-account flag + report config (upserted on edit)."""
    with SessionLocal() as session:
        filters = []
        if key_only:
            filters.append(DimCustomer.is_key_account.is_(True))
        if q and q.strip():
            needle = f"%{q.strip()}%"
            filters.append(or_(DimCustomer.code.ilike(needle), DimCustomer.name.ilike(needle)))

        count_stmt = (
            select(func.count())
            .select_from(DimCustomer)
            .outerjoin(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        )
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = int(session.scalar(count_stmt) or 0)

        stmt = (
            select(DimCustomer, CustomerReportConfig)
            .outerjoin(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
            .order_by(DimCustomer.name.asc(), DimCustomer.id.asc())
        )
        if filters:
            stmt = stmt.where(*filters)
        rows = session.execute(stmt.limit(limit).offset(offset)).all()
        return {
            "items": [_config_json(cfg, customer=cust) for cust, cfg in rows],
            "total": total,
        }


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
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    with SessionLocal() as session:
        if status and status.strip():
            statuses = tuple(s.strip() for s in status.split(",") if s.strip())
        else:
            statuses = ("due", "late", "missing")
        for s in statuses:
            if s not in ("due", "late", "missing", "received"):
                raise HTTPException(status_code=400, detail=f"Unknown slot status={s}")

        base_where = CustomerCstReportSlot.status.in_(statuses)
        counts = {
            "due": int(
                session.scalar(
                    select(func.count()).select_from(CustomerCstReportSlot).where(
                        CustomerCstReportSlot.status == "due"
                    )
                )
                or 0
            ),
            "late": int(
                session.scalar(
                    select(func.count()).select_from(CustomerCstReportSlot).where(
                        CustomerCstReportSlot.status == "late"
                    )
                )
                or 0
            ),
            "missing": int(
                session.scalar(
                    select(func.count()).select_from(CustomerCstReportSlot).where(
                        CustomerCstReportSlot.status == "missing"
                    )
                )
                or 0
            ),
            "received": int(
                session.scalar(
                    select(func.count()).select_from(CustomerCstReportSlot).where(
                        CustomerCstReportSlot.status == "received"
                    )
                )
                or 0
            ),
        }
        total = int(
            session.scalar(
                select(func.count()).select_from(CustomerCstReportSlot).where(base_where)
            )
            or 0
        )
        slots = list(
            session.scalars(
                select(CustomerCstReportSlot)
                .where(base_where)
                .order_by(
                    CustomerCstReportSlot.week_start_date.desc(),
                    CustomerCstReportSlot.id.desc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
        )
        cust_ids = {int(s.customer_id) for s in slots}
        cmap: dict[int, DimCustomer] = {}
        if cust_ids:
            for c in session.scalars(select(DimCustomer).where(DimCustomer.id.in_(cust_ids))).all():
                cmap[int(c.id)] = c
        items = [_slot_json(slot, cmap.get(int(slot.customer_id))) for slot in slots]
        return {
            "as_of": date.today().isoformat(),
            "counts": counts,
            "total": total,
            "items": items,
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


@router.get("/article-aliases")
def list_article_aliases(
    status: str | None = Query(default="proposed"),
    customer_id: int | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    with SessionLocal() as session:
        filters = []
        if status and status.strip() and status.strip().lower() != "all":
            statuses = tuple(s.strip() for s in status.split(",") if s.strip())
            filters.append(CustomerArticleAlias.status.in_(statuses))
        if customer_id is not None:
            filters.append(CustomerArticleAlias.customer_id == customer_id)
        if q and q.strip():
            needle = f"%{q.strip().lower()}%"
            filters.append(CustomerArticleAlias.article_no_normalized.ilike(needle))

        count_stmt = select(func.count()).select_from(CustomerArticleAlias)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = int(session.scalar(count_stmt) or 0)

        stmt = select(CustomerArticleAlias).order_by(CustomerArticleAlias.id.desc())
        if filters:
            stmt = stmt.where(*filters)
        rows = list(session.scalars(stmt.limit(limit).offset(offset)).all())
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
        return {
            "items": [
                _alias_json(r, cmap.get(int(r.customer_id)), pmap.get(int(r.product_id))) for r in rows
            ],
            "total": total,
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
