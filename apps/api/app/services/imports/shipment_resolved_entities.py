"""Populate ``resolved_*`` entity columns on shipment evidence lines (Unit 1 PO↔lineup alignment).

Uses the same alias resolvers as validate/steward — no second resolver or fuzzy matching.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.distributor_sales_inventory import (
    _norm_key,
    _resolve_distributor_strict,
    _resolve_distributor_strict_from_cache,
)
from app.services.imports.shipment_customer_alias_scope import lookup_approved_customer_alias_for_scope
from app.services.imports.shipment_evidence_import import _parse_date

if TYPE_CHECKING:
    from app.models.ingestion import ImportJob
    from app.services.imports.dsi_resolution_cache import DSIResolutionCache


def parse_crad_from_raw_row(raw: dict[str, Any] | None) -> date | None:
    """Parse CRAD from evidence ``raw_source_row`` (workbook header ``CRAD``)."""
    if not isinstance(raw, dict):
        return None
    val = raw.get("CRAD")
    if val is None:
        for k, v in raw.items():
            if isinstance(k, str) and k.strip().upper() == "CRAD":
                val = v
                break
    return _parse_date(val)


def resolve_shipment_customer_id_from_token(
    db: Session,
    raw_token: str | None,
    source_definition_id: int | None,
) -> int | None:
    """Scoped ``customer_source_token_alias`` lookup (shipment steward scope — distributor_id None)."""
    if not raw_token or not str(raw_token).strip():
        return None
    nt = _norm_key(str(raw_token).strip())
    if not nt:
        return None
    row = lookup_approved_customer_alias_for_scope(
        db,
        normalized_token=nt,
        source_definition_id=source_definition_id,
        distributor_id=None,
    )
    return int(row.customer_id) if row is not None else None


def resolve_shipment_distributor_id_from_line(
    db: Session,
    *,
    bill_to_raw: str | None,
    ship_to_raw: str | None,
    source_definition_id: int | None,
    res_cache: "DSIResolutionCache | None" = None,
) -> int | None:
    """Alias-target root via strict distributor resolver (Bill To then Ship To)."""

    def _resolve(tok: str) -> int | None:
        if res_cache is not None:
            did, _err = _resolve_distributor_strict_from_cache(tok, source_definition_id, res_cache)
        else:
            did, _err = _resolve_distributor_strict(db, tok, source_definition_id)
        return int(did) if did is not None else None

    if bill_to_raw and str(bill_to_raw).strip():
        did = _resolve(str(bill_to_raw).strip())
        if did is not None:
            return did
    if ship_to_raw and str(ship_to_raw).strip():
        return _resolve(str(ship_to_raw).strip())
    return None


def apply_resolved_entities_to_line(
    line: ShipmentEvidenceLine,
    db: Session,
    source_definition_id: int | None,
    *,
    res_cache: "DSIResolutionCache | None" = None,
) -> None:
    """Set ``resolved_*`` on one line; keep in sync with stamped ``customer_id`` / ``distributor_id``."""
    if line.distributor_id is not None:
        line.resolved_distributor_id = int(line.distributor_id)
    elif line.resolved_distributor_id is None:
        did = resolve_shipment_distributor_id_from_line(
            db,
            bill_to_raw=line.bill_to_raw,
            ship_to_raw=line.ship_to_raw,
            source_definition_id=source_definition_id,
            res_cache=res_cache,
        )
        if did is not None:
            line.resolved_distributor_id = did

    if line.customer_id is not None:
        line.resolved_customer_id = int(line.customer_id)
    elif line.resolved_customer_id is None and line.customer_dealer_token:
        cid = resolve_shipment_customer_id_from_token(
            db, line.customer_dealer_token, source_definition_id
        )
        if cid is not None:
            line.resolved_customer_id = cid

    if line.crad_date is None:
        raw = line.raw_source_row if isinstance(line.raw_source_row, dict) else {}
        line.crad_date = parse_crad_from_raw_row(raw)


def populate_resolved_entities_for_job(
    db: Session,
    job: "ImportJob",
    *,
    res_cache: "DSIResolutionCache | None" = None,
) -> int:
    """Populate ``resolved_*`` + ``crad_date`` for every evidence line on the job."""
    jid = int(job.id)
    sid = int(job.source_id) if job.source_id else None
    lines = list(
        db.scalars(select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == jid)).all()
    )
    for line in lines:
        apply_resolved_entities_to_line(line, db, sid, res_cache=res_cache)
        db.add(line)
    db.flush()
    return len(lines)
