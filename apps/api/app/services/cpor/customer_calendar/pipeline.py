"""Mapping profiles, upload preview and apply for customer calendars (sync session).

Preview parses the file through the profile and reports what would be written: events per
customer, rows that could not be read, customer names that match no customer. Nothing is written
and no customer is created (a name that matches no customer, or more than one, is listed for a
steward to fix in the file or the customer master). Apply writes the same events and replaces the
earlier events of the same upload for the same customers, so applying a file twice leaves the same
rows.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.customer_calendar import CustomerCalendarEvent, CustomerCalendarMappingProfile
from app.models.dimensions import DimCustomer
from app.services.cpor.customer_calendar.parser import parse_calendar_file
from app.services.cpor.customer_calendar.profiles import (
    DEFAULT_PROFILE_CODE,
    default_calendar_profile,
    validate_profile,
)
from app.services.cpor.customer_calendar.scope import bind_calendar_tenant

PREVIEW_EVENT_LIMIT = 200
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class CalendarUploadError(Exception):
    """A request the caller can fix (bad profile, unknown customer, nothing to apply)."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# --------------------------------------------------------------------------- profiles


def profile_to_dict(row: CustomerCalendarMappingProfile) -> dict[str, Any]:
    return {
        "id": row.id,
        "profile_code": row.profile_code,
        "display_name": row.display_name,
        "header_row_index": row.header_row_index,
        "sheet_name": row.sheet_name,
        "column_map_json": row.column_map_json,
        "value_maps_json": row.value_maps_json,
        "is_default": row.is_default,
        "notes": row.notes,
    }


def ensure_default_profile(db: Session, tenant_id: str) -> CustomerCalendarMappingProfile:
    bind_calendar_tenant(db, tenant_id)
    row = db.scalar(
        select(CustomerCalendarMappingProfile).where(
            CustomerCalendarMappingProfile.tenant_id == tenant_id,
            CustomerCalendarMappingProfile.profile_code == DEFAULT_PROFILE_CODE,
        )
    )
    if row is not None:
        return row
    d = default_calendar_profile()
    db.execute(
        pg_insert(CustomerCalendarMappingProfile)
        .values(
            tenant_id=tenant_id,
            profile_code=d["profile_code"],
            display_name=d["display_name"],
            header_row_index=d["header_row_index"],
            sheet_name=d["sheet_name"],
            column_map_json=d["column_map_json"],
            value_maps_json=d["value_maps_json"],
            is_default=True,
            notes=d["notes"],
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "profile_code"])
    )
    return db.scalar(
        select(CustomerCalendarMappingProfile).where(
            CustomerCalendarMappingProfile.tenant_id == tenant_id,
            CustomerCalendarMappingProfile.profile_code == DEFAULT_PROFILE_CODE,
        )
    )


def list_profiles(db: Session, tenant_id: str) -> list[CustomerCalendarMappingProfile]:
    ensure_default_profile(db, tenant_id)
    return list(
        db.scalars(
            select(CustomerCalendarMappingProfile)
            .where(CustomerCalendarMappingProfile.tenant_id == tenant_id)
            .order_by(CustomerCalendarMappingProfile.id)
        ).all()
    )


def _profile_or_404(db: Session, tenant_id: str, profile_id: int) -> CustomerCalendarMappingProfile:
    bind_calendar_tenant(db, tenant_id)
    row = db.scalar(
        select(CustomerCalendarMappingProfile).where(
            CustomerCalendarMappingProfile.tenant_id == tenant_id,
            CustomerCalendarMappingProfile.id == profile_id,
        )
    )
    if row is None:
        raise CalendarUploadError("profile_not_found", "Calendar mapping profile not found", 404)
    return row


