"""Customer promotion calendar API (final wave d).

Mapping profiles (CRUD), calendar upload preview / apply, and the per-customer timeline that
returns our CPOR promotion windows, the customer's uploaded calendar events and the clashes.
Same shape as the CPOR payment-evidence and historical-import routes: reads need sign-in, writes
need steward / planner / admin, every write is steward-audited.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.cpor_cases import _actor
from app.core.security import Role, get_current_user, require_roles
from app.core.tenant_scope import tenant_id_from_user
from app.db.session_sync import SessionLocal
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.services.customer_reporting import reporting_customer_clauses
from app.services.cpor.customer_calendar.pipeline import (
    MAX_UPLOAD_BYTES,
    CalendarUploadError,
    apply_upload,
    delete_profile,
    list_profiles,
    preview_upload,
    profile_to_dict,
    save_profile,
)
from app.services.cpor.customer_calendar.timeline import build_clash_summary, build_timeline
from app.services.steward_audit import record_steward_audit_sync

router = APIRouter()
_require_calendar_writer = require_roles(Role.STEWARD, Role.PLANNER, Role.ADMIN)
IMPORTER = "cpor_customer_calendar"


class ProfileBody(BaseModel):
    profile_code: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=256)
    header_row_index: int = Field(default=1, ge=1)
    sheet_name: str | None = Field(default=None, max_length=128)
    column_map_json: dict[str, list[str]]
    value_maps_json: dict[str, Any] = Field(default_factory=lambda: {"kind": {}})
    is_default: bool = False
    notes: str | None = None


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


_Reader = Annotated[dict, Depends(get_current_user)]
_Writer = Annotated[dict, Depends(_require_calendar_writer)]
_Db = Annotated[Session, Depends(_sync_db)]


def _http(exc: CalendarUploadError) -> HTTPException:
    return HTTPException(status_code=exc.status, detail={"code": exc.code, "message": exc.message})


def _calendar_unavailable(exc: ProgrammingError, db: Session) -> dict[str, Any]:
    if getattr(exc.orig, "sqlstate", None) != "42P01":
        raise exc
    db.rollback()
    return {
        "data_unavailable": True,
        "message": (
            "Customer calendar tables are unavailable. "
            "The calendar migration must be applied before use."
        ),
    }


def _read_upload(file: UploadFile) -> bytes:
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "file_too_large", "message": "The file is larger than 10 MB"},
        )
    return data


@router.get("/profiles")
def list_calendar_profiles(_user: _Reader, db: _Db) -> dict[str, Any]:
    """Saved profiles plus the computed generic default. Read only: nothing is created here."""
    try:
        profiles = list_profiles(db, tenant_id_from_user(_user))
    except ProgrammingError as exc:
        return {**_calendar_unavailable(exc, db), "profiles": []}
    return {"profiles": profiles}


@router.post("/profiles", status_code=201)
def create_calendar_profile(body: ProfileBody, _user: _Writer, db: _Db) -> dict[str, Any]:
    tenant = tenant_id_from_user(_user)
    try:
        row = save_profile(db, tenant, body.model_dump(), actor=_actor(_user))
    except CalendarUploadError as exc:
        raise _http(exc) from exc
    record_steward_audit_sync(
        _user,
        action="customer_calendar_profile_create",
        importer=IMPORTER,
        entity_type="customer_calendar_mapping_profile",
        entity_token=row.profile_code,
        target_id=row.id,
        payload={"profile_code": row.profile_code},
        db=db,
    )
    return profile_to_dict(row)


@router.put("/profiles/{profile_id}")
def update_calendar_profile(
    profile_id: int, body: ProfileBody, _user: _Writer, db: _Db
) -> dict[str, Any]:
    tenant = tenant_id_from_user(_user)
    try:
        row = save_profile(
            db, tenant, body.model_dump(), profile_id=profile_id, actor=_actor(_user)
        )
    except CalendarUploadError as exc:
        raise _http(exc) from exc
    record_steward_audit_sync(
        _user,
        action="customer_calendar_profile_update",
        importer=IMPORTER,
        entity_type="customer_calendar_mapping_profile",
        entity_token=row.profile_code,
        target_id=row.id,
        payload={"profile_code": row.profile_code},
        db=db,
    )
    return profile_to_dict(row)


@router.delete("/profiles/{profile_id}")
def delete_calendar_profile(profile_id: int, _user: _Writer, db: _Db) -> dict[str, Any]:
    try:
        delete_profile(db, tenant_id_from_user(_user), profile_id)
    except CalendarUploadError as exc:
        raise _http(exc) from exc
    record_steward_audit_sync(
        _user,
        action="customer_calendar_profile_delete",
        importer=IMPORTER,
        entity_type="customer_calendar_mapping_profile",
        target_id=profile_id,
        payload={"profile_id": profile_id},
        db=db,
    )
    return {"deleted": profile_id}


@router.post("/upload/preview")
def preview_calendar_upload(
    file: Annotated[UploadFile, File()],
    _user: _Writer,
    db: _Db,
    profile_code: Annotated[str | None, Form()] = None,
    customer_id: Annotated[int | None, Form()] = None,
    upload_id: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    """Parse the file through the mapping profile and report what apply would write.

    Writes nothing.
    """
    try:
        return preview_upload(
            db,
            tenant_id_from_user(_user),
            filename=file.filename or "upload",
            data=_read_upload(file),
            profile_code=profile_code,
            customer_id=customer_id,
            upload_id=upload_id,
        )
    except CalendarUploadError as exc:
        raise _http(exc) from exc


@router.post("/upload/apply")
def apply_calendar_upload(
    file: Annotated[UploadFile, File()],
    _user: _Writer,
    db: _Db,
    confirm: Annotated[bool, Form()] = False,
    profile_code: Annotated[str | None, Form()] = None,
    customer_id: Annotated[int | None, Form()] = None,
    upload_id: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    """Write the events, replacing this upload's earlier events for the same customers."""
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    try:
        out = apply_upload(
            db,
            tenant_id_from_user(_user),
            filename=file.filename or "upload",
            data=_read_upload(file),
            profile_code=profile_code,
            customer_id=customer_id,
            upload_id=upload_id,
            actor=_actor(_user),
        )
    except CalendarUploadError as exc:
        raise _http(exc) from exc
    record_steward_audit_sync(
        _user,
        action="customer_calendar_apply",
        importer=IMPORTER,
        entity_type="customer_calendar_upload",
        entity_token=out["upload_id"],
        payload={k: out[k] for k in ("upload_id", "inserted", "replaced", "file_sha256")},
        db=db,
    )
    return out


