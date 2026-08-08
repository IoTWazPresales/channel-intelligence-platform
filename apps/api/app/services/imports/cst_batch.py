"""CST multi-file batch: capability grouping and unified job creation (DSI parity)."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.storage.local import get_storage_backend
from app.utils.json_safe import to_jsonable

CST_TEMPLATE_SLUG = "customer_sell_through"
CST_CAPABLE_GROUP_SIGNATURE = "cst_capable"
CST_UNMAPPABLE_GROUP_SIGNATURE = "unmappable"

# Header tokens that indicate a Takealot-style / flat CST sales sheet (case-insensitive).
_CST_SIGNAL_TOKENS = (
    "transaction week",
    "transaction month",
    "supplier code",
    "barcode",
    "sales",
    "order quantity gross",
    "qty sellable",
    "tsin",
    "selling price",
)


@dataclass(frozen=True)
class CstFilePreview:
    filename: str
    signature: str
    column_count: int
    sheet_count: int
    unmappable: bool
    unmappable_reason: str | None = None


@dataclass(frozen=True)
class CstBatchGroupPreview:
    signature: str
    files: list[CstFilePreview]


def cst_layout_signature(headers: list[str]) -> str:
    norms = [str(h).strip().lower() for h in headers if str(h).strip()]
    norms.sort()
    return hashlib.sha256(",".join(norms).encode("utf-8")).hexdigest()[:16]


def _headers_look_cst(headers: list[str]) -> bool:
    lowered = {str(h).strip().lower() for h in headers if str(h).strip()}
    if not lowered:
        return False
    hits = 0
    for tok in _CST_SIGNAL_TOKENS:
        if any(tok in h or h == tok for h in lowered):
            hits += 1
    has_product = any(
        any(p in h for p in ("barcode", "supplier code", "tsin", "product")) for h in lowered
    )
    has_qty_or_period = any(
        any(p in h for p in ("sales", "quantity", "qty", "week", "month", "period")) for h in lowered
    )
    return hits >= 2 and has_product and has_qty_or_period


def normalized_cst_header_signature(
    filename: str, raw_bytes: bytes
) -> tuple[str, int, int, bool, str | None]:
    """Diagnose a file: header fingerprint + CST-mappable flag."""
    from app.services.imports.parsers.customer_sell_through_flat import (
        _normalize_text,
        _read_workbook_sheets,
    )

    try:
        sheets = _read_workbook_sheets(raw_bytes, filename)
    except Exception:
        return ("unmappable", 0, 0, True, "parse_error")

    sheet_count = len(sheets)
    if not sheets:
        return ("unmappable", 0, 0, True, "empty")

    best_headers: list[str] = []
    for _name, raw in sheets:
        if raw is None or raw.empty:
            continue
        headers = [str(_normalize_text(c) or "").strip() for c in raw.iloc[0].tolist()]
        if _headers_look_cst(headers):
            best_headers = headers
            break
        if len(headers) > len(best_headers):
            best_headers = headers

    if not best_headers:
        return ("unmappable", 0, sheet_count, True, "empty")
    if not _headers_look_cst(best_headers):
        return (
            cst_layout_signature(best_headers),
            len(best_headers),
            sheet_count,
            True,
            "no_cst_headers",
        )
    return (cst_layout_signature(best_headers), len(best_headers), sheet_count, False, None)


def propose_cst_batch_groups(
    files: list[tuple[str, bytes]],
) -> list[CstBatchGroupPreview]:
    """Group uploaded files by CST capability (read-only, no DB).

    All CST-capable files join one ``cst_capable`` group so one steward session covers
    multi-week Takealot-style batches. Unmappable files are listed separately.
    """
    previews: list[CstFilePreview] = []
    for filename, raw_bytes in files:
        sig, col_count, sheet_count, unmappable, reason = normalized_cst_header_signature(
            filename, raw_bytes
        )
        previews.append(
            CstFilePreview(
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
    groups: list[CstBatchGroupPreview] = []
    if capable:
        groups.append(CstBatchGroupPreview(signature=CST_CAPABLE_GROUP_SIGNATURE, files=capable))
    if unmappable_files:
        groups.append(
            CstBatchGroupPreview(signature=CST_UNMAPPABLE_GROUP_SIGNATURE, files=unmappable_files)
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


def create_cst_batch_job_sync(
    db: Session,
    *,
    source_id: int,
    filenames_and_bytes: list[tuple[str, bytes]],
    import_mode: str = "validate",
) -> ImportJob:
    """Create one CST import job with N raw files; run process sync."""
    if not filenames_and_bytes:
        raise ValueError("create_cst_batch_job_sync requires at least one file")

    source = db.scalar(
        select(SourceDefinition)
        .options(joinedload(SourceDefinition.import_template))
        .where(SourceDefinition.id == source_id)
    )
    if not source or not source.is_active:
        raise ValueError("Unknown or inactive source_id")
    tpl = source.import_template
    if not tpl or tpl.slug != CST_TEMPLATE_SLUG:
        raise ValueError("CST batch jobs require customer_sell_through source")

    filenames = [fn for fn, _ in filenames_and_bytes]
    # file_name must keep a real extension — pipeline read_tabular sniffs job.file_name.
    job = ImportJob(
        source_id=source_id,
        template_slug=tpl.slug,
        import_mode=import_mode,
        status="pending",
        stage="uploaded",
        file_name=filenames[0],
        content_type=None,
    )
    db.add(job)
    db.flush()

    sm = dict(job.staged_metadata or {})
    sm["cst_multi_file"] = len(filenames_and_bytes) > 1
    sm["cst_batch_filenames"] = filenames
    sm["cst_batch_display_name"] = _batch_job_display_name(filenames)
    sm.setdefault("report_structure_type", "flat")
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

    from app.ingestion.pipeline import process_import_job_sync

    process_import_job_sync(db, job.id)
    refreshed = db.get(ImportJob, job.id)
    if refreshed is None:
        raise RuntimeError("CST batch job missing after process")
    return refreshed


def batch_groups_preview_to_dict(groups: list[CstBatchGroupPreview]) -> list[dict[str, Any]]:
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


def get_cst_excluded_filenames(job: ImportJob) -> set[str]:
    sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = sm.get("cst_excluded_files")
    if not isinstance(raw, list):
        return set()
    return {str(x) for x in raw if str(x).strip()}


def get_cst_file_period_stamps(job: ImportJob) -> dict[str, str]:
    """filename → ISO date string steward override."""
    sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    raw = sm.get("cst_file_period_stamps")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        ks = str(k).strip()
        vs = str(v).strip() if v is not None else ""
        if ks and vs:
            out[ks] = vs[:10]
    return out
