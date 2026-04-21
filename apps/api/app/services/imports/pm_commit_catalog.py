"""Product Master commit: catalog_product + EAV for sources with product_catalog_id.

Namespace rules (deterministic, no duplicate definitions for the same logical key):
- Staged file columns:  `catalog:{catalog_id}:staged:{header_slug}`
- Attribute candidates:  `catalog:{catalog_id}:candidate:{header_slug}`

`header_slug` = lowercased, non-alphanumeric → underscore, max 80 chars.
"""

from __future__ import annotations

import re
from typing import Any, Literal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimProduct
from app.models.ingestion import ImportJob, SourceDefinition
from app.services.imports.pm_dataframe_sanitize import normalize_scalar_for_pm, scalar_to_clean_str
from app.utils.json_safe import to_jsonable

# Aligned with `catalog_product` ORM columns (see `app.models.product_catalog.CatalogProduct`).
_MAX_CATALOG_SOURCE_SKU = 128
_MAX_CATALOG_DISPLAY_NAME = 512

from app.models.product_catalog import (
    AttributeDefinition,
    CatalogProduct,
    ProductAttributeValue,
)

def _header_slug(header: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (header or "").lower()).strip("_")
    return (s or "column")[:80]


def _namespace_for(catalog_id: int, kind: Literal["staged", "candidate"], header: str) -> str:
    prefix = "staged" if kind == "staged" else "candidate"
    return f"catalog:{catalog_id}:{prefix}:{_header_slug(header)}"


def get_or_create_attr_def(
    db: Session,
    *,
    catalog_id: int,
    namespace: str,
    display_name: str,
    kind: Literal["staged", "candidate"],
) -> AttributeDefinition:
    row = db.scalars(select(AttributeDefinition).where(AttributeDefinition.namespace == namespace)).first()
    if row:
        return row
    desc = "Product Master import: staged column" if kind == "staged" else "Product Master import: attribute candidate (steward review)"
    ad = AttributeDefinition(
        namespace=namespace,
        catalog_id=catalog_id,
        display_name=display_name[:256],
        description=desc,
        data_type="string",
    )
    db.add(ad)
    db.flush()
    return ad


def _set_pav(
    db: Session, *, catalog_product_id: int, attribute_definition_id: int, value: Any
) -> None:
    raw = to_jsonable(value)
    if raw is None:
        return
    wrapped: dict[str, Any] = {"value": raw}
    existing = db.scalars(
        select(ProductAttributeValue).where(
            ProductAttributeValue.catalog_product_id == catalog_product_id,
            ProductAttributeValue.attribute_definition_id == attribute_definition_id,
        )
    ).first()
    if existing:
        existing.value_json = wrapped
    else:
        db.add(
            ProductAttributeValue(
                catalog_product_id=catalog_product_id,
                attribute_definition_id=attribute_definition_id,
                value_json=wrapped,
            )
        )


def _disposition_columns(decisions: dict[str, Any] | None) -> tuple[list[str], list[str]]:
    """Return (stage_raw headers, attribute_candidate headers) from mapping_decisions."""
    staged: list[str] = []
    candidates: list[str] = []
    if not decisions:
        return staged, candidates
    for h, meta in decisions.items():
        if not isinstance(meta, dict):
            continue
        d = str(meta.get("disposition") or "").strip()
        if d == "stage_raw":
            staged.append(str(h))
        elif d == "attribute_candidate":
            candidates.append(str(h))
    return staged, candidates


def commit_catalog_and_eav(
    db: Session,
    job: ImportJob,
    source: SourceDefinition,
    df: pd.DataFrame,
    *,
    mapping_decisions: dict[str, Any] | None,
    staged_row_values: dict[str, dict[str, Any]],
    technical_id_col: str,
    name_col: str,
    source_sku_col: str | None = None,
) -> int:
    """Upsert catalog_product + PAV rows. Returns number of catalog_product rows touched.

    `technical_id_col` is the file column mapped to part_number or sku; used to find `DimProduct` by `dim_product.sku`.
    `source_sku_col` when set supplies `catalog_product.source_sku`; otherwise technical id value is used.
    """
    catalog_id = source.product_catalog_id
    if catalog_id is None:
        return 0

    stage_headers, cand_headers = _disposition_columns(mapping_decisions)
    n = 0
    for idx, row in df.iterrows():
        tid = scalar_to_clean_str(row.get(technical_id_col)) or ""
        if not tid:
            continue
        src_sku = tid
        if source_sku_col:
            alt = normalize_scalar_for_pm(row.get(source_sku_col))
            if alt is not None and str(alt).strip():
                src_sku = str(alt).strip()
        name = scalar_to_clean_str(row.get(name_col))
        if len(src_sku) > _MAX_CATALOG_SOURCE_SKU:
            raise ValueError(
                f"Mapped source_product_code / catalog source SKU exceeds {_MAX_CATALOG_SOURCE_SKU} characters "
                f"(row index {idx}, technical id {tid[:80]!r}…, length {len(src_sku)}). "
                "Shorten values or map a shorter column to source_product_code."
            )
        if name is not None and len(name) > _MAX_CATALOG_DISPLAY_NAME:
            raise ValueError(
                f"Display name exceeds {_MAX_CATALOG_DISPLAY_NAME} characters (row index {idx}, "
                f"technical id {tid[:80]!r}…)."
            )
        prod = db.scalars(select(DimProduct).where(DimProduct.sku == tid)).first()
        if not prod:
            continue

        cp = db.scalars(
            select(CatalogProduct).where(
                CatalogProduct.catalog_id == catalog_id,
                CatalogProduct.source_sku == src_sku,
            )
        ).first()
        meta: dict[str, Any] = {
            "import_job_id": job.id,
            "template_slug": job.template_slug,
            "stage_raw_headers": stage_headers,
            "attribute_candidate_headers": cand_headers,
        }
        rk = str(int(idx))
        row_staged = staged_row_values.get(rk) or {}
        if row_staged:
            meta["row_staged_snapshot"] = row_staged

        if cp:
            cp.display_name = name or cp.display_name
            cp.canonical_product_id = prod.id
            cp.source_metadata_json = meta
            cp.last_import_job_id = job.id
        else:
            cp = CatalogProduct(
                catalog_id=catalog_id,
                source_sku=src_sku,
                display_name=name,
                canonical_product_id=prod.id,
                source_metadata_json=meta,
                last_import_job_id=job.id,
            )
            db.add(cp)
        db.flush()
        n += 1

        for h in stage_headers:
            ns = _namespace_for(catalog_id, "staged", h)
            ad = get_or_create_attr_def(db, catalog_id=catalog_id, namespace=ns, display_name=h, kind="staged")
            v = normalize_scalar_for_pm(row.get(h))
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            if isinstance(v, float) and pd.isna(v):
                continue
            _set_pav(db, catalog_product_id=cp.id, attribute_definition_id=ad.id, value=v)

        for h in cand_headers:
            ns = _namespace_for(catalog_id, "candidate", h)
            ad = get_or_create_attr_def(db, catalog_id=catalog_id, namespace=ns, display_name=h, kind="candidate")
            v = normalize_scalar_for_pm(row.get(h))
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            if isinstance(v, float) and pd.isna(v):
                continue
            _set_pav(db, catalog_product_id=cp.id, attribute_definition_id=ad.id, value=v)

    return n