def save_profile(
    db: Session,
    tenant_id: str,
    payload: dict[str, Any],
    *,
    profile_id: int | None = None,
    actor: str | None = None,
) -> CustomerCalendarMappingProfile:
    """Create (profile_id None) or update a tenant profile after validating its mapping."""
    bind_calendar_tenant(db, tenant_id)
    problems = validate_profile(payload)
    if problems:
        raise CalendarUploadError("invalid_profile", "; ".join(problems), 422)
    code = str(payload.get("profile_code") or "").strip()
    if not code:
        raise CalendarUploadError("invalid_profile", "profile_code is required", 422)
    clash = db.scalar(
        select(CustomerCalendarMappingProfile.id).where(
            CustomerCalendarMappingProfile.tenant_id == tenant_id,
            CustomerCalendarMappingProfile.profile_code == code,
        )
    )
    if profile_id is None:
        if clash is not None:
            raise CalendarUploadError("profile_exists", f"Profile {code!r} already exists", 409)
        row = CustomerCalendarMappingProfile(tenant_id=tenant_id, profile_code=code)
        db.add(row)
    else:
        row = _profile_or_404(db, tenant_id, profile_id)
        if clash is not None and clash != row.id:
            raise CalendarUploadError("profile_exists", f"Profile {code!r} already exists", 409)
        row.profile_code = code
    row.display_name = str(payload.get("display_name") or code)[:256]
    row.header_row_index = int(payload.get("header_row_index") or 1)
    row.sheet_name = (
        (str(payload.get("sheet_name")).strip() or None) if payload.get("sheet_name") else None
    )
    row.column_map_json = payload["column_map_json"]
    row.value_maps_json = payload.get("value_maps_json") or {"kind": {}}
    row.notes = payload.get("notes")
    row.updated_by = actor
    if payload.get("is_default"):
        for other in db.scalars(
            select(CustomerCalendarMappingProfile).where(
                CustomerCalendarMappingProfile.tenant_id == tenant_id,
                CustomerCalendarMappingProfile.is_default.is_(True),
            )
        ).all():
            if other is not row:
                other.is_default = False
        row.is_default = True
    elif profile_id is not None and "is_default" in payload:
        row.is_default = False
    db.flush()
    return row


def delete_profile(db: Session, tenant_id: str, profile_id: int) -> None:
    row = _profile_or_404(db, tenant_id, profile_id)
    if row.is_default and row.profile_code == DEFAULT_PROFILE_CODE:
        raise CalendarUploadError(
            "profile_protected", "The generic default profile cannot be deleted", 409
        )
    db.delete(row)
    db.flush()


def resolve_profile(
    db: Session, tenant_id: str, profile_code: str | None
) -> tuple[dict[str, Any], int | None]:
    """The named profile, else the tenant default, else the generic default: (profile, id)."""
    bind_calendar_tenant(db, tenant_id)
    row = None
    if profile_code:
        row = db.scalar(
            select(CustomerCalendarMappingProfile).where(
                CustomerCalendarMappingProfile.tenant_id == tenant_id,
                CustomerCalendarMappingProfile.profile_code == profile_code,
            )
        )
        if row is None and profile_code != DEFAULT_PROFILE_CODE:
            raise CalendarUploadError(
                "profile_not_found", f"Profile {profile_code!r} not found", 404
            )
    else:
        row = db.scalar(
            select(CustomerCalendarMappingProfile)
            .where(
                CustomerCalendarMappingProfile.tenant_id == tenant_id,
                CustomerCalendarMappingProfile.is_default.is_(True),
            )
            .order_by(CustomerCalendarMappingProfile.id)
        )
    if row is None:
        return default_calendar_profile(), None
    return profile_to_dict(row), int(row.id)


# --------------------------------------------------------------------------- customers


def _norm(s: str | None) -> str:
    return " ".join(str(s or "").strip().lower().split())


def resolve_customer_tokens(db: Session, tenant_id: str, tokens: set[str]) -> dict[str, int]:
    """Normalised token -> customer id, where exactly one customer (after merges) matches."""
    if not tokens:
        return {}
    from app.services.merge_redirect import (
        build_redirect_map,
        collapse_ids,
        merged_into_customer_id,
    )

    customers = list(
        db.scalars(select(DimCustomer).where(DimCustomer.tenant_id == tenant_id)).all()
    )
    redirect = build_redirect_map((int(c.id), merged_into_customer_id(c)) for c in customers)
    buckets: dict[str, list[int]] = defaultdict(list)
    for c in customers:
        for key in (_norm(c.code), _norm(c.name)):
            if key and key in tokens:
                buckets[key].append(int(c.id))
    out: dict[str, int] = {}
    for tok, ids in buckets.items():
        uniq = collapse_ids(ids, redirect)
        if len(uniq) == 1:
            out[tok] = uniq[0]
    return out


