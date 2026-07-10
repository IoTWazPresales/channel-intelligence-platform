"""Configurable archive layout for bulk lineup backfill (Spec C Step C).

Tenant-specific roots, folder segment conventions, and BU vocabulary are **config inputs** —
not hardcoded in detection logic. Default factory targets the ACZA Consumer archive.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# Default ACZA Consumer tenant BU tab/folder codes (Spec C §3.5 + archive inventory).
DEFAULT_ACZA_TENANT_BU_CODES: frozenset[str] = frozenset({"NB", "NR", "NV", "NX", "PF", "XB"})

_YEAR_RE = re.compile(r"^20\d{2}$")
_QUARTER_RE = re.compile(r"^Q[1-4]$", re.IGNORECASE)
_SHORT_QUARTER_RE = re.compile(r"^26Q[1-4]$", re.IGNORECASE)
_LINEUP_GLOB = ("*.xlsx", "*.xls", "*.xlsm")


@dataclass(frozen=True, slots=True)
class FolderConventionConfig:
    """Path segment roles relative to ``archive_root`` (outermost first).

    Example ACZA tree: ``{BU}/{year}/{quarter}/file.xlsx``.
    Irregular paths (``PF/Q2/file``, ``NV/2026/file``) are classified heuristically
    per segment — not every role is present on every file.
    """

    segment_roles: tuple[str, ...] = ("business_unit", "year", "quarter")
    business_unit_role: str = "business_unit"
    year_role: str = "year"
    quarter_role: str = "quarter"


@dataclass
class BackfillArchiveConfig:
    """Archive scan + metadata config consumed by the bulk backfill preview runner."""

    archive_roots: list[Path]
    folder_convention: FolderConventionConfig = field(default_factory=FolderConventionConfig)
    tenant_bu_codes: frozenset[str] = DEFAULT_ACZA_TENANT_BU_CODES
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
            "tenant_bu_codes": sorted(self.tenant_bu_codes),
            "extra_file_paths": [str(p) for p in self.extra_file_paths],
        }


def default_acza_consumer_config(
    archive_root: Path | str | None = None,
    *,
    extra_file_paths: list[Path | str] | None = None,
) -> BackfillArchiveConfig:
    """Factory for the local ASUS Consumer Product Lineup tree."""
    root = Path(
        archive_root
        or Path.home()
        / "OneDrive - ASUS"
        / "ACZA Consumer - Sales"
        / "Consumer PM Team"
        / "Product Lineup"
    )
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
    if upper in tenant_bu_codes:
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


def iter_archive_lineup_files(config: BackfillArchiveConfig) -> Iterator[dict[str, Any]]:
    """Yield file records: absolute path, relative path, folder_path, bytes-ready metadata."""
    seen: set[Path] = set()

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
            tenant_bu_codes=config.tenant_bu_codes,
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
