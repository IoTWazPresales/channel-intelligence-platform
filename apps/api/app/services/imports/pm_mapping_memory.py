"""Source-scoped learned column mappings for Product Master (confirmed saves only)."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.ingestion import SourceDefinition
from app.services.imports.pm_field_catalog import normalize_pm_mapping_target


MEMORY_SCHEMA_VERSION = "1"
MAPPING_PROFILE_KEY = "mapping_profile"
# D-0060: this business maps column sets by product line (tenant_column_grain default).
DEFAULT_COLUMN_GRAIN = "product_line"


def tenant_column_grain_sync(db: Session, tenant_id: str | None) -> str:
    """The tenant's column-set axis (tenant_column_grain), product_line when unset."""
    tid = (tenant_id or "").strip()
    if not tid:
        return DEFAULT_COLUMN_GRAIN
    from app.models.product_line_access import TenantColumnGrain

    row = db.get(TenantColumnGrain, tid)
    grain = (getattr(row, "grain", None) or "").strip() if row is not None else ""
    return grain or DEFAULT_COLUMN_GRAIN

PARITY_TARGETS: tuple[str, ...] = (
    "technical_product_id",  # item / material code
    "barcode_ean",  # EAN/UPC
    "market_sku",  # sales model
)


def norm_header_key(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (h or "").strip().lower()).strip("_")


def load_by_header_norm(
    source: Any,
    product_line: str | None = None,
    *,
    grain: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Return header_norm → {target|disposition, confirmations}.

    product_line overlays stay in by_product_line. Another admin-set grain
    overlays from by_grain. Parity targets keep source-wide mappings unless
    that profile maps the header.
    """
    raw = getattr(source, "column_mapping_memory", None)
    if not raw or not isinstance(raw, dict):
        return {}
    bh = dict(raw.get("by_header_norm") or {}) if isinstance(raw.get("by_header_norm"), dict) else {}
    line = (product_line or "").strip()
    if not line:
        return bh
    axis = (grain or "product_line").strip() or "product_line"
    profile = raw.get(MAPPING_PROFILE_KEY) if isinstance(raw.get(MAPPING_PROFILE_KEY), dict) else {}
    if axis == "product_line":
        bucket = profile.get("by_product_line") if isinstance(profile.get("by_product_line"), dict) else {}
        line_root = bucket.get(line) if isinstance(bucket.get(line), dict) else {}
    else:
        by_grain = profile.get("by_grain") if isinstance(profile.get("by_grain"), dict) else {}
        axis_bucket = by_grain.get(axis) if isinstance(by_grain.get(axis), dict) else {}
        line_root = axis_bucket.get(line) if isinstance(axis_bucket.get(line), dict) else {}
    line_bh = line_root.get("by_header_norm") if isinstance(line_root.get("by_header_norm"), dict) else {}
    if not isinstance(line_bh, dict):
        return bh
    return {**bh, **line_bh}


def merge_memory_from_pm_save(
    db: Session,
    *,
    source_id: int,
    mapping_decisions: dict[str, Any],
    product_line: str | None = None,
    grain: str | None = None,
) -> None:
    """Upsert learned mappings after a successful Product Master mapping save."""
    src = db.get(SourceDefinition, source_id)
    if src is None:
        return

    root: dict[str, Any] = dict(src.column_mapping_memory or {})
    line = (product_line or "").strip()
    axis = (grain or "product_line").strip() or "product_line"
    if line:
        profile = dict(root.get(MAPPING_PROFILE_KEY) or {})
        if axis == "product_line":
            by_line = dict(profile.get("by_product_line") or {})
            line_root = dict(by_line.get(line) or {})
        else:
            by_grain = dict(profile.get("by_grain") or {})
            axis_bucket = dict(by_grain.get(axis) or {})
            line_root = dict(axis_bucket.get(line) or {})
        bh: dict[str, Any] = dict(line_root.get("by_header_norm") or {})
    else:
        bh = dict(root.get("by_header_norm") or {})

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

    if line:
        profile = dict(root.get(MAPPING_PROFILE_KEY) or {})
        if axis == "product_line":
            by_line = dict(profile.get("by_product_line") or {})
            line_root = dict(by_line.get(line) or {})
            line_root["by_header_norm"] = bh
            by_line[line] = line_root
            profile["by_product_line"] = by_line
        else:
            by_grain = dict(profile.get("by_grain") or {})
            axis_bucket = dict(by_grain.get(axis) or {})
            line_root = dict(axis_bucket.get(line) or {})
            line_root["by_header_norm"] = bh
            axis_bucket[line] = line_root
            by_grain[axis] = axis_bucket
            profile["by_grain"] = by_grain
        root[MAPPING_PROFILE_KEY] = profile
    else:
        root["by_header_norm"] = bh
    root["schema_version"] = MEMORY_SCHEMA_VERSION
    src.column_mapping_memory = root
    db.add(src)


def headers_parity_first(headers: list[str], header_memory: dict[str, dict[str, Any]]) -> list[str]:
    """Feed suggest_pm_mapping so item/material, then EAN/UPC, then sales model win used_targets."""
    buckets: dict[str, list[str]] = {t: [] for t in PARITY_TARGETS}
    rest: list[str] = []
    for h in headers:
        nh = norm_header_key(h)
        row = header_memory.get(nh) if isinstance(header_memory.get(nh), dict) else None
        tgt = (row or {}).get("target")
        if tgt in buckets:
            buckets[str(tgt)].append(h)
        else:
            rest.append(h)
    ordered: list[str] = []
    for t in PARITY_TARGETS:
        ordered.extend(buckets[t])
    ordered.extend(rest)
    return ordered