def _customer_names(db: Session, tenant_id: str, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.execute(
        select(DimCustomer.id, DimCustomer.name).where(
            DimCustomer.tenant_id == tenant_id, DimCustomer.id.in_(sorted(ids))
        )
    ).all()
    return {int(i): str(n) for i, n in rows}


# --------------------------------------------------------------------------- upload


def default_upload_id(filename: str) -> str:
    base = os.path.basename((filename or "").replace("\\", "/")).strip().lower()
    base = re.sub(r"\s+", "-", base)
    return (base or "upload")[:128]


def _plan(
    db: Session,
    tenant_id: str,
    *,
    filename: str,
    data: bytes,
    profile_code: str | None,
    customer_id: int | None,
    upload_id: str | None,
) -> dict[str, Any]:
    if not data:
        raise CalendarUploadError("empty_file", "The file is empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise CalendarUploadError("file_too_large", "The file is larger than 10 MB", 413)
    profile, profile_id = resolve_profile(db, tenant_id, profile_code)
    parsed = parse_calendar_file(filename, data, profile)

    fixed_customer: int | None = None
    if customer_id is not None:
        names = _customer_names(db, tenant_id, {int(customer_id)})
        if int(customer_id) not in names:
            raise CalendarUploadError("customer_not_found", "Customer not found", 404)
        fixed_customer = int(customer_id)

    events = parsed["events"]
    tokens = {_norm(e["customer_token"]) for e in events if e.get("customer_token")}
    by_token = {} if fixed_customer is not None else resolve_customer_tokens(db, tenant_id, tokens)

    placed: list[dict[str, Any]] = []
    unresolved: dict[str, dict[str, Any]] = {}
    for e in events:
        if fixed_customer is not None:
            cid = fixed_customer
        else:
            token = _norm(e.get("customer_token"))
            cid = by_token.get(token)
            if cid is None:
                label = e.get("customer_token") or ""
                slot = unresolved.setdefault(token, {"token": label, "rows": 0})
                slot["rows"] += 1
                continue
        placed.append({**e, "customer_id": cid})

    names = _customer_names(db, tenant_id, {int(p["customer_id"]) for p in placed})
    per_customer: dict[int, int] = defaultdict(int)
    for p in placed:
        per_customer[int(p["customer_id"])] += 1

    uid = (upload_id or "").strip()[:128] or default_upload_id(filename)
    replaces = 0
    if per_customer:
        replaces = int(
            db.scalar(
                select(func.count())
                .select_from(CustomerCalendarEvent)
                .where(
                    CustomerCalendarEvent.tenant_id == tenant_id,
                    CustomerCalendarEvent.upload_id == uid,
                    CustomerCalendarEvent.customer_id.in_(sorted(per_customer)),
                )
            )
            or 0
        )
    return {
        "parsed": parsed,
        "profile_id": profile_id,
        "profile_code": profile.get("profile_code"),
        "placed": placed,
        "unresolved": list(unresolved.values()),
        "customers": [
            {"customer_id": cid, "customer_name": names.get(cid, ""), "events": n}
            for cid, n in sorted(per_customer.items())
        ],
        "upload_id": uid,
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "will_replace": replaces,
    }


def _event_out(e: dict[str, Any], names: dict[int, str]) -> dict[str, Any]:
    return {
        "row_number": e["row_number"],
        "customer_id": e["customer_id"],
        "customer_name": names.get(int(e["customer_id"]), ""),
        "name": e["name"],
        "kind": e["kind"],
        "start_date": e["start_date"].isoformat(),
        "end_date": e["end_date"].isoformat(),
    }


def preview_upload(
    db: Session,
    tenant_id: str,
    *,
    filename: str,
    data: bytes,
    profile_code: str | None = None,
    customer_id: int | None = None,
    upload_id: str | None = None,
) -> dict[str, Any]:
    plan = _plan(
        db,
        tenant_id,
        filename=filename,
        data=data,
        profile_code=profile_code,
        customer_id=customer_id,
        upload_id=upload_id,
    )
    parsed = plan["parsed"]
    names = {c["customer_id"]: c["customer_name"] for c in plan["customers"]}
    placed = plan["placed"]
    return {
        "ok": bool(parsed["ok"]) and bool(placed),
        "filename": filename,
        "profile_code": plan["profile_code"],
        "upload_id": plan["upload_id"],
        "file_sha256": plan["file_sha256"],
        "headers": parsed["headers"],
        "mapped_columns": parsed["mapped_columns"],
        "blocking_errors": parsed["blocking_errors"],
        "row_errors": parsed["row_errors"],
        "parsed_rows": parsed["row_count"],
        "will_insert": len(placed),
        "will_replace": plan["will_replace"],
        "customers": plan["customers"],
        "unresolved_customers": plan["unresolved"],
        "events": [_event_out(e, names) for e in placed[:PREVIEW_EVENT_LIMIT]],
        "events_truncated": len(placed) > PREVIEW_EVENT_LIMIT,
    }


def apply_upload(
    db: Session,
    tenant_id: str,
    *,
    filename: str,
    data: bytes,
    profile_code: str | None = None,
    customer_id: int | None = None,
    upload_id: str | None = None,
    actor: str | None = None,
) -> dict[str, Any]:
    plan = _plan(
        db,
        tenant_id,
        filename=filename,
        data=data,
        profile_code=profile_code,
        customer_id=customer_id,
        upload_id=upload_id,
    )
    parsed = plan["parsed"]
    if parsed["blocking_errors"]:
        raise CalendarUploadError(
            "blocking_errors", "; ".join(e["message"] for e in parsed["blocking_errors"][:3])
        )
    placed = plan["placed"]
    if not placed:
        raise CalendarUploadError(
            "nothing_to_apply",
            "No rows could be placed on a customer: pick a customer for the file "
            "or fix the unmatched names",
        )

    customer_ids = sorted({int(p["customer_id"]) for p in placed})
    # Serialize replacement of this tenant/upload, including its first-ever apply. A row lock
    # cannot protect a not-yet-existing upload. The endpoint owns this lock's transaction.
    bind_calendar_tenant(db, tenant_id)
    db.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(
                    f"customer-calendar:{tenant_id}:{plan['upload_id']}",
                    0,
                )
            )
        )
    )
    deleted = db.execute(
        delete(CustomerCalendarEvent).where(
            CustomerCalendarEvent.tenant_id == tenant_id,
            CustomerCalendarEvent.upload_id == plan["upload_id"],
            CustomerCalendarEvent.customer_id.in_(customer_ids),
        )
    ).rowcount
    for offset in range(0, len(placed), 1000):
        db.execute(
            insert(CustomerCalendarEvent),
            [
                dict(
                    tenant_id=tenant_id,
                    customer_id=int(p["customer_id"]),
                    name=p["name"],
                    kind=p["kind"],
                    start_date=p["start_date"],
                    end_date=p["end_date"],
                    upload_id=plan["upload_id"],
                    source_file=(filename or "")[:512] or None,
                    source_row=p["row_number"],
                    file_sha256=plan["file_sha256"],
                    profile_id=plan["profile_id"],
                    raw_source_row=p["raw_row"],
                    created_by=actor,
                )
                for p in placed[offset : offset + 1000]
            ],
        )
    db.flush()
    return {
        "upload_id": plan["upload_id"],
        "inserted": len(placed),
        "replaced": int(deleted or 0),
        "customers": plan["customers"],
        "unresolved_customers": plan["unresolved"],
        "row_errors": len(parsed["row_errors"]),
        "file_sha256": plan["file_sha256"],
    }
