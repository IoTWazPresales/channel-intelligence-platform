"""Configurable archive layout for bulk lineup backfill (Spec C Step C).

Tenant-specific roots, folder segment conventions, and BU vocabulary are **config inputs** —
not hardcoded in detection logic. The archive root is always supplied by the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

_YEAR_RE = re.compile(r"^20\d{2}$")
_QUARTER_RE = re.compile(r"^Q[1-4]$", re.IGNORECASE)
_SHORT_QUARTER_RE = re.compile(r"^\d{2}Q[1-4]$", re.IGNORECASE)
_LINEUP_GLOB = ("*.xlsx", "*.xls", "*.xlsm")


@dataclass(frozen=True, slots=True)
class FolderConventionConfig:
    """Path segment roles relative to ``archive_root`` (outermost first).

    Example tree: ``{BU}/{year}/{quarter}/file.xlsx``.
    Irregular paths (``PF/Q2/file``, ``NV/2026/file``) are classified heuristically
    per segment — not every role is present on every file.
    """

    segment_roles: tuple[str, ...] = ("business_unit", "year", "quarter")
    business_unit_role: str = "business_unit"
    year_role: str = "year"
    quarter_role: str = "quarter"


@dataclass
class BackfillArchiveConfig:
    """Archive scan + metadata config consumed by the bulk backfill preview runner.

    ``tenant_bu_codes`` is an optional override. When unset, callers pass the sellable
    product-line codes (``app.services.catalog.product_lines.sellable_line_codes``, D-g).
    """

    archive_roots: list[Path]
    folder_convention: FolderConventionConfig = field(default_factory=FolderConventionConfig)
    tenant_bu_codes: frozenset[str] | None = None
    extra_file_paths: list[Path] = field(default_factory=list)
    exclude_name_substrings: tuple[str, ...] = (
        "do not use",
        "previous q",
        "kept as reference",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "archive_roots": [str(p) for p in self.archive_roots],
            "folder_convention": {
                "segment_roles": list(self.folder_convention.segment_roles),
            },
            "tenant_bu_codes": sorted(self.tenant_bu_codes) if self.tenant_bu_codes is not None else None,
            "extra_file_paths": [str(p) for p in self.extra_file_paths],
        }


def archive_config_for_root(
    archive_root: Path | str,
    *,
    extra_file_paths: list[Path | str] | None = None,
) -> BackfillArchiveConfig:
    """Config for one lineup archive root. The root is tenant data and must be given."""
    if archive_root is None or not str(archive_root).strip():
        raise ValueError("archive_root is required (no default archive location)")
    root = Path(archive_root)
    extras = [Path(p) for p in (extra_file_paths or [])]
    return BackfillArchiveConfig(
        archive_roots=[root],
        extra_file_paths=extras,
    )


def _classify_segment(segment: str, tenant_bu_codes: frozenset[str]) -> str | None:
    text = segment.strip()
    if not text:
        return None
    upper = text.upper()
    if any(upper == str(code).strip().upper() for code in tenant_bu_codes):
        return "business_unit"
    if _YEAR_RE.match(text):
        return "year"
    if _QUARTER_RE.match(text) or _SHORT_QUARTER_RE.match(text):
        return "quarter"
    return None


def parse_archive_relative_path(
    relative: Path,
    *,
    tenant_bu_codes: frozenset[str],
    convention: FolderConventionConfig | None = None,
) -> dict[str, Any]:
    """Derive BU/year/quarter + synthetic ``folder_path`` for layered period/BU inference."""
    _ = convention  # reserved for alternate convention shapes
    parts = list(relative.parts[:-1]) if relative.name else list(relative.parts)
    found: dict[str, str] = {}
    for part in parts:
        role = _classify_segment(part, tenant_bu_codes)
        if role and role not in found:
            found[role] = part

    bu = found.get("business_unit")
    year = found.get("year")
    quarter = found.get("quarter")
    if quarter and _SHORT_QUARTER_RE.match(quarter):
        # 26Q1 → Q1 for folder_path consumers
        quarter = f"Q{quarter[-1]}"

    segments: list[str] = []
    if bu:
        segments.append(bu)
    if year:
        segments.append(year)
    if quarter:
        segments.append(quarter.upper() if quarter.upper().startswith("Q") else quarter)

    folder_path = "\\".join(segments) if segments else None
    return {
        "relative_path": str(relative).replace("/", "\\"),
        "business_unit": bu,
        "year": year,
        "quarter": quarter,
        "folder_path": folder_path,
        "path_segments": parts,
    }


def iter_archive_lineup_files(
    config: BackfillArchiveConfig,
    *,
    sellable_line_codes: frozenset[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield file records: absolute path, relative path, folder_path, bytes-ready metadata.

    BU folder segments match ``config.tenant_bu_codes`` when set, else ``sellable_line_codes``.
    """
    seen: set[Path] = set()
    bu_codes = config.tenant_bu_codes if config.tenant_bu_codes is not None else (sellable_line_codes or frozenset())

    def _maybe_yield(path: Path, *, root: Path | None) -> Iterator[dict[str, Any]]:
        path = path.resolve()
        if path in seen or not path.is_file():
            return
        name_lower = path.name.lower()
        if any(sub in name_lower for sub in config.exclude_name_substrings):
            return
        seen.add(path)
        if root is not None:
            try:
                relative = path.relative_to(root)
            except ValueError:
                relative = Path(path.name)
        else:
            relative = Path(path.name)
        meta = parse_archive_relative_path(
            relative,
            tenant_bu_codes=bu_codes,
            convention=config.folder_convention,
        )
        yield {
            "absolute_path": str(path),
            "filename": path.name,
            "folder_path": meta.get("folder_path"),
            "archive_meta": meta,
        }

    for root in config.archive_roots:
        root = root.resolve()
        if not root.exists():
            continue
        for pattern in _LINEUP_GLOB:
            for path in sorted(root.rglob(pattern)):
                yield from _maybe_yield(path, root=root)

    for extra in config.extra_file_paths:
        yield from _maybe_yield(Path(extra), root=None)
