"""Daily FX quotes, missing-rate suggestions, and operator-confirmed FX mode declaration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.core.security import get_current_user
from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.db.session_sync import SessionLocal
from app.models.cpor import CporCase
from app.services.cpor.fx_rate import (
    SOURCE_OPERATOR,
    confirm_backfill_suggestion,
    declare_fx_mode,
    ensure_rate_for_date,
    ensure_today_rate,
)
from app.services.cpor.intelligence_scope import where_commercial_intelligence
from app.services.cpor.settle_readiness import FX_MODES, case_missing_roe, fx_declared, fx_mode_valid

router = APIRouter()


class BackfillItem(BaseModel):
    case_id: int
    rate: float | None = None


class BackfillConfirmBody(BaseModel):
    items: list[BackfillItem] = Field(..., min_length=1)


class DeclareModeBody(BaseModel):
    confirm: bool = False
    mode: str = "booked"
    case_ids: list[int] | None = None


def _actor(user: dict) -> str:
    return str(user.get("display_name") or user.get("id") or "unknown")


def _tenant_cases(session, user: dict):
    return session.scalars(
        select(CporCase)
        .where(where_tenant(CporCase.tenant_id, user))
        .where(where_commercial_intelligence())
    ).all()


@router.get("/fx/rates/today")
def fx_rate_today(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    _ = user
    with SessionLocal() as session:
        quote = ensure_today_rate(session)
        session.commit()
        return quote.as_json()


@router.post("/fx/rates/fetch")
def fx_rate_fetch(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    _ = user
    with SessionLocal() as session:
        quote = ensure_today_rate(session)
        session.commit()
        return quote.as_json()


@router.get("/fx/backfill-suggestions")
def fx_backfill_suggestions(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Suggest rates only for cases that genuinely lack a positive ROE snapshot.

    Cases that already have a rate and are blocked because fx_mode is missing
    are counted, not suggested — use POST /fx/declare-mode for those.
    """
    _ = tenant_id_from_user(user)
    with SessionLocal() as session:
        cases = _tenant_cases(session, user)
        missing_rate = [c for c in cases if case_missing_roe(c)]
        rate_no_mode = [c for c in cases if fx_declared(c) and not fx_mode_valid(c)]
        by_date: dict = {}
        items: list[dict[str, Any]] = []
        for case in missing_rate:
            window = case.window_start
            if window not in by_date:
                by_date[window] = ensure_rate_for_date(session, window)
            quote = by_date[window]
            items.append(
                {
                    "case_id": case.id,
                    "case_code": case.case_code,
                    "status": case.status,
                    "window_start": window.isoformat() if window else None,
                    "customer_id": case.customer_id,
                    "fx_proposed_rate": (
                        float(case.fx_proposed_rate) if case.fx_proposed_rate is not None else None
                    ),
                    "suggested_rate": quote.rate,
                    "suggested_rate_date": quote.rate_date.isoformat() if quote.rate_date else None,
                    "source": quote.source,
                    "is_fallback": quote.is_fallback,
                    "fetch_failed": quote.fetch_failed,
                    "will_book_on_confirm": (case.status or "").strip().lower()
                    in {"approved", "active", "ended"},
                }
            )
        session.commit()
        return {
            "items": items,
            "count": len(items),
            "missing_rate_count": len(missing_rate),
            "rate_no_mode_count": len(rate_no_mode),
        }


@router.post("/fx/backfill-confirm")
def fx_backfill_confirm(
    body: BackfillConfirmBody,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    actor = _actor(user)
    with SessionLocal() as session:
        results: list[dict[str, Any]] = []
        for item in body.items:
            case = session.get(CporCase, item.case_id)
            if case is None or (getattr(case, "tenant_id", None) or "default") != tenant_id_from_user(
                user
            ):
                results.append({"case_id": item.case_id, "ok": False, "reason": "not_found"})
                continue
            if not case_missing_roe(case):
                results.append({"case_id": case.id, "ok": False, "reason": "already_declared"})
                continue
            rate = item.rate
            source = SOURCE_OPERATOR
            if rate is None:
                quote = ensure_rate_for_date(session, case.window_start)
                rate = quote.rate
                source = quote.source
            if rate is None:
                results.append({"case_id": case.id, "ok": False, "reason": "no_rate"})
                continue
            out = confirm_backfill_suggestion(case, float(rate), actor, source=source)
            out["case_id"] = case.id
            out["case_code"] = case.case_code
            if out.get("ok"):
                session.add(case)
            results.append(out)
        session.commit()
        confirmed = sum(1 for r in results if r.get("ok"))
        booked = sum(1 for r in results if r.get("booked"))
        return {"results": results, "confirmed": confirmed, "booked": booked}


@router.post("/fx/declare-mode")
def fx_declare_mode(
    body: DeclareModeBody,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Bulk-set fx_mode. Never auto. Never writes roe_snapshot."""
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="confirm=true is required — FX mode is never auto-declared",
        )
    mode = (body.mode or "").strip().lower()
    if mode not in FX_MODES:
        raise HTTPException(status_code=400, detail=f"fx_mode must be one of: {sorted(FX_MODES)}")
    actor = _actor(user)
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        stmt = (
            select(CporCase)
            .where(where_tenant(CporCase.tenant_id, user))
            .where(CporCase.roe_snapshot.is_not(None))
            .where(CporCase.roe_snapshot > 0)
            .where(or_(CporCase.fx_mode.is_(None), CporCase.fx_mode.notin_(list(FX_MODES))))
        )
        if body.case_ids:
            stmt = stmt.where(CporCase.id.in_(body.case_ids))
        else:
            stmt = stmt.where(where_commercial_intelligence())
        cases = session.scalars(stmt).all()
        declared_ids: list[int] = []
        skipped = 0
        failed: list[dict[str, Any]] = []
        for case in cases:
            out = declare_fx_mode(case, mode, actor, now=now)
            if out.get("ok") and not out.get("skipped"):
                declared_ids.append(int(case.id))
            elif out.get("skipped"):
                skipped += 1
            else:
                failed.append({"case_id": case.id, "reason": out.get("reason")})
        session.commit()
        return {
            "declared": len(declared_ids),
            "skipped": skipped,
            "failed": failed,
            "mode": mode,
            "case_ids": declared_ids,
        }
