"""Per-file DSI inventory snapshot period: banner Application Date → Monday → confirm → stamp.

ASUS weekly inventory forms put ``Application Date`` = ``2026W26`` in the form banner,
not a table column. Twin of ``dsi_file_distributor`` on the shared ``dsi_file_stamp`` core.

No filename/AGP inference — banner only. ISO week resolves to Monday (platform coverage grain).
"""

from __future__ import annotations

from datetime import date, datetime
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
)
from app.services.imports.parsers.customer_sell_through_period import classify_period_header

DSI_FILE_SNAPSHOT_PERIODS_KEY = "dsi_file_snapshot_periods"

_APPLICATION_DATE_LABELS = (
    "application date",
    "as of",
    "as-of date",
    "as of date",
    "snapshot date",
    "inventory date",
    "week",
)


def sniff_banner_application_date_token_from_grid(grid: pd.DataFrame | None) -> str | None:
    return sniff_banner_label_value(grid, _APPLICATION_DATE_LABELS)


def sniff_banner_application_date_token(
    filename: str, raw_bytes: bytes, *, header_row: int = 19
) -> str | None:
    grid = load_banner_grid(filename, raw_bytes, header_row=header_row)
    return sniff_banner_application_date_token_from_grid(grid)


def resolve_snapshot_period_token(token: str | None) -> tuple[date | None, str]:
    """Parse banner token → (Monday date, reason_suffix)."""
    if not token or not str(token).strip():
        return None, "missing"
    kind, d, _ptype = classify_period_header(str(token).strip())
    if d is None:
        return None, "banner_unparsed"
    if kind in ("iso_week", "fiscal_week", "date", "month"):
        return d, "banner_application_date"
    return d, "banner_application_date"


def get_dsi_file_snapshot_periods(job: ImportJob) -> dict[str, dict[str, Any]]:
    return get_file_stamps(job, DSI_FILE_SNAPSHOT_PERIODS_KEY)


def set_dsi_file_snapshot_periods(job: ImportJob, stamps: dict[str, dict[str, Any]]) -> None:
    set_file_stamps(job, DSI_FILE_SNAPSHOT_PERIODS_KEY, stamps)


def _stamp_ready(st: dict[str, Any]) -> bool:
    if not st.get("confirmed"):
        return False
    return bool(str(st.get("resolved_date") or "").strip())


def file_needs_snapshot_period_stamp(job: ImportJob, filename: str) -> bool:
    """Inventory-bearing file with no snapshot_date column mapping."""
    if not file_maps_canonical_target(job, filename, "stock_on_hand"):
        return False
    if file_maps_canonical_target(job, filename, "snapshot_date"):
        return False
    return True


def file_has_mapped_snapshot_column(job: ImportJob, filename: str) -> bool:
    return file_maps_canonical_target(job, filename, "snapshot_date")


def file_snapshot_periods_all_confirmed(job: ImportJob) -> bool:
    """Every inventory file that needs a period stamp has a confirmed resolved date."""
    stamps = get_dsi_file_snapshot_periods(job)
    files = included_batch_filenames(job)
    needing = [f for f in files if file_needs_snapshot_period_stamp(job, f)]
    if not needing:
        return True
    for name in needing:
        if file_has_mapped_snapshot_column(job, name):
            continue
        if not _stamp_ready(stamps.get(name) or {}):
            return False
    return True


def snapshot_identity_satisfied(
    job: ImportJob,
    mapping: dict[str, str],
    *,
    mapping_key: str | None = None,
) -> bool:
    """True when this sheet's inventory period is satisfied by column or confirmed stamp."""
    vals = set(mapping.values())
    if "snapshot_date" in vals:
        return True
    if "stock_on_hand" not in vals:
        # Sell-out-only sheet — snapshot stamp not required for this mapping.
        return False
    stamps = get_dsi_file_snapshot_periods(job)
    if mapping_key and "::" in mapping_key:
        fname = mapping_key.split("::", 1)[0]
        return _stamp_ready(stamps.get(fname) or {})
    files = included_batch_filenames(job)
    if len(files) == 1:
        return _stamp_ready(stamps.get(files[0]) or {})
    return file_snapshot_periods_all_confirmed(job)


def propose_file_snapshot_periods_for_job(db: Session, job: ImportJob) -> dict[str, dict[str, Any]]:
    existing = get_dsi_file_snapshot_periods(job)
    stamps: dict[str, dict[str, Any]] = dict(existing)

    for filename, data, header_row in iter_raw_files_for_propose(db, job):
        if filename in stamps and stamps[filename].get("confirmed"):
            continue
        token = sniff_banner_application_date_token(filename, data, header_row=header_row)
        resolved, reason = resolve_snapshot_period_token(token)
        entry: dict[str, Any] = {
            "token": token,
            "resolved_date": resolved.isoformat() if resolved else None,
            "reason": reason if token else "missing",
            "confirmed": False,
            "source": "banner",
        }
        prev = existing.get(filename) or {}
        if prev.get("confirmed"):
            entry = dict(prev)
        stamps[filename] = entry

    set_dsi_file_snapshot_periods(job, stamps)
    return stamps


def confirm_dsi_file_snapshot_period(
    db: Session,
    job: ImportJob,
    *,
    filename: str,
    confirm: bool = True,
    clear: bool = False,
    resolved_date: str | date | None = None,
    confirm_all_sniffed: bool = False,
) -> dict[str, dict[str, Any]]:
    stamps = get_dsi_file_snapshot_periods(job)

    if confirm_all_sniffed:
        for name, st in list(stamps.items()):
            if st.get("confirmed"):
                continue
            if not str(st.get("resolved_date") or "").strip():
                continue
            entry = dict(st)
            entry["confirmed"] = True
            stamps[name] = entry
        set_dsi_file_snapshot_periods(job, stamps)
        db.add(job)
        db.commit()
        db.refresh(job)
        return stamps

    name = str(filename).strip()
    if not name:
        raise ValueError("filename is required")
    if clear:
        stamps[name] = {
            "token": None,
            "resolved_date": None,
            "reason": "cleared",
            "confirmed": False,
            "source": "cleared",
        }
        set_dsi_file_snapshot_periods(job, stamps)
        db.add(job)
        db.commit()
        db.refresh(job)
        return stamps

    entry = dict(stamps.get(name) or {})
    if resolved_date is not None:
        if isinstance(resolved_date, date):
            d = resolved_date
        else:
            try:
                d = datetime.strptime(str(resolved_date).strip()[:10], "%Y-%m-%d").date()
            except ValueError as exc:
                raise ValueError("resolved_date must be YYYY-MM-DD") from exc
        entry["resolved_date"] = d.isoformat()
        entry["reason"] = entry.get("reason") or "steward_override"
        entry["source"] = "steward_override"
        if not entry.get("token"):
            entry["token"] = d.isoformat()
    if confirm:
        if not str(entry.get("resolved_date") or "").strip():
            raise ValueError("Cannot confirm without resolved_date")
        entry["confirmed"] = True
    stamps[name] = entry
    set_dsi_file_snapshot_periods(job, stamps)
    db.add(job)
    db.commit()
    db.refresh(job)
    return stamps


def apply_file_snapshot_stamps_to_dataframe(job: ImportJob, df: pd.DataFrame) -> pd.DataFrame:
    def _value(st: dict[str, Any]) -> str:
        return str(st.get("resolved_date") or "").strip()

    return apply_stamps_to_column(
        job,
        df,
        metadata_key=DSI_FILE_SNAPSHOT_PERIODS_KEY,
        column="snapshot_date",
        is_ready=_stamp_ready,
        value_from_stamp=_value,
    )
