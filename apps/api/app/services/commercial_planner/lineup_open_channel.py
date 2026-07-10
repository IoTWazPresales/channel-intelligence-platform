"""Open Channel route detection for current-lineup staging rows (no migrations).

Values like "Channel - Rectron" describe Open Channel stock routed via a distributor,
not a managed end-customer token. Flags and raw audit blobs live in raw_row_payload JSON.
"""
from __future__ import annotations

import re
from typing import Any

from app.models.commercial_lineup import CommercialLineupLine

# "Channel - Rectron", "channel- Mustek", etc.
_CHANNEL_ROUTE_PATTERN = re.compile(r"^\s*channel\s*-\s*(.+)$", re.IGNORECASE)

# Staging flag written by parser (no DB migration — JSON payload only).
STAGING_OPEN_CHANNEL_KEY = "staging_open_channel"
CHANNEL_ROUTE_UPLOADED_CELL_KEY = "channel_route_uploaded_cell"


def extract_distributor_name_from_channel_customer_cell(value: str | None) -> str | None:
    """If value looks like Open Channel routed via <name>, return distributor name hint."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _CHANNEL_ROUTE_PATTERN.match(s)
    if not m:
        return None
    hint = m.group(1).strip()
    return hint or None


def lineup_line_is_open_channel_staging(ln: CommercialLineupLine) -> bool:
    p = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else {}
    return p.get(STAGING_OPEN_CHANNEL_KEY) is True


def effective_lineup_customer_id(
    ln: CommercialLineupLine,
    *,
    open_channel_customer_id: int | None,
) -> int | None:
    """Customer grain for planned qty / PO match — OPEN_CHANNEL dim when row is open-channel staging."""
    if ln.customer_id is not None:
        return int(ln.customer_id)
    if lineup_line_is_open_channel_staging(ln) and open_channel_customer_id is not None:
        return int(open_channel_customer_id)
    return None


def managed_customer_token_unresolved(ln: CommercialLineupLine) -> bool:
    """True when a non–open-channel customer token is present but not mapped to DimCustomer."""
    if lineup_line_is_open_channel_staging(ln):
        return False
    ct = (ln.customer_token or "").strip()
    if not ct:
        return False
    return ln.customer_id is None


def distributor_cell_unresolved(ln: CommercialLineupLine) -> bool:
    """Distributor token present in payload but no distributor_id (includes unknown_distributor case)."""
    p = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else {}
    raw = p.get("distributor_token")
    if raw is None:
        return False
    tok = str(raw).strip()
    if not tok:
        return False
    return ln.distributor_id is None


def distributor_unassigned_soft(ln: CommercialLineupLine) -> bool:
    """No distributor_id and no distributor_token to resolve (intentionally blank)."""
    if ln.distributor_id is not None:
        return False
    p = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else {}
    raw = p.get("distributor_token")
    if raw is None:
        return True
    return not str(raw).strip()


def sync_ui_severity_for_line(ln: CommercialLineupLine, skip_reason: str) -> str | None:
    """UI hint: 'error' | 'warning' | None — does not change CommercialPlanLine schema."""
    if not skip_reason:
        return None
    if skip_reason == "missing_distributor":
        # CommercialPlanLine.distributor_id is NOT NULL — cannot sync without a distributor.
        return "error"
    if skip_reason in (
        "open_channel_account_missing",
        "missing_customer",
        "unresolved_product",
        "missing_srp",
        "missing_quantity",
        "duplicate",
    ):
        return "error"
    return "error"


def sync_skip_detail_message(ln: CommercialLineupLine, skip_reason: str) -> str | None:
    if not skip_reason:
        return None
    if skip_reason == "open_channel_account_missing":
        return (
            "Reference data missing: dim_customer code OPEN_CHANNEL (controlled Open Channel account). "
            "Not a row-mapping issue — run seed from repo root: pnpm local:db:seed or pnpm docker:seed. "
            "Never created from upload tokens."
        )
    if skip_reason == "missing_customer":
        return "Customer unresolved — map a customer or use a sync fallback."
    if skip_reason == "missing_distributor":
        if distributor_unassigned_soft(ln):
            return (
                "Reference data missing: dim_distributor code UNASSIGNED (placeholder for intentionally "
                "blank distributor). Run seed: pnpm local:db:seed or pnpm docker:seed. "
                "Or map a real distributor / use sync fallback."
            )
        return (
            "Distributor unresolved — a distributor_token is present but not mapped. "
            "Map to an existing distributor or use a sync fallback (not the UNASSIGNED placeholder)."
        )
    return None


def uploaded_columns_from_payload(payload: dict[str, Any] | None) -> dict[str, str]:
    """Return uploaded header→value map stored under raw_row_payload['uploaded']."""
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("uploaded")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if v is None:
            continue
        s = str(v).strip()
        if s:
            out[str(k)] = s
    return out
