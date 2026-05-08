"""Distributor stewardship for shipment / order evidence (Bill To / Ship To tokens).

V1: aggregate unresolved lines, create ``DistributorSourceTokenAlias`` mappings, optional provisional
``DimDistributor`` rows, and re-run strict distributor resolution for affected import jobs.
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dimensions import DimDistributor
from app.models.ingestion import ImportJob
from app.models.import_distributor_si import DistributorSourceTokenAlias
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_steward_candidate_ops import DISTRIBUTOR_PROVISIONAL_SUSPICIOUS
from app.services.imports.shipment_evidence_import import resolve_distributor_for_evidence


def _job_source_id(db: Session, job_id: int) -> int | None:
    job = db.get(ImportJob, job_id)
    if not job:
        return None
    return int(job.source_id) if job.source_id else None


def _allocate_tmp_distributor_code(db: Session) -> str:
    for _ in range(32):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        cand = f"TMP-DIST-{stamp}-{secrets.token_hex(3).upper()}"[:32]
        exists = db.scalar(select(DimDistributor.id).where(DimDistributor.code == cand))
        if exists is None:
            return cand
    raise RuntimeError("Could not allocate temporary distributor code")


def reprocess_shipment_distributor_resolution(
    db: Session,
    *,
    import_job_id: int | None = None,
    line_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Recompute distributor_id / status / token for shipment lines (strict resolution + aliases)."""
    q = select(ShipmentEvidenceLine)
    if line_ids is not None:
        lids = [int(x) for x in line_ids]
        if not lids:
            return {"lines_scanned": 0, "lines_updated": 0}
        q = q.where(ShipmentEvidenceLine.id.in_(lids))
    elif import_job_id is not None:
        q = q.where(ShipmentEvidenceLine.import_job_id == int(import_job_id))
    else:
        raise ValueError("import_job_id or line_ids is required")

    scanned = 0
    updated = 0
    cache: dict[int, int | None] = {}
    for line in db.scalars(q):
        scanned += 1
        jid = int(line.import_job_id)
        if jid not in cache:
            cache[jid] = _job_source_id(db, jid)
        sid = cache[jid]
        did, dstatus, dtoken = resolve_distributor_for_evidence(
            db, sid, bill_to=line.bill_to_raw, ship_to=line.ship_to_raw
        )
        cur_tok = line.distributor_resolution_token
        if (
            line.distributor_id != did
            or line.distributor_resolution_status != dstatus
            or (cur_tok or None) != (dtoken or None)
        ):
            line.distributor_id = did
            line.distributor_resolution_status = dstatus
            line.distributor_resolution_token = dtoken
            updated += 1
    db.commit()
    return {"lines_scanned": scanned, "lines_updated": updated}


def _existing_approved_alias_for_token(
    db: Session, *, source_definition_id: int | None, normalized_token: str
) -> DistributorSourceTokenAlias | None:
    q = select(DistributorSourceTokenAlias).where(
        DistributorSourceTokenAlias.normalized_token == normalized_token,
        DistributorSourceTokenAlias.status == "approved",
    )
    if source_definition_id is not None:
        q = q.where(
            or_(
                DistributorSourceTokenAlias.source_definition_id.is_(None),
                DistributorSourceTokenAlias.source_definition_id == source_definition_id,
            )
        )
    else:
        q = q.where(DistributorSourceTokenAlias.source_definition_id.is_(None))
    rows = list(db.scalars(q).all())
    if not rows:
        return None
    return rows[0]


def list_shipment_distributor_steward_tokens(db: Session, import_job_id: int | None) -> list[dict[str, Any]]:
    q = select(ShipmentEvidenceLine).where(
        ShipmentEvidenceLine.distributor_id.is_(None),
        ShipmentEvidenceLine.distributor_resolution_status == "unresolved",
    )
    if import_job_id is not None:
        q = q.where(ShipmentEvidenceLine.import_job_id == int(import_job_id))
    rows = list(db.scalars(q))

    groups: dict[tuple[int, str, str], dict[str, Any]] = {}

    def bump(key: tuple[int, str, str], line: ShipmentEvidenceLine, raw_display: str) -> None:
        g = groups.get(key)
        if g is None:
            g = {
                "import_job_id": key[0],
                "party": key[1],
                "normalized_token": key[2],
                "representative_raw_token": raw_display.strip()[:512],
                "row_count": 0,
                "total_quantity": Decimal(0),
                "total_amount": Decimal(0),
                "sample_line_ids": [],
                "sample_source_row_numbers": [],
            }
            groups[key] = g
        g["row_count"] += 1
        if line.quantity is not None:
            g["total_quantity"] += Decimal(str(line.quantity))
        if line.amount is not None:
            g["total_amount"] += Decimal(str(line.amount))
        if len(g["sample_line_ids"]) < 30:
            g["sample_line_ids"].append(int(line.id))
        if len(g["sample_source_row_numbers"]) < 15:
            g["sample_source_row_numbers"].append(int(line.source_row_number))

    for line in rows:
        jid = int(line.import_job_id)
        if line.bill_to_raw and str(line.bill_to_raw).strip():
            nk = _norm_key(line.bill_to_raw)
            if nk:
                bump((jid, "bill_to", nk), line, str(line.bill_to_raw))
        if line.ship_to_raw and str(line.ship_to_raw).strip():
            nk = _norm_key(line.ship_to_raw)
            if nk:
                bump((jid, "ship_to", nk), line, str(line.ship_to_raw))

    out: list[dict[str, Any]] = []
    for g in groups.values():
        job = db.get(ImportJob, int(g["import_job_id"]))
        tq = g["total_quantity"]
        ta = g["total_amount"]
        out.append(
            {
                "import_job_id": g["import_job_id"],
                "party": g["party"],
                "normalized_token": g["normalized_token"],
                "representative_raw_token": g["representative_raw_token"],
                "row_count": g["row_count"],
                "total_quantity": float(tq) if tq is not None else None,
                "total_amount": float(ta) if ta is not None else None,
                "sample_line_ids": g["sample_line_ids"],
                "sample_source_row_numbers": g["sample_source_row_numbers"],
                "import_job_file_name": job.file_name if job else None,
            }
        )
    out.sort(key=lambda x: (-int(x["row_count"]), x["party"], x["normalized_token"]))
    return out