@router.get("/reporting-customers")
def calendar_reporting_customers(_user: _Reader, db: _Db) -> dict[str, Any]:
    """Reporting customers of the tenant (same definition as CST / line-up pickers)."""
    tenant = tenant_id_from_user(_user)
    rows = db.execute(
        select(DimCustomer.id, DimCustomer.name, DimCustomer.code)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(DimCustomer.tenant_id == tenant, *reporting_customer_clauses())
        .order_by(func.lower(DimCustomer.name), DimCustomer.id)
    ).all()
    return {
        "customers": [
            {"id": int(cid), "name": name, "code": code}
            for cid, name, code in rows
        ]
    }


@router.get("/clashes/summary")
def clash_summary(
    _user: _Reader,
    db: _Db,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    """Exact count of our open promotions that clash with customer calendar events, all customers.

    The planner's calendar-clash card. Same rules as ``/timeline`` (superseded, cancelled, fixture
    and fully voided cases left out; clashes are same-customer date overlaps, inclusive).
    """
    if date_from is not None and date_to is not None and date_to < date_from:
        raise HTTPException(status_code=422, detail="'to' is before 'from'")
    try:
        return build_clash_summary(
            db, tenant_id_from_user(_user), date_from=date_from, date_to=date_to
        )
    except ProgrammingError as exc:
        return _calendar_unavailable(exc, db)


@router.get("/timeline")
def customer_timeline(
    customer_id: Annotated[int, Query(gt=0)],
    _user: _Reader,
    db: _Db,
    date_from: Annotated[date | None, Query(alias="from")] = None,
    date_to: Annotated[date | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    """Our open CPOR promotions, the customer's calendar events and the clashes between them."""
    if date_from is not None and date_to is not None and date_to < date_from:
        raise HTTPException(status_code=422, detail="'to' is before 'from'")
    try:
        out = build_timeline(
            db,
            tenant_id_from_user(_user),
            customer_id=customer_id,
            date_from=date_from,
            date_to=date_to,
        )
    except ProgrammingError as exc:
        return {
            **_calendar_unavailable(exc, db),
            "promotions": [],
            "calendar_events": [],
            "clashes": [],
        }
    if out is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return out
