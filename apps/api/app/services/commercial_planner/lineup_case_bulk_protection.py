"""Bulk-automation protection for commercial lineup cases (BACKLOG-110/115 / Q-011).

A case is **selection-protected** (excluded from select-all) when ANY of:
  - commercial_status advanced beyond ``draft_imported``
  - it has ≥1 ``commercial_lineup_case_po`` link (steward-confirmed links)
  - the proposal is contested (D-033 competition status)
  - case id is in the optional tenant config set ``CIP_LINEUP_PROTECTED_CASE_IDS``

Service refuse (needs ``allow_protected=True``) uses the same reasons **except**
contested-only: D-033 FLAG≠BLOCK — contested stays annotation + select-all
exclusion; deliberate single-item apply remains unblocked without the override.

Config, never hardcoded id constants in call sites.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable

# Statuses that are still "pre-PO draft" for bulk-protection purposes.
_DRAFT_STATUSES: frozenset[str] = frozenset({"draft_imported"})


@dataclass(frozen=True)
class BulkProtection:
    """Explainable protection decision for one case / proposal."""

    reasons: tuple[str, ...]
    contested: bool = False

    @property
    def selection_protected(self) -> bool:
        """Exclude from select-all / bulk-automation sweeps."""
        return bool(self.reasons) or self.contested

    @property
    def requires_allow_protected(self) -> bool:
        """Service refuse unless ``allow_protected=True`` (contested alone does not)."""
        return bool(self.reasons)

    def as_dict(self) -> dict[str, Any]:
        return {
            "selection_protected": self.selection_protected,
            "requires_allow_protected": self.requires_allow_protected,
            "reasons": list(self.reasons),
            "contested": self.contested,
        }


def protected_lineup_case_ids_from_config() -> frozenset[int]:
    """Optional tenant exception set — env ``CIP_LINEUP_PROTECTED_CASE_IDS`` (comma ids)."""
    raw = os.environ.get("CIP_LINEUP_PROTECTED_CASE_IDS")
    if raw is None or str(raw).strip() == "":
        try:
            from app.core.config import get_settings

            settings = get_settings()
            raw = getattr(settings, "cip_lineup_protected_case_ids", None) or ""
        except Exception:
            raw = ""
    ids: set[int] = set()
    for part in str(raw).replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return frozenset(ids)


def evaluate_case_bulk_protection(
    *,
    case_id: int,
    commercial_status: str | None,
    po_link_count: int,
    competition_status: str | None = None,
    protected_ids: Iterable[int] | None = None,
) -> BulkProtection:
    """Property-based protection — no hardcoded survivor id list in the predicate."""
    reasons: list[str] = []
    status = (commercial_status or "").strip().lower()
    if status and status not in _DRAFT_STATUSES:
        reasons.append("status_advanced")
    if int(po_link_count or 0) > 0:
        reasons.append("confirmed_po_links")
    cfg = frozenset(protected_ids) if protected_ids is not None else protected_lineup_case_ids_from_config()
    if int(case_id) in cfg:
        reasons.append("tenant_protected_id")
    contested = (competition_status or "").strip().lower() == "contested"
    # Dedupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            ordered.append(r)
    return BulkProtection(reasons=tuple(ordered), contested=contested)


class CaseProtectedError(Exception):
    """Raised when linking a protected case without ``allow_protected=True``."""

    def __init__(self, case_id: int, protection: BulkProtection):
        self.case_id = case_id
        self.protection = protection
        reason_s = ",".join(protection.reasons) or "protected"
        super().__init__(
            f"Case {case_id} is protected from bulk automation ({reason_s}); "
            "pass allow_protected=True for deliberate single-item stewarding"
        )
