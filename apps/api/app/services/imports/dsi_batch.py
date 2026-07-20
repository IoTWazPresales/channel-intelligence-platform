"""DSI multi-file batch: capability grouping and unified job creation."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.imports.dsi_mapping_workflow import infer_dsi_job_sync
from app.services.imports.dsi_workbook import (
    DSI_SIGNATURE_MAX_ROWS,
    _sheet_looks_dsi_mappable,
    load_dsi_workbook_sheet_frames,
    raw_file_display_name,
)
from app.storage.local import get_storage_backend
from app.utils.json_safe import to_jsonable

# Stable group ids for propose/create (not exact-header hashes).
DSI_CAPABLE_GROUP_SIGNATURE = "dsi_capable"
DSI_UNMAPPABLE_GROUP_SIGNATURE = "unmappable"


@dataclass(frozen=True)
class DsiFilePreview:
    filename: str
    signature: str
    column_count: int
    sheet_count: int
    unmappable: bool
    unmappable_reason: str | None = None


@dataclass(frozen=True)
class DsiBatchGroupPreview:
    signature: str
    files: list[DsiFilePreview]


def dsi_layout_signature(headers: list[str]) -> str:
    """Stable fingerprint of a column layout (presentation-grain for mapping tabs).

    Normalize: strip + lower; drop empties; keep duplicates; sort; sha256[:16].
    """
    norms = [str(h).strip().lower() for h in headers if str(h).strip()]
    norms.sort()
    normalized = ",".join(norms)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def normalized_header_signature(
    filename: str, raw_bytes: bytes
) -> tuple[str, int, int, bool, str | None]:
    """Diagnose a file: header fingerprint + mappable flag.

    The fingerprint is retained for UI transparency / debugging. Batch grouping no longer
    splits on exact header equality — see ``propose_dsi_batch_groups``.
    """
    try:
        frames = load_dsi_workbook_sheet_frames(
            filename, raw_bytes, max_data_rows=DSI_SIGNATURE_MAX_ROWS
        )
    except Exception:
        return ("unmappable", 0, 0, True, "parse_error")

    sheet_count = len(frames)
    if not frames or all(int(df.shape[1]) == 0 for _sn, df, _hr in frames):
        return ("unmappable", 0, sheet_count, True, "empty")
    primary_cols: set[str] = set()
    for _sheet_name, df, _header_row in frames:
        if _sheet_looks_dsi_mappable(df):
            primary_cols = {str(c).strip().lower() for c in df.columns if str(c).strip()}
            break
    if not primary_cols:
        return ("unmappable", 0, sheet_count, True, "no_dsi_headers")
    sig = dsi_layout_signature(list(primary_cols))
    return (sig, len(primary_cols), sheet_count, False, None)


def propose_dsi_batch_groups(
    files: list[tuple[str, bytes]],
) -> list[DsiBatchGroupPreview]:
    """Group uploaded files by DSI capability (read-only, no DB).

    All files that parse and expose DSI-like headers join **one** ``dsi_capable`` group so
    nested per-file mapping + per-file distributor stamps share a single steward session.
    Exact column-layout equality is not required (Power BI–style combine). Unmappable files
    are returned in a separate ``unmappable`` group and are not turned into jobs.
    """
    previews: list[DsiFilePreview] = []
    for filename, raw_bytes in files:
        sig, col_count, sheet_count, unmappable, reason = normalized_header_signature(
            filename, raw_bytes
        )
        previews.append(
            DsiFilePreview(
                filename=filename,
                signature=sig,
                column_count=col_count,
                sheet_count=sheet_count,
                unmappable=unmappable,
                unmappable_reason=reason,
            )
        )

    capable = [p for p in previews if not p.unmappable]
    unmappable_files = [p for p in previews if p.unmappable]

    groups: list[DsiBatchGroupPreview] = []
    if capable:
        groups.append(
            DsiBatchGroupPreview(signature=DSI_CAPABLE_GROUP_SIGNATURE, files=capable)
        )
    if unmappable_files:
        groups.append(
            DsiBatchGroupPreview(
                signature=DSI_UNMAPPABLE_GROUP_SIGNATURE, files=unmappable_files
            )
        )
    return groups


def _batch_job_display_name(filenames: list[str]) -> str:
    if not filenames:
        return "batch"
    if len(filenames) == 1:
        return filenames[0]
    if len(filenames) <= 3:
        return " + ".join(filenames)
    return f"{filenames[0]} +{len(filenames) - 1} more"


def create_dsi_batch_job_sync(
    db: Session,
    *,
    source_id: int,
    filenames_and_bytes: list[tuple[str, bytes]],
    import_mode: str = "validate",
    dsi_workflow_mode: str = "auto",
) -> ImportJob:
    """Create one DSI import job with N raw files; run infer."""
    if not filenames_and_bytes:
        raise ValueError("create_dsi_batch_job_sync requires at least one file")

    source = db.scalar(
        select(SourceDefinition)
        .options(joinedload(SourceDefinition.import_template))
        .where(SourceDefinition.id == source_id)
    )
    if not source or not source.is_active:
        raise ValueError("Unknown or inactive source_id")
    tpl = source.import_template
    if not tpl or tpl.slug != "distributor_inventory":
        raise ValueError("DSI batch jobs require distributor_inventory source")

    filenames = [fn for fn, _ in filenames_and_bytes]
    job = ImportJob(
        source_id=source_id,
        template_slug=tpl.slug,
        import_mode=import_mode,
        status="pending",
        stage="uploaded",
        file_name=_batch_job_display_name(filenames),
        content_type=None,
    )
    db.add(job)
    db.flush()

    mode_explicit = (dsi_workflow_mode or "auto").strip().lower()
    if mode_explicit not in ("auto", "historical", "weekly"):
        mode_explicit = "auto"
    sm = dict(job.staged_metadata or {})
    sm["dsi_workflow_mode_explicit"] = mode_explicit
    sm["dsi_multi_file"] = len(filenames_and_bytes) > 1
    sm["dsi_batch_filenames"] = filenames
    job.staged_metadata = to_jsonable(sm)
    db.add(job)

    storage = get_storage_backend()
    for filename, raw_bytes in filenames_and_bytes:
        key = f"imports/{uuid.uuid4().hex}/{filename}"
        storage.save(key, raw_bytes, None)
        db.add(
            RawFileMetadata(
                job_id=job.id,
                storage_key=key,
                byte_size=len(raw_bytes),
                checksum=None,
            )
        )
    db.commit()
    db.refresh(job)

    infer_dsi_job_sync(db, job.id)
    refreshed = db.get(ImportJob, job.id)
    if refreshed is None:
        raise RuntimeError("DSI batch job missing after infer")
    return refreshed


def batch_groups_preview_to_dict(groups: list[DsiBatchGroupPreview]) -> list[dict[str, Any]]:
    return [
        {
            "signature": g.signature,
            "files": [
                {
                    "filename": f.filename,
                    "signature": f.signature,
                    "column_count": f.column_count,
                    "sheet_count": f.sheet_count,
                    "unmappable": f.unmappable,
                    "unmappable_reason": f.unmappable_reason,
                }
                for f in g.files
            ],
        }
        for g in groups
    ]


def list_raw_files_for_job(db: Session, job_id: int) -> list[RawFileMetadata]:
    return list(
        db.scalars(
            select(RawFileMetadata)
            .where(RawFileMetadata.job_id == job_id)
            .order_by(RawFileMetadata.id.asc())
        ).all()
    )


def get_dsi_excluded_filenames(job: ImportJob) -> set[str]:
    sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = sm.get("dsi_excluded_files")
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if str(x).strip()}


def get_dsi_excluded_mapping_keys(job: ImportJob) -> set[str]:
    """Per-sheet exclusions within an included file (e.g. undateable Sell out sheet)."""
    sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = sm.get("dsi_excluded_mapping_keys")
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if str(x).strip()}


def set_dsi_file_exclusions_sync(
    db: Session,
    job_id: int,
    *,
    excluded_filenames: list[str],
    excluded_mapping_keys: list[str] | None = None,
) -> ImportJob:
    """Set pre-apply file/sheet exclusions; clear staging and return job to mapping-ready for re-validate."""
    from sqlalchemy import delete

    from app.models.import_distributor_si import ImportDistributorSiStagingLine, ImportEntityMappingCandidate
    from app.models.ingestion import ImportRowResult

    job = db.get(ImportJob, job_id)
    if job is None or job.template_slug != "distributor_inventory":
        raise ValueError("DSI file exclusions require a distributor_inventory job")

    cleaned = sorted({str(x).strip() for x in excluded_filenames if str(x).strip()})
    sm = dict(job.staged_metadata or {})
    sm["dsi_excluded_files"] = cleaned
    if excluded_mapping_keys is not None:
        sm["dsi_excluded_mapping_keys"] = sorted(
            {str(x).strip() for x in excluded_mapping_keys if str(x).strip()}
        )
    job.staged_metadata = to_jsonable(sm)

    db.execute(
        delete(ImportDistributorSiStagingLine).where(
            ImportDistributorSiStagingLine.import_job_id == int(job_id)
        )
    )
    db.execute(
        delete(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == int(job_id)
        )
    )
    db.execute(delete(ImportRowResult).where(ImportRowResult.job_id == int(job_id)))

    job.stage = "dsi_mapping_ready"
    job.status = "pending"
    job.error_summary = None
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
