"""Contract for ``possible_duplicate_of`` hint objects (JSONB on mapping candidate context).

Phase A active bases are emitted by validate-time duplicate annotation.
Reserved bases and optional evidence keys are parse-safe for future Phase B work
without schema migration.
"""

from __future__ import annotations

from typing import Any

# --- Active match bases (may be written by annotate_dsi_customer_candidate_duplicates) ---
MATCH_BASIS_DEALER_GROUP_EXACT = "dealer_group_exact"
MATCH_BASIS_DEALER_GROUP_SIMILAR = "dealer_group_similar"
MATCH_BASIS_SOURCE_CUSTOMER_EXACT = "source_customer_exact"
MATCH_BASIS_SOURCE_CUSTOMER_SIMILAR = "source_customer_similar"
MATCH_BASIS_DEALER_GROUP_PREFIX_STEM = "dealer_group_prefix_stem"
MATCH_BASIS_DEALER_GROUP_SHARED_LABEL = "dealer_group_shared_label_different_counterparty"

MATCH_BASIS_ACTIVE: frozenset[str] = frozenset(
    {
        MATCH_BASIS_DEALER_GROUP_EXACT,
        MATCH_BASIS_DEALER_GROUP_SIMILAR,
        MATCH_BASIS_SOURCE_CUSTOMER_EXACT,
        MATCH_BASIS_SOURCE_CUSTOMER_SIMILAR,
        MATCH_BASIS_DEALER_GROUP_PREFIX_STEM,
        MATCH_BASIS_DEALER_GROUP_SHARED_LABEL,
    }
)

# --- Reserved for future phases (parse-safe; not emitted by current annotate path) ---
MATCH_BASIS_TEMPORAL_SAME_DISTI = "temporal_same_disti"
MATCH_BASIS_CROSS_DISTI = "cross_disti"

MATCH_BASIS_RESERVED: frozenset[str] = frozenset(
    {
        MATCH_BASIS_TEMPORAL_SAME_DISTI,
        MATCH_BASIS_CROSS_DISTI,
    }
)

MATCH_BASIS_KNOWN: frozenset[str] = MATCH_BASIS_ACTIVE | MATCH_BASIS_RESERVED

DUPLICATE_HINT_OPTIONAL_EVIDENCE_KEYS: tuple[str, ...] = (
    "matched_value",
    "matched_field",
    "dealer_group_norm",
    "source_customer_norm",
    "distributor_scope",
    "evidence_reason",
)


def is_known_match_basis(value: str | None) -> bool:
    return bool(value and value.strip() in MATCH_BASIS_KNOWN)


def is_reserved_match_basis(value: str | None) -> bool:
    return bool(value and value.strip() in MATCH_BASIS_RESERVED)


def _coerce_optional_str(value: Any, *, max_len: int = 512) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    t = value.strip()
    if not t:
        return None
    return t[:max_len]


def _coerce_distributor_scope(value: Any) -> list[int] | None:
    if value is None:
        return None
    if isinstance(value, list):
        out: list[int] = []
        for item in value:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out[:16] or None
    return None


def build_duplicate_hint_entry(
    *,
    normalized_key: str,
    similarity_score: float,
    match_basis: str | None = None,
    matched_value: str | None = None,
    matched_field: str | None = None,
    dealer_group_norm: str | None = None,
    source_customer_norm: str | None = None,
    distributor_scope: list[int] | None = None,
    evidence_reason: str | None = None,
) -> dict[str, Any]:
    """Build a backwards-compatible hint dict for ``context.possible_duplicate_of``."""
    entry: dict[str, Any] = {
        "normalized_key": (normalized_key or "").strip(),
        "similarity_score": round(float(similarity_score), 4),
    }
    basis = _coerce_optional_str(match_basis, max_len=64)
    if basis:
        entry["match_basis"] = basis
    mv = _coerce_optional_str(matched_value)
    if mv:
        entry["matched_value"] = mv
    mf = _coerce_optional_str(matched_field, max_len=64)
    if mf:
        entry["matched_field"] = mf
    dgn = _coerce_optional_str(dealer_group_norm)
    if dgn:
        entry["dealer_group_norm"] = dgn
    scn = _coerce_optional_str(source_customer_norm)
    if scn:
        entry["source_customer_norm"] = scn
    scope = _coerce_distributor_scope(distributor_scope)
    if scope:
        entry["distributor_scope"] = scope
    er = _coerce_optional_str(evidence_reason, max_len=256)
    if er:
        entry["evidence_reason"] = er
    return entry


def parse_duplicate_hint_entry(raw: Any) -> dict[str, Any] | None:
    """Parse a hint from context JSONB; unknown ``match_basis`` strings are preserved."""
    if isinstance(raw, str):
        nk = raw.strip()
        if not nk:
            return None
        return {"normalized_key": nk}
    if not isinstance(raw, dict):
        return None
    nk = str(raw.get("normalized_key") or "").strip()
    if not nk:
        return None
    out: dict[str, Any] = {"normalized_key": nk}
    score = raw.get("similarity_score")
    if score is not None:
        try:
            out["similarity_score"] = round(float(score), 4)
        except (TypeError, ValueError):
            pass
    basis = _coerce_optional_str(raw.get("match_basis"), max_len=64)
    if basis:
        out["match_basis"] = basis
    for key in DUPLICATE_HINT_OPTIONAL_EVIDENCE_KEYS:
        if key not in raw:
            continue
        if key == "distributor_scope":
            scope = _coerce_distributor_scope(raw.get(key))
            if scope:
                out[key] = scope
            continue
        val = _coerce_optional_str(raw.get(key), max_len=512 if key != "evidence_reason" else 256)
        if val:
            out[key] = val
    return out
