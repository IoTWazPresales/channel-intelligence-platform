"""Distributor-token classifier for lineup customer-column tokens (Unit 6c / W1–W2).

A customer-column token that names a distributor means Open Channel + that distributor
on the line. Matching is exact on normalized name / distributor aliases after optional
structured remainder stripping — never fuzzy, never substring, never auto-create.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.imports.distributor_sales_inventory import _norm_key

# Structured remainder patterns (Warren lock Unit 6c STOP GATE Q1). Applied once each;
# remainder must exact-match dim_distributor.name or approved distributor alias.
_PREFIXES = (
    "sadc - ",
    "channel - ",
    "channel ",
)
_SUFFIXES = (
    " distribution",
)


@dataclass(frozen=True)
class DistributorTokenMatch:
    distributor_id: int
    matched_via: str  # "exact_name" | "exact_alias" | "stripped_name" | "stripped_alias"
    matched_key: str


def distributor_match_keys(norm_token: str) -> list[str]:
    """Return candidate exact keys: full token first, then one structured strip."""
    nt = _norm_key(norm_token)
    if not nt:
        return []
    keys = [nt]
    for pref in _PREFIXES:
        if nt.startswith(pref) and len(nt) > len(pref):
            keys.append(nt[len(pref) :].strip())
            break
    else:
        for suf in _SUFFIXES:
            if nt.endswith(suf) and len(nt) > len(suf):
                keys.append(nt[: -len(suf)].strip())
                break
    # de-dup preserve order
    out: list[str] = []
    for k in keys:
        if k and k not in out:
            out.append(k)
    return out


def match_distributor_token(
    norm_token: str,
    *,
    name_to_id: dict[str, int],
    alias_to_id: dict[str, int],
) -> DistributorTokenMatch | None:
    """Exact match only. ``name_to_id`` / ``alias_to_id`` keys must already be `_norm_key`d."""
    keys = distributor_match_keys(norm_token)
    if not keys:
        return None
    full = keys[0]
    # Full token first
    if full in name_to_id:
        return DistributorTokenMatch(name_to_id[full], "exact_name", full)
    if full in alias_to_id:
        return DistributorTokenMatch(alias_to_id[full], "exact_alias", full)
    # Structured remainder
    for k in keys[1:]:
        if k in name_to_id:
            return DistributorTokenMatch(name_to_id[k], "stripped_name", k)
        if k in alias_to_id:
            return DistributorTokenMatch(alias_to_id[k], "stripped_alias", k)
    return None