def map_shipment_party_token_to_distributor(
    db: Session,
    *,
    import_job_id: int,
    party: str,
    raw_token: str,
    distributor_id: int,
    notes: str | None = None,
) -> dict[str, Any]:
    if party not in ("bill_to", "ship_to"):
        raise ValueError("party must be bill_to or ship_to")
    raw = raw_token.strip()
    nt = _norm_key(raw)
    if not nt:
        raise ValueError("raw_token is empty after normalization")
    dist = db.get(DimDistributor, int(distributor_id))
    if not dist:
        raise ValueError("distributor not found")
    job = db.get(ImportJob, int(import_job_id))
    if not job:
        raise ValueError("import job not found")
    sid = int(job.source_id) if job.source_id else None

    existing = _existing_approved_alias_for_token(db, source_definition_id=sid, normalized_token=nt)
    if existing is not None and int(existing.distributor_id) != int(distributor_id):
        raise ValueError("An approved alias already maps this token to a different distributor")
    if existing is not None and int(existing.distributor_id) == int(distributor_id):
        rp = reprocess_shipment_distributor_resolution(db, import_job_id=int(import_job_id))
        return {"ok": True, "idempotent": True, "alias_id": int(existing.id), "distributor_id": int(distributor_id), **rp}

    alias = DistributorSourceTokenAlias(
        distributor_id=int(distributor_id),
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=sid,
        status="approved",
        notes=(notes or f"Shipment evidence steward map ({party}, job {import_job_id})")[:2000],
        created_from_import_job_id=int(import_job_id),
    )
    db.add(alias)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Could not create distributor alias (conflict)") from exc

    rp = reprocess_shipment_distributor_resolution(db, import_job_id=int(import_job_id))
    return {"ok": True, "alias_id": int(alias.id), "distributor_id": int(distributor_id), **rp}


def create_provisional_distributor_for_shipment_party_token(
    db: Session,
    *,
    import_job_id: int,
    party: str,
    raw_token: str,
    display_name: str | None,
    distributor_code: str | None,
    confirm_for_suspicious_token: bool,
) -> dict[str, Any]:
    if party not in ("bill_to", "ship_to"):
        raise ValueError("party must be bill_to or ship_to")
    raw = raw_token.strip()
    nt = _norm_key(raw)
    if not nt:
        raise ValueError("raw_token is empty after normalization")
    if nt in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS and not confirm_for_suspicious_token:
        raise ValueError("suspicious_token_requires_confirm")

    job = db.get(ImportJob, int(import_job_id))
    if not job:
        raise ValueError("import job not found")
    sid = int(job.source_id) if job.source_id else None

    existing = _existing_approved_alias_for_token(db, source_definition_id=sid, normalized_token=nt)
    if existing is not None:
        raise ValueError("Token already has an approved distributor alias")

    code = (distributor_code or "").strip()[:32] or _allocate_tmp_distributor_code(db)
    if db.scalar(select(DimDistributor.id).where(DimDistributor.code == code)) is not None:
        raise ValueError("distributor_code already exists")

    name = (display_name or raw).strip()[:256] or code
    row = DimDistributor(code=code, name=name)
    db.add(row)
    db.flush()
    alias = DistributorSourceTokenAlias(
        distributor_id=int(row.id),
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=sid,
        status="approved",
        notes=f"Provisional distributor from shipment evidence steward ({party}, job {import_job_id})",
        created_from_import_job_id=int(import_job_id),
    )
    db.add(alias)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Could not create provisional distributor") from exc

    rp = reprocess_shipment_distributor_resolution(db, import_job_id=int(import_job_id))
    return {
        "ok": True,
        "distributor_id": int(row.id),
        "distributor_code": row.code,
        "alias_id": int(alias.id),
        **rp,
    }
