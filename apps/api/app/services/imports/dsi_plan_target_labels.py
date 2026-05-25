"""Resolve steward plan ``suggested_target_id`` to display labels (read-only enrichment)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer, DimDistributor, DimProduct


def enrich_plan_rows_with_target_labels(session: Session, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return rows

    customer_ids: set[int] = set()
    distributor_ids: set[int] = set()
    product_ids: set[int] = set()

    for r in rows:
        tid = r.get("suggested_target_id")
        if tid is None:
            continue
        try:
            i = int(tid)
        except (TypeError, ValueError):
            continue
        if i <= 0:
            continue
        et = str(r.get("entity_type") or "")
        act = str(r.get("suggested_action") or "")
        if et == "customer_dealer_token" or act == "map_customer":
            customer_ids.add(i)
        elif et == "distributor_token" or act == "map_distributor":
            distributor_ids.add(i)
        elif et == "product_identifier" or act == "resolve_product":
            product_ids.add(i)

    cust_labels: dict[int, str] = {}
    if customer_ids:
        for row in session.scalars(select(DimCustomer).where(DimCustomer.id.in_(customer_ids))).all():
            name = (row.name or row.code or "").strip()
            code = (row.code or "").strip()
            cust_labels[int(row.id)] = f"{name} ({code})" if code and name != code else (name or code or f"id {row.id}")

    dist_labels: dict[int, str] = {}
    if distributor_ids:
        for row in session.scalars(select(DimDistributor).where(DimDistributor.id.in_(distributor_ids))).all():
            name = (row.name or row.code or "").strip()
            code = (row.code or "").strip()
            dist_labels[int(row.id)] = f"{name} ({code})" if code and name != code else (name or code or f"id {row.id}")

    prod_labels: dict[int, str] = {}
    if product_ids:
        for row in session.scalars(select(DimProduct).where(DimProduct.id.in_(product_ids))).all():
            sm = (row.sales_model_name or row.model_name or row.sku or "").strip()
            sku = (row.sku or "").strip()
            prod_labels[int(row.id)] = f"{sm} · sku {sku}" if sku and sm else (sm or sku or f"id {row.id}")

    out: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r)
        tid = row.get("suggested_target_id")
        if tid is None:
            out.append(row)
            continue
        try:
            i = int(tid)
        except (TypeError, ValueError):
            out.append(row)
            continue
        et = str(row.get("entity_type") or "")
        act = str(row.get("suggested_action") or "")
        label: str | None = None
        if et == "customer_dealer_token" or act == "map_customer":
            label = cust_labels.get(i)
        elif et == "distributor_token" or act == "map_distributor":
            label = dist_labels.get(i)
        elif et == "product_identifier" or act == "resolve_product":
            label = prod_labels.get(i)
        if label:
            row["suggested_target_label"] = label[:256]
        out.append(row)
    return out
