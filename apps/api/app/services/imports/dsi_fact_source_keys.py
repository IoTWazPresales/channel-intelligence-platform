"""Deterministic ``source_key`` builders for DSI sell-out, returns, and distributor SOH facts.

Grain (sell-out and returns): ``distributor_id``, ``product_id``, ``customer_id``,
``transaction_date``, ``invoice_no``. Missing invoice numbers in source files use the empty
string ``''`` (not NULL) so hash inputs stay stable across re-imports.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date


def normalize_dsi_invoice_no(value: str | None) -> str:
    """Sentinel for absent invoice numbers — always ``''``, never NULL in keys."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    return s[:128]


def _dsi_transaction_grain_digest(
    *,
    distributor_id: int,
    product_id: int,
    customer_id: int,
    transaction_date: date,
    invoice_no: str | None,
) -> str:
    inv = normalize_dsi_invoice_no(invoice_no)
    body = (
        f"{int(distributor_id)}|{int(product_id)}|{int(customer_id)}|"
        f"{transaction_date.isoformat()}|{inv}"
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:48]


def dsi_sellout_source_key(
    *,
    distributor_id: int,
    product_id: int,
    customer_id: int,
    transaction_date: date,
    invoice_no: str | None,
) -> str:
    digest = _dsi_transaction_grain_digest(
        distributor_id=distributor_id,
        product_id=product_id,
        customer_id=customer_id,
        transaction_date=transaction_date,
        invoice_no=invoice_no,
    )
    return f"dsi-sellout:{digest}"


def dsi_return_source_key(
    *,
    distributor_id: int,
    product_id: int,
    customer_id: int,
    transaction_date: date,
    invoice_no: str | None,
) -> str:
    digest = _dsi_transaction_grain_digest(
        distributor_id=distributor_id,
        product_id=product_id,
        customer_id=customer_id,
        transaction_date=transaction_date,
        invoice_no=invoice_no,
    )
    return f"dsi-return:{digest}"


def dsi_inventory_source_key(
    *,
    distributor_id: int,
    product_id: int,
    as_of_date: date,
) -> str:
    return f"dsi-soh:{int(distributor_id)}:{int(product_id)}:{as_of_date.isoformat()}"


def dsi_reconciliation_source_key(
    *,
    distributor_id: int,
    product_id: int,
    customer_id: int | None,
    period_end_date: date,
) -> str:
    """Natural key for ``fact_inventory_reconciliation`` (customer id ``0`` = open channel bucket)."""
    cid = int(customer_id) if customer_id is not None else 0
    return (
        f"dsi-recon:{int(distributor_id)}:{int(product_id)}:{cid}:{period_end_date.isoformat()}"
    )
