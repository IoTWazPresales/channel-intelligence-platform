"""Store and DC replenishment. Steward writes. Imports do not create locations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import Role, get_current_user, require_roles
from app.core.tenant_scope import tenant_id_from_user
from app.db.session_sync import SessionLocal
from app.services.store_dc.candidates import (
    decide_candidate,
    list_candidates,
    refresh_candidates,
    save_tenant_config,
    set_served_accounts,
    tenant_config,
)
from app.services.store_dc.level import set_site_level
from app.services.store_dc.map import build_store_map, drop_pin
from app.services.store_dc.read_model import (
    build_customer_view,
    list_board_customers,
    set_customer_thresholds,
)
from app.services.store_dc.rules import SiteLevelRejected

router = APIRouter()


def _sync_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _actor(user: dict) -> str:
    return str(user.get("id") or user.get("email") or "steward")[:128]


def _tenant(user: dict) -> str:
    return tenant_id_from_user(user)


class LevelBody(BaseModel):
    site_level: str | None = None
    site_owner: str | None = None


class DecisionBody(BaseModel):
    decision: str


class ServedBody(BaseModel):
    customer_ids: list[int] = Field(default_factory=list)


class ConfigBody(BaseModel):
    lead_time_min_deliveries: int | None = None
    dc_name_patterns: list[str] | None = None
    stock_behaviour_min_soh: float | None = None


class ThresholdBody(BaseModel):
    slow_cover_multiple: float | None = None
    unsold_weeks: float | None = None


class PinBody(BaseModel):
    customer_id: int
    site_label: str
    latitude: float
    longitude: float


def _run(fn):
    try:
        return fn()
    except SiteLevelRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError:
        raise HTTPException(status_code=404, detail="Not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/locations/{owner_table}/{location_id}/level")
def post_site_level(
    owner_table: str,
    location_id: int,
    body: LevelBody,
    db: Session = Depends(_sync_db),
    user: dict = Depends(require_roles(Role.STEWARD)),
):
    return _run(
        lambda: set_site_level(
            db,
            owner_table=owner_table,
            location_id=location_id,
            site_level=body.site_level,
            site_owner=body.site_owner,
            actor=_actor(user),
        )
    )


@router.get("/customers")
def get_customers(db: Session = Depends(_sync_db), user: dict = Depends(get_current_user)):
    return {"customers": list_board_customers(db, _tenant(user))}


@router.get("/customers/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(_sync_db), user: dict = Depends(get_current_user)):
    return _run(lambda: build_customer_view(db, _tenant(user), customer_id))


@router.put("/customers/{customer_id}/thresholds")
def put_thresholds(
    customer_id: int,
    body: ThresholdBody,
    db: Session = Depends(_sync_db),
    user: dict = Depends(require_roles(Role.STEWARD)),
):
    fields = body.model_fields_set
    return _run(
        lambda: set_customer_thresholds(
            db,
            _tenant(user),
            customer_id,
            slow_cover_multiple=body.slow_cover_multiple,
            unsold_weeks=body.unsold_weeks,
            set_slow="slow_cover_multiple" in fields,
            set_unsold="unsold_weeks" in fields,
        )
    )


@router.get("/candidates")
def get_candidates(
    status: str | None = None,
    db: Session = Depends(_sync_db),
    user: dict = Depends(get_current_user),
):
    return {"candidates": list_candidates(db, _tenant(user), status=status)}


@router.post("/candidates/refresh")
def post_refresh(db: Session = Depends(_sync_db), user: dict = Depends(require_roles(Role.STEWARD))):
    return refresh_candidates(db, _tenant(user))


@router.post("/candidates/{candidate_id}/decision")
def post_decision(
    candidate_id: int,
    body: DecisionBody,
    db: Session = Depends(_sync_db),
    user: dict = Depends(require_roles(Role.STEWARD)),
):
    return _run(lambda: decide_candidate(db, _tenant(user), candidate_id, body.decision, _actor(user)))


@router.put("/candidates/{candidate_id}/served-accounts")
def put_served(
    candidate_id: int,
    body: ServedBody,
    db: Session = Depends(_sync_db),
    user: dict = Depends(require_roles(Role.STEWARD)),
):
    return _run(lambda: set_served_accounts(db, _tenant(user), candidate_id, body.customer_ids))


@router.get("/config")
def get_config(db: Session = Depends(_sync_db), user: dict = Depends(get_current_user)):
    return tenant_config(db, _tenant(user))


@router.put("/config")
def put_config(body: ConfigBody, db: Session = Depends(_sync_db), user: dict = Depends(require_roles(Role.STEWARD))):
    return _run(
        lambda: save_tenant_config(
            db,
            _tenant(user),
            lead_time_min_deliveries=body.lead_time_min_deliveries,
            dc_name_patterns=body.dc_name_patterns,
            stock_behaviour_min_soh=body.stock_behaviour_min_soh,
        )
    )


@router.get("/lead-times")
def get_lead_times(
    customer_id: int | None = None,
    db: Session = Depends(_sync_db),
    user: dict = Depends(get_current_user),
):
    if customer_id is None:
        cfg = tenant_config(db, _tenant(user))
        from app.services.store_dc.rules import onward_leg

        return {
            "lead_time_min_deliveries": cfg["lead_time_min_deliveries"],
            "lead_times": [],
            "onward": onward_leg(),
        }
    view = _run(lambda: build_customer_view(db, _tenant(user), customer_id))
    return {
        "customer_id": customer_id,
        "lead_time_min_deliveries": view["lead_time_min_deliveries"],
        "lead_times": view["lead_times"],
    }


@router.get("/map")
def get_map(
    customer_id: list[int] = Query(default=[]),
    db: Session = Depends(_sync_db),
    user: dict = Depends(get_current_user),
):
    return build_store_map(db, _tenant(user), customer_id or None)


@router.post("/pins")
def post_pin(body: PinBody, db: Session = Depends(_sync_db), user: dict = Depends(require_roles(Role.STEWARD))):
    return _run(
        lambda: drop_pin(
            db,
            tenant_id=_tenant(user),
            customer_id=body.customer_id,
            site_label=body.site_label,
            latitude=body.latitude,
            longitude=body.longitude,
            actor=_actor(user),
        )
    )
