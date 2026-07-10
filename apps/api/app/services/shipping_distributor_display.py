"""Display-name-first distributor labels for shipping read models (CPOR Batch 3).

Read/serialization only — never mutates dim_distributor. TMP provisionals
(``TMP-DIST-*``) prefer a human name; when ``name`` equals the TMP code, fall
through to bill_to / ship_to / resolution token / suggested token name.
"""

from __future__ import annotations

from typing import Any

from app.services.imports.shipment_evidence_candidate_names import (
    suggested_name_for_distributor_token,
)

TMP_DIST_PREFIX = "TMP-DIST"


def is_tmp_distributor_code(code: str | None) -> bool:
    return (code or "").strip().upper().startswith(TMP_DIST_PREFIX)


def name_looks_like_tmp_code(name: str | None, code: str | None) -> bool:
    """True when stored name is empty or is just the TMP code (common mint fallback)."""
    dn = (name or "").strip()
    dc = (code or "").strip()
    if not dn:
        return True
    if is_tmp_distributor_code(dc) and dn.upper() == dc.upper():
        return True
    if is_tmp_distributor_code(dn):
        return True
    return False


def resolve_distributor_display(
    *,
    distributor_name: str | None,
    distributor_code: str | None,
    bill_to_raw: str | None = None,
    ship_to_raw: str | None = None,
    distributor_resolution_token: str | None = None,
) -> tuple[str, bool]:
    """Return (display_label, is_provisional).

    Preference order for provisional / TMP-like rows:
    1. Human ``distributor_name`` (when it is not the TMP code itself)
    2. ``bill_to_raw`` / ``ship_to_raw``
    3. Suggested name from ``distributor_resolution_token``
    4. Raw resolution token
    5. TMP code (last resort)

    For non-TMP rows: name, else non-TMP code, else evidence fields, else "—".
    """
    dn = (distributor_name or "").strip()
    dc = (distributor_code or "").strip()
    provisional = is_tmp_distributor_code(dc) or is_tmp_distributor_code(dn)

    if dn and not name_looks_like_tmp_code(dn, dc):
        return dn[:240], provisional

    if dc and not is_tmp_distributor_code(dc):
        return dc[:240], False

    br = (bill_to_raw or "").strip()
    if br:
        return br[:240], provisional

    sr = (ship_to_raw or "").strip()
    if sr:
        return sr[:240], provisional

    tok = (distributor_resolution_token or "").strip()
    if tok:
        suggested = suggested_name_for_distributor_token(tok)
        if suggested and not name_looks_like_tmp_code(suggested, dc):
            return suggested[:240], provisional
        return tok[:240], provisional

    if dc:
        return dc[:240], provisional
    return "—", provisional


def resolve_distributor_display_from_row(
    row: Any,
    distributor_name: str | None,
    distributor_code: str | None,
) -> tuple[str, bool]:
    """Adapter for FactInboundShipment-like rows."""
    return resolve_distributor_display(
        distributor_name=distributor_name,
        distributor_code=distributor_code,
        bill_to_raw=getattr(row, "bill_to_raw", None),
        ship_to_raw=getattr(row, "ship_to_raw", None),
        distributor_resolution_token=getattr(row, "distributor_resolution_token", None),
    )
