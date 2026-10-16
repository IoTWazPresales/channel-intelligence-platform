"""Carry the former sell-through sources over to customer layouts (N-0111, Warren 2026-10-16).

A sell-through source used to be what a user picked. Now the upload picks a reporting customer and
the only per-customer configuration is the column layout. For every customer sell-through source:

* the source's **applied jobs** (stage ``loaded``) on a customer that is ticked as a reporting
  customer become saved layouts of that customer. The layout is read from the job exactly as it
  loaded: the stored ``field_mapping`` is kept as it is, the headers come from the job's stored file
  (the same header sniffing the upload uses), the structure from the job. Two jobs with the same
  header set give one layout.
* every source is then hidden (``source_definition.is_hidden``), so no source is ever offered.
  Nothing is deleted: jobs, files, facts and the source rows stay, and un-hiding a source is one
  column.

``plan`` reads only. ``apply`` writes layouts and the hide flag, and running it again changes nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.dimensions import DimCustomer
from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.imports.cst_layouts import (
    ANCHOR_SOURCE_CODE,
    CST_TEMPLATE_SLUG,
    DEFAULT_STRUCTURE,
    cst_template_expected_columns,
    find_matching_layout,
    layout_signature,
    list_reporting_customers,
    meaningful_headers,
    save_layout,
    sniff_columns,
)
from app.services.merge_redirect import follow_customer_merge_redirect_sync
from app.storage.local import get_storage_backend


@dataclass
class LayoutCandidate:
    customer_id: int
    name: str
    columns: list[str]
    field_mapping: dict[str, str]
    structure: str
    source_id: int
    job_id: int
    jobs: list[int] = field(default_factory=list)
    note: str = ""


@dataclass
class SourceRow:
    source_id: int
    slug: str
    customer_id: int | None
    customer_name: str
    applied_jobs: int
    outcome: str = ""
    layouts: list[str] = field(default_factory=list)
    already_hidden: bool = False


def _job_columns(db: Session, job: ImportJob, expected: dict[str, Any]) -> tuple[list[str] | None, str]:
    """Header set of a loaded job: from its stored file (as the upload reads it), else its inferred schema."""
    raws = list(
        db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job.id).order_by(RawFileMetadata.id)).all()
    )
    mapping = dict(job.field_mapping or {})
    if raws:
        try:
            data = get_storage_backend().read(raws[0].storage_key)
            info = sniff_columns(os.path.basename(raws[0].storage_key) or job.file_name, data, expected, mapping)
            if info is not None:
                return info["columns"], "stored file"
        except (OSError, NotImplementedError):
            pass
    schema = job.inferred_schema if isinstance(job.inferred_schema, dict) else {}
    cols = [str(c.get("name")) for c in (schema.get("columns") or []) if isinstance(c, dict) and c.get("name")]
    return (cols or None), "inferred schema"


def _stem(name: str) -> str:
    return os.path.splitext(os.path.basename(name or ""))[0].strip() or "file"


def plan_source_migration(db: Session) -> tuple[list[SourceRow], list[LayoutCandidate]]:
    expected = cst_template_expected_columns(db)
    reporting = {c["id"] for c in list_reporting_customers(db)}
    sources = list(
        db.scalars(
            select(SourceDefinition)
            .options(joinedload(SourceDefinition.import_template))
            .where(SourceDefinition.code != ANCHOR_SOURCE_CODE)
            .order_by(SourceDefinition.id)
        ).unique()
    )
    sources = [s for s in sources if s.import_template is not None and s.import_template.slug == CST_TEMPLATE_SLUG]

    rows: list[SourceRow] = []
    candidates: dict[tuple[int, str], LayoutCandidate] = {}
    for src in sources:
        tmpl = src.expected_template if isinstance(src.expected_template, dict) else {}
        raw_cid = tmpl.get("customer_id")
        cid = follow_customer_merge_redirect_sync(db, int(raw_cid)) if raw_cid is not None else None
        cust = db.get(DimCustomer, cid) if cid is not None else None
        applied = list(
            db.scalars(
                select(ImportJob)
                .where(ImportJob.source_id == src.id, ImportJob.stage == "loaded")
                .order_by(ImportJob.id)
            ).all()
        )
        row = SourceRow(
            source_id=int(src.id),
            slug=src.code,
            customer_id=cid,
            customer_name=cust.name if cust is not None else "(none)",
            applied_jobs=len(applied),
            already_hidden=bool(src.is_hidden),
        )
        rows.append(row)
        if not applied:
            row.outcome = "hidden (no applied jobs)"
            continue
        if cid is None or cid not in reporting:
            row.outcome = "hidden (applied jobs, but the customer is not ticked as a reporting customer: no layout)"
            continue
        made, same = [], []
        for job in applied:
            columns, how = _job_columns(db, job, expected)
            if not columns or not job.field_mapping:
                continue
            sig = layout_signature(columns)
            meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
            structure = str(meta.get("report_structure_type") or tmpl.get("report_structure_type") or DEFAULT_STRUCTURE)
            key = (int(cid), sig)
            cand = candidates.get(key)
            if cand is None:
                candidates[key] = LayoutCandidate(
                    customer_id=int(cid),
                    name=f"Imported layout - {_stem(job.file_name)}",
                    columns=columns,
                    field_mapping=dict(job.field_mapping),
                    structure=structure,
                    source_id=int(src.id),
                    job_id=int(job.id),
                    jobs=[int(job.id)],
                    note=f"headers from {how}",
                )
                made.append(candidates[key].name)
            else:
                cand.jobs.append(int(job.id))
                if dict(job.field_mapping) != cand.field_mapping or structure != cand.structure:
                    # The job that loaded last is the mapping that works today; the earlier one is noted.
                    cand.note += f"; job {job.id} replaces job {cand.job_id} (its mapping or structure differed)"
                    cand.field_mapping = dict(job.field_mapping)
                    cand.structure = structure
                    cand.job_id = int(job.id)
                if cand.source_id != int(src.id):
                    same.append(cand.name)
        row.layouts = sorted(set(made))
        if made:
            row.outcome = f"layout saved: {', '.join(sorted(set(made)))}; source hidden"
        elif same:
            row.outcome = f"same header set as layout {', '.join(sorted(set(same)))}; source hidden"
        else:
            row.outcome = "hidden (applied jobs had no readable header set or mapping: no layout)"
    return rows, list(candidates.values())


def apply_source_migration(db: Session) -> dict[str, Any]:
    """Write the layouts and hide the sources. Safe to run twice."""
    rows, candidates = plan_source_migration(db)
    created = existing = 0
    for cand in candidates:
        if find_matching_layout(db, cand.customer_id, cand.columns) is not None:
            existing += 1
            continue
        _lay, was_created = save_layout(
            db,
            customer_id=cand.customer_id,
            name=cand.name,
            columns=cand.columns,
            field_mapping=cand.field_mapping,
            report_structure_type=cand.structure,
            origin="migrated_source",
            origin_source_id=cand.source_id,
            origin_import_job_id=cand.job_id,
        )
        created += 1 if was_created else 0
        existing += 0 if was_created else 1
    hidden = 0
    for row in rows:
        src = db.get(SourceDefinition, row.source_id)
        if src is not None and not src.is_hidden:
            src.is_hidden = True
            db.add(src)
            hidden += 1
    db.commit()
    return {"layouts_created": created, "layouts_already_there": existing, "sources_hidden": hidden}


def headers_of(candidate: LayoutCandidate) -> list[str]:
    return meaningful_headers(candidate.columns)
