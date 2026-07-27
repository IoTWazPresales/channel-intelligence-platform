"""Per-file DSI distributor identity: banner sniff, confirm, row stamp.

Distributor may come from a mapped column OR a confirmed per-file stamp
(ASUS weekly sellout puts Company Name in the form banner, not a table column).
Built on ``dsi_file_stamp`` shared core.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.services.imports.dsi_file_stamp import (
    apply_stamps_to_column,
    file_maps_canonical_target,
    get_file_stamps,
    included_batch_filenames,
    iter_raw_files_for_propose,
    load_banner_grid,
    set_file_stamps,
    sniff_banner_label_value,
    stamps_covering_files,
)

DSI_FILE_DISTRIBUTORS_KEY = "dsi_file_distributors"

_COMPANY_LABELS = ("company name", "company", "distributor name", "distributor")


def sniff_banner_company_token_from_grid(grid: pd.DataFrame) -> str | None:
    return sniff_banner_label_value(grid, _COMPANY_LABELS)


def sniff_banner_company_token(filename: str, raw_bytes: bytes, *, header_row: int = 19) -> str | None:
    grid = load_banner_grid(filename, raw_bytes, header_row=header_row)
    return sniff_banner_company_token_from_grid(grid) if grid is not None else None


def get_dsi_file_distributors(job: ImportJob) -> dict[str, dict[str, Any]]:
    return get_file_stamps(job, DSI_FILE_DISTRIBUTORS_KEY)


def set_dsi_file_distributors(job: ImportJob, stamps: dict[str, dict[str, Any]]) -> None:
    set_file_stamps(job, DSI_FILE_DISTRIBUTORS_KEY, stamps)


def _stamp_ready(st: dict[str, Any]) -> bool:
    if not st.get("confirmed"):
        return False
    if st.get("distributor_id") is not None:
        return True
    return bool(str(st.get("token") or "").strip())


def file_has_mapped_distributor_column(job: ImportJob, filename: str) -> bool:
    return file_maps_canonical_target(job, filename, "distributor_token")


def file_distributors_all_confirmed(job: ImportJob) -> bool:
    return stamps_covering_files(
        job,
        metadata_key=DSI_FILE_DISTRIBUTORS_KEY,
        is_ready=_stamp_ready,
        column_satisfies=file_has_mapped_distributor_column,
    )


def distributor_identity_satisfied(
    job: ImportJob,
    mapping: dict[str, str],
    *,
    mapping_key: str | None = None,
) -> bool:
    if "distributor_token" in set(mapping.values()):
        return True
    stamps = get_dsi_file_distributors(job)
    if mapping_key and "::" in mapping_key:
        fname = mapping_key.split("::", 1)[0]
        return _stamp_ready(stamps.get(fname) or {})
    files = included_batch_filenames(job)
    if len(files) == 1:
        return _stamp_ready(stamps.get(files[0]) or {})
    return file_distributors_all_confirmed(job)


def propose_file_distributors_for_job(db: Session, job: ImportJob) -> dict[str, dict[str, Any]]:
    existing = get_dsi_file_distributors(job)
    stamps: dict[str, dict[str, Any]] = dict(existing)
    source_id = int(job.source_id) if job.source_id is not None else None

    for filename, data, header_row in iter_raw_files_for_propose(db, job):
        if filename in stamps and stamps[filename].get("confirmed"):
            continue
        token = sniff_banner_company_token(filename, data, header_row=header_row)
        entry: dict[str, Any] = {
            "token": token,
            "reason": "banner_company_name" if token else "missing",
            "confirmed": False,
            "distributor_id": None,
            "distributor_name": None,
        }
        if token and source_id is not None:
            try:
                from app.services.imports.distributor_sales_inventory import _resolve_distributor_strict

                did, err = _resolve_distributor_strict(db, token, source_id)
                if did is not None and not err:
                    from app.models.dimensions import DimDistributor

                    dist = db.get(DimDistributor, int(did))
                    entry["distributor_id"] = int(did)
                    entry["distributor_name"] = dist.name if dist else None
                    entry["reason"] = "banner_company_name_resolved"
            except Exception:
                pass
        prev = existing.get(filename) or {}
        if prev.get("confirmed"):
            entry = dict(prev)
        stamps[filename] = entry

    set_dsi_file_distributors(job, stamps)
    return stamps


def confirm_dsi_file_distributor(
    db: Session,
    job: ImportJob,
    *,
    filename: str,
    distributor_id: int | None = None,
    confirm: bool = True,
    clear: bool = False,
) -> dict[str, dict[str, Any]]:
    from app.models.dimensions import DimDistributor

    stamps = get_dsi_file_distributors(job)
    name = str(filename).strip()
    if not name:
        raise ValueError("filename is required")
    if clear:
        stamps[name] = {
            "token": None,
            "reason": "cleared",
            "confirmed": False,
            "distributor_id": None,
            "distributor_name": None,
        }
        set_dsi_file_distributors(job, stamps)
        db.add(job)
        db.commit()
        db.refresh(job)
        return stamps

    entry = dict(stamps.get(name) or {})
    if distributor_id is not None:
        dist = db.get(DimDistributor, int(distributor_id))
        if dist is None:
            raise ValueError(f"Unknown distributor_id={distributor_id}")
        entry["distributor_id"] = int(distributor_id)
        entry["distributor_name"] = dist.name
        entry["token"] = entry.get("token") or dist.code or dist.name
        entry["reason"] = entry.get("reason") or "steward_assigned"
    if confirm:
        if entry.get("distributor_id") is None and not str(entry.get("token") or "").strip():
            raise ValueError("Cannot confirm without distributor_id or token")
        entry["confirmed"] = True
    stamps[name] = entry
    set_dsi_file_distributors(job, stamps)
    db.add(job)
    db.commit()
    db.refresh(job)
    return stamps


def apply_file_distributor_stamps_to_dataframe(job: ImportJob, df: pd.DataFrame) -> pd.DataFrame:
    def _value(st: dict[str, Any]) -> str:
        return str(st.get("token") or st.get("distributor_name") or "").strip()

    return apply_stamps_to_column(
        job,
        df,
        metadata_key=DSI_FILE_DISTRIBUTORS_KEY,
        column="distributor_token",
        is_ready=_stamp_ready,
        value_from_stamp=_value,
    )


# Re-export for callers that imported included_batch_filenames from this module.
__all__ = [
    "DSI_FILE_DISTRIBUTORS_KEY",
    "apply_file_distributor_stamps_to_dataframe",
    "confirm_dsi_file_distributor",
    "distributor_identity_satisfied",
    "file_distributors_all_confirmed",
    "file_has_mapped_distributor_column",
    "get_dsi_file_distributors",
    "included_batch_filenames",
    "propose_file_distributors_for_job",
    "set_dsi_file_distributors",
    "sniff_banner_company_token",
    "sniff_banner_company_token_from_grid",
]
