"""Steward apply for shipment evidence distributor candidates (sync Session).

Apply intentionally **updates ``ShipmentEvidenceLine`` rows in place** using ``context.line_ids``,
unlike DSI distributor map/provisional executors which do not touch staging lines.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dimensions import DimDistributor
from app.models.import_distributor_si import DistributorSourceTokenAlias, ImportEntityMappingCandidate
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_steward_candidate_ops import DISTRIBUTOR_PROVISIONAL_SUSPICIOUS
from app.services.imports.shipment_evidence_resolution_plan import SHIPMENT_DISTRIBUTOR_ENTITY


class ShipmentStewardOpError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = message


def _first_sample_raw(cand: ImportEntityMappingCandidate) -> str:
    samples = cand.sample_raw_values or []
    for s in samples:
        if isinstance(s, str) and s.strip():
            return s.strip()[:512]
    return (cand.normalized_key or "").strip()[:512]


def _allocate_tmp_distributor_code(db: Session) -> str:
    for _ in range(32):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        cand = f"TMP-DIST-{stamp}-{secrets.token_hex(3).upper()}"[:32]
        exists = db.scalar(select(DimDistributor.id).where(DimDistributor.code == cand))
        if exists is None:
            return cand
    raise ShipmentStewardOpError("Could not allocate temporary distributor code", status_code=503)


def _line_ids_from_context(cand: ImportEntityMappingCandidate) -> list[int]:
    ctx = cand.context if isinstance(cand.context, dict) else {}
    raw = ctx.get("line_ids")
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for x in raw:
        try:
            out.append(int(x))
        except (TypeError, ValueError):
            continue
    return out


def _verify_line_scope(db: Session, cand: ImportEntityMappingCandidate, line_ids: list[int]) -> None:
    jid = int(cand.import_job_id)
    for lid in line_ids:
        row = db.get(ShipmentEvidenceLine, lid)
        if not row or int(row.import_job_id) != jid:
            raise ShipmentStewardOpError(f"Line {lid} not in scope for candidate job {jid}", status_code=400)


def _update_lines_resolved(
    db: Session,
    *,
    line_ids: list[int],
    distributor_id: int,
    resolution_token: str,
) -> int:
    n = 0
    tok = (resolution_token or "")[:512]
    for lid in line_ids:
        line = db.get(ShipmentEvidenceLine, lid)
        if line is None:
            continue
        line.distributor_id = int(distributor_id)
        line.distributor_resolution_status = "resolved"
        line.distributor_resolution_token = tok
        n += 1
    return n


def execute_map_shipment_distributor(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    distributor_id: int,
    raw_token: str | None,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_distributor candidate", status_code=400)
    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)
    dist = db.get(DimDistributor, int(distributor_id))
    if not dist:
        raise ShipmentStewardOpError("distributor_id not found", status_code=404)
    raw = (raw_token or _first_sample_raw(cand)).strip()
    if not raw:
        raise ShipmentStewardOpError("raw_token required", status_code=400)
    nt = _norm_key(raw)
    if not nt:
        raise ShipmentStewardOpError("raw_token empty after normalization", status_code=400)

    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        raise ShipmentStewardOpError("candidate.context.line_ids missing or empty", status_code=400)
    _verify_line_scope(db, cand, line_ids)

    alias = DistributorSourceTokenAlias(
        distributor_id=int(distributor_id),
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        status="approved",
        notes=f"Mapped from shipment evidence candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
    )
    db.add(alias)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ShipmentStewardOpError("Could not create distributor alias (duplicate or conflict)", status_code=409) from exc

    _update_lines_resolved(db, line_ids=line_ids, distributor_id=int(distributor_id), resolution_token=raw)
    cand.status = "resolved"
    cand.suggested_entity_id = int(distributor_id)
    cand.match_reason = "steward_map_existing_distributor"
    db.add(cand)
    db.commit()
    db.refresh(alias)
    return {"ok": True, "alias_id": int(alias.id), "distributor_id": int(distributor_id), "candidate_id": int(cand.id), "lines_updated": len(line_ids)}


def execute_create_provisional_shipment_distributor(
    db: Session,
    cand: ImportEntityMappingCandidate,
    *,
    display_name: str | None,
    distributor_code: str | None,
    confirm_for_suspicious_token: bool,
) -> dict[str, Any]:
    if cand.entity_type != SHIPMENT_DISTRIBUTOR_ENTITY:
        raise ShipmentStewardOpError("Not a shipment_distributor candidate", status_code=400)
    if cand.status in ("resolved", "ignored", "waived_open_channel"):
        raise ShipmentStewardOpError("Candidate already terminal", status_code=400)

    raw = _first_sample_raw(cand)
    nt = _norm_key(raw)
    if not nt:
        raise ShipmentStewardOpError("Token empty after normalization", status_code=400)
    if nt in DISTRIBUTOR_PROVISIONAL_SUSPICIOUS and not confirm_for_suspicious_token:
        raise ShipmentStewardOpError(
            "suspicious_token_requires_confirm — set confirm_for_suspicious_token=true",
            status_code=400,
        )

    line_ids = _line_ids_from_context(cand)
    if not line_ids:
        raise ShipmentStewardOpError("candidate.context.line_ids missing or empty", status_code=400)
    _verify_line_scope(db, cand, line_ids)

    code = (distributor_code or "").strip()[:32] or _allocate_tmp_distributor_code(db)
    if db.scalar(select(DimDistributor.id).where(DimDistributor.code == code)) is not None:
        raise ShipmentStewardOpError("distributor_code already exists", status_code=409)

    name = (display_name or raw).strip()[:256] or code
    row = DimDistributor(code=code, name=name)
    db.add(row)
    db.flush()

    alias = DistributorSourceTokenAlias(
        distributor_id=int(row.id),
        raw_token=raw[:512],
        normalized_token=nt[:512],
        source_definition_id=cand.source_definition_id,
        status="approved",
        notes=f"Provisional distributor from shipment evidence candidate {cand.id} (job {cand.import_job_id})",
        created_from_import_job_id=cand.import_job_id,
    )
    db.add(alias)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ShipmentStewardOpError("Could not create provisional distributor or alias", status_code=409) from exc

    _update_lines_resolved(db, line_ids=line_ids, distributor_id=int(row.id), resolution_token=raw)
    cand.status = "resolved"
    cand.suggested_entity_id = int(row.id)
    cand.match_reason = "steward_created_provisional_distributor"
    db.add(cand)
    db.commit()
    db.refresh(row)
    db.refresh(alias)
    return {
        "ok": True,
        "distributor_id": int(row.id),
        "distributor_code": row.code,
        "alias_id": int(alias.id),
        "candidate_id": int(cand.id),
        "lines_updated": len(line_ids),
    }
