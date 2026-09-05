"""Daily FX quotes and FX-blocked backfill suggestions — booked-rate lifecycle."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.security import get_current_user
from app.core.tenant_scope import tenant_id_from_user, where_tenant
from app.db.session_sync import SessionLocal
from app.models.cpor import CporCase
from app.services.cpor.fx_rate import (
    SOURCE_OPERATOR,
    confirm_backfill_suggestion,
    ensure_rate_for_date,
    ensure_today_rate,
)
from app.services.cpor.settle_readiness import settle_fx_blocked

router = APIRouter()


class BackfillItem(BaseModel):
    case_id: int
    rate: float | None = None


class BackfillConfirmBody(BaseModel):
    items: list[BackfillItem] = Field(..., min_length=1)


def _actor(user: dict) -> str:
    return str(user.get("display_name") or user.get("id") or "unknown")


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
    with SessionLocal() as session:
        cases = session.scalars(
            where_tenant(select(CporCase), CporCase, tenant_id_from_user(user))
        ).all()
        blocked = [c for c in cases if settle_fx_blocked(c)]
        by_date: dict = {}
        items: list[dict[str, Any]] = []
        for case in blocked:
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
        return {"items": items, "count": len(items)}


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
