"""Source-scoped learned column mappings for Product Master (confirmed saves only)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.ingestion import SourceDefinition
from app.services.imports.pm_field_catalog import normalize_pm_mapping_target


MEMORY_SCHEMA_VERSION = "1"


def norm_header_key(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (h or "").strip().lower()).strip("_")


def load_by_header_norm(source: Any) -> dict[str, dict[str, Any]]:
    """Return header_norm → {target|disposition, confirmations}."""
    raw = getattr(source, "column_mapping_memory", None)
    if not raw or not isinstance(raw, dict):
        return {}
    bh = raw.get("by_header_norm")
    return bh if isinstance(bh, dict) else {}


def merge_memory_from_pm_save(db: Session, *, source_id: int, mapping_decisions: dict[str, Any]) -> None:
    """Upsert learned mappings after a successful Product Master mapping save."""
    src = db.get(SourceDefinition, source_id)
    if src is None:
        return

    root: dict[str, Any] = dict(src.column_mapping_memory or {})
    bh: dict[str, Any] = dict(root.get("by_header_norm") or {})

    for header, meta in mapping_decisions.items():
        if not isinstance(meta, dict):
            continue
        nh = norm_header_key(str(header))
        if not nh:
            continue
        prev = bh.get(nh) if isinstance(bh.get(nh), dict) else {}
        tgt = meta.get("target")
        disp = meta.get("disposition")

        if tgt and str(tgt).strip():
            nt = normalize_pm_mapping_target(str(tgt))
            if nt:
                bh[nh] = {
                    "target": nt,
                    "confirmations": int(prev.get("confirmations", 0)) + 1,
                }
        elif disp == "stage_raw":
            bh[nh] = {
                "disposition": "stage_raw",
                "confirmations": int(prev.get("confirmations", 0)) + 1,
            }
        elif disp == "ignore":
            bh[nh] = {
                "disposition": "ignore",
                "confirmations": int(prev.get("confirmations", 0)) + 1,
            }
        elif disp == "attribute_candidate":
            bh[nh] = {
                "disposition": "attribute_candidate",
                "confirmations": int(prev.get("confirmations", 0)) + 1,
            }

    root["by_header_norm"] = bh
    root["schema_version"] = MEMORY_SCHEMA_VERSION
    src.column_mapping_memory = root
    db.add(src)
