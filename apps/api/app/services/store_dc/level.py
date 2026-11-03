"""Steward action on a location that already exists. Does not create a location."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.dimensions import CustomerLocation, DistributorLocation
from app.services.store_dc.rules import SITE_LEVELS, assert_owner_level

_TABLES = {
    "customer": CustomerLocation,
    "distributor": DistributorLocation,
}


def location_payload(row: CustomerLocation | DistributorLocation, *, owner_table: str) -> dict:
    payload = {
        "id": row.id,
        "owner_table": owner_table,
        "location_code": row.location_code,
        "location_name": row.location_name,
        "location_type": row.location_type,
        "site_level": row.site_level,
        "site_owner": row.site_owner,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
        "confirmed_by": row.confirmed_by,
        "levels": list(SITE_LEVELS),
    }
    if isinstance(row, CustomerLocation):
        payload["customer_id"] = row.customer_id
        payload["latitude"] = float(row.latitude) if row.latitude is not None else None
        payload["longitude"] = float(row.longitude) if row.longitude is not None else None
    else:
        payload["distributor_id"] = row.distributor_id
    return payload


def set_site_level(
    db: Session,
    *,
    owner_table: str,
    location_id: int,
    site_level: str | None,
    site_owner: str | None,
    actor: str,
) -> dict:
    model = _TABLES.get(owner_table)
    if model is None:
        raise LookupError(owner_table)
    row = db.get(model, location_id)
    if row is None:
        raise LookupError(str(location_id))
    owner = site_owner if site_owner is not None else row.site_owner
    assert_owner_level(owner, site_level)
    row.site_owner = owner
    row.site_level = site_level
    if site_level:
        row.confirmed_at = datetime.now(timezone.utc)
        row.confirmed_by = actor
    else:
        row.confirmed_at = None
        row.confirmed_by = None
    db.flush()
    return location_payload(row, owner_table=owner_table)
