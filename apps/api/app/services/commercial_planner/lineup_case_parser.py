"""Parser for current working lineup files uploaded to CommercialLineupCase.

Populates CommercialLineupLine rows from CSV or XLSX.
Creates an ImportJob audit record for every parse run.

Hard constraints (never violate):
- dap_evidence_local is stored as evidence only — never written to landed_cost_usd.
- Never auto-creates products, customers, or distributors.
- Never touches HistoricalLineupImportLine.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition

# ── Column alias mapping ──────────────────────────────────────────────────────

_CANONICAL_ALIASES: dict[str, list[str]] = {
    "sku_raw": ["sku", "item", "product_sku", "sku_raw"],
    "part_number_raw": ["part_number", "mpn", "part_no", "part no", "sales_part_number"],
    "model_raw": ["model", "model_name", "model name", "series"],
    "customer_token": ["customer", "customer_code", "account", "account_name"],
    "distributor_token": ["distributor", "disti", "distributor_code"],
    "quantity_units": ["qty", "quantity", "units", "forecast_qty"],
    "msrp_local": ["msrp", "srp", "rrp", "list_price", "retail_price"],
    "promo_price_evidence_local": [
        "promo_price", "promo_srp", "promo", "deal_price", "promo price",
        "suggested_promo_price",
    ],
    "dap_evidence_local": ["dap", "dap_local"],
    "rebate_pct_evidence": ["rebate", "rebate_pct"],
    "distributor_margin_pct_evidence": ["disti_margin", "distributor_margin", "disti_margin_pct"],
    "vat_pct_evidence": ["vat", "vat_pct", "tax_pct"],
    "base_unit_raw": ["base_unit", "baseunit", "base unit"],
}

_HEADER_TOKENS = {"sku", "model", "part", "qty", "quantity", "units", "msrp", "srp", "dap", "promo"}


@dataclass
class ParseResult:
    case_id: int
    import_job_id: int
    total_rows: int
    resolved_products: int
    unresolved_products: int
    line_count: int
    warnings: list[str] = field(default_factory=list)


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _safe_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none") else None


def _build_alias_lookup(columns: list[str]) -> dict[str, str]:
    """Return {canonical_field: actual_column_name} by matching lowercased aliases."""
    col_lower = {c.lower().replace(" ", "_"): c for c in columns}
    col_lower_space = {c.lower(): c for c in columns}
    mapping: dict[str, str] = {}
    for field_name, aliases in _CANONICAL_ALIASES.items():
        for alias in aliases:
            norm = alias.lower().replace(" ", "_")
            if norm in col_lower:
                mapping[field_name] = col_lower[norm]
                break
            if alias.lower() in col_lower_space:
                mapping[field_name] = col_lower_space[alias.lower()]
                break
    return mapping


def _find_header_row(df: pd.DataFrame) -> int | None:
    """Scan first 12 rows for a header containing at least 2 of the known tokens."""
    for i in range(min(12, len(df))):
        row_vals = " ".join(str(v).lower() for v in df.iloc[i].values if pd.notna(v))
        hits = sum(1 for t in _HEADER_TOKENS if t in row_vals)
        if hits >= 2:
            return i
    return None


def _load_df(filename: str, file_bytes: bytes) -> pd.DataFrame:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("xlsx", "xlsm"):
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
        sheets = xl.sheet_names
        chosen = sheets[0]
        for name in sheets:
            sample = xl.parse(name, header=None, nrows=15)
            vals = " ".join(str(v).lower() for v in sample.values.flatten() if pd.notna(v))
            if "sku" in vals or "model" in vals:
                chosen = name
                break
        return xl.parse(chosen, header=None)
    return pd.read_csv(io.BytesIO(file_bytes), header=None, dtype=str)


def _build_product_map(products: list[DimProduct]) -> dict[str, DimProduct]:
    m: dict[str, DimProduct] = {}
    for p in products:
        for val in (p.sku, p.part_number, p.model_name, p.sales_model_name):
            if val:
                key = val.lower().strip()
                if key and key not in m:
                    m[key] = p
    return m


def _build_customer_map(customers: list[DimCustomer]) -> dict[str, DimCustomer]:
    m: dict[str, DimCustomer] = {}
    for c in customers:
        if c.name:
            m[c.name.lower().strip()] = c
        if c.code:
            m[c.code.lower().strip()] = c
    return m


def _build_distributor_map(distributors: list[DimDistributor]) -> dict[str, DimDistributor]:
    m: dict[str, DimDistributor] = {}
    for d in distributors:
        if d.name:
            m[d.name.lower().strip()] = d
        if d.code:
            m[d.code.lower().strip()] = d
    return m


async def parse_current_lineup_file(
    db: AsyncSession,
    case_id: int,
    filename: str,
    file_bytes: bytes,
) -> ParseResult:
    """Parse an uploaded lineup file and write CommercialLineupLine rows.

    Creates an ImportJob audit record.
    dap_evidence_local is stored as evidence only — never written to landed_cost_usd.
    """
    now = datetime.now(tz=timezone.utc)

    case = await db.get(CommercialLineupCase, case_id)
    if case is None:
        raise ValueError(f"CommercialLineupCase id={case_id} not found")

    # Resolve source_definition for the current_lineup template (required FK).
    source = await db.scalar(
        select(SourceDefinition)
        .join(ImportTemplate, ImportTemplate.id == SourceDefinition.import_template_id)
        .where(ImportTemplate.slug == "current_lineup")
        .limit(1)
    )
    source_id = source.id if source is not None else 1

    job = ImportJob(
        source_id=source_id,
        template_slug="current_lineup",
        import_mode="apply",
        status="running",
        file_name=filename,
        started_at=now,
    )
    db.add(job)
    await db.flush()

    warnings: list[str] = []

    try:
        raw_df = _load_df(filename, file_bytes)

        header_row = _find_header_row(raw_df)
        if header_row is None:
            header_row = 0
            warnings.append("Could not detect header row; using row 0 as header.")

        header = [str(v).strip() for v in raw_df.iloc[header_row].values]
        data_df = raw_df.iloc[header_row + 1 :].copy()
        data_df.columns = header  # type: ignore[assignment]
        data_df = data_df.reset_index(drop=True)

        col_map = _build_alias_lookup(header)

        if not col_map:
            warnings.append("No recognisable columns found in file; no lines written.")

        # Load all products and customers into memory
        products = (await db.execute(select(DimProduct))).scalars().all()
        customers = (await db.execute(select(DimCustomer))).scalars().all()
        distributors = (await db.execute(select(DimDistributor))).scalars().all()

        product_map = _build_product_map(list(products))
        customer_map = _build_customer_map(list(customers))
        distributor_map = _build_distributor_map(list(distributors))

        lines_to_add: list[CommercialLineupLine] = []
        total_rows = 0
        resolved_products = 0
        unresolved_products = 0

        for row_idx, row in data_df.iterrows():
            raw: dict[str, Any] = {}
            for dest_field, src_col in col_map.items():
                raw[dest_field] = row.get(src_col)

            all_empty = all(
                _safe_str(v) is None for v in raw.values()
            )
            if all_empty:
                continue

            total_rows += 1
            diag: list[str] = []

            sku_raw = _safe_str(raw.get("sku_raw"))
            part_number_raw = _safe_str(raw.get("part_number_raw"))
            model_raw = _safe_str(raw.get("model_raw"))
            customer_token_val = _safe_str(raw.get("customer_token"))
            distributor_token_val = _safe_str(raw.get("distributor_token"))
            base_unit_raw = _safe_str(raw.get("base_unit_raw"))

            resolved_product: DimProduct | None = None
            for lookup_val in (sku_raw, part_number_raw, model_raw):
                if lookup_val and lookup_val.lower() in product_map:
                    resolved_product = product_map[lookup_val.lower()]
                    break

            if resolved_product is None:
                diag.append("unresolved_product")
                unresolved_products += 1
            else:
                resolved_products += 1

            resolved_customer: DimCustomer | None = None
            if customer_token_val:
                resolved_customer = customer_map.get(customer_token_val.lower())
                if resolved_customer is None:
                    diag.append("unknown_customer")

            resolved_distributor: DimDistributor | None = None
            if distributor_token_val:
                resolved_distributor = distributor_map.get(distributor_token_val.lower())

            payload_keys = {
                "sku_raw", "part_number_raw", "model_raw", "customer_token",
                "distributor_token", "quantity_units", "msrp_local",
                "promo_price_evidence_local", "dap_evidence_local",
                "rebate_pct_evidence", "distributor_margin_pct_evidence",
                "vat_pct_evidence", "base_unit_raw",
            }
            raw_row_payload = {
                dest: _safe_str(val)
                for dest, val in raw.items()
                if dest in payload_keys and val is not None
            }

            line = CommercialLineupLine(
                case_id=case_id,
                source_row_number=int(row_idx) + 1,
                product_id=resolved_product.id if resolved_product else None,
                customer_id=resolved_customer.id if resolved_customer else None,
                distributor_id=resolved_distributor.id if resolved_distributor else None,
                customer_token=customer_token_val,
                sku_raw=sku_raw,
                part_number_raw=part_number_raw,
                model_raw=model_raw,
                base_unit_raw=base_unit_raw,
                quantity_units=_safe_float(raw.get("quantity_units")),
                msrp_local=_safe_float(raw.get("msrp_local")),
                promo_price_evidence_local=_safe_float(raw.get("promo_price_evidence_local")),
                dap_evidence_local=_safe_float(raw.get("dap_evidence_local")),
                rebate_pct_evidence=_safe_float(raw.get("rebate_pct_evidence")),
                distributor_margin_pct_evidence=_safe_float(raw.get("distributor_margin_pct_evidence")),
                vat_pct_evidence=_safe_float(raw.get("vat_pct_evidence")),
                raw_row_payload=raw_row_payload,
                row_status="resolved" if resolved_product else "unresolved",
                diagnostic_codes=diag if diag else None,
            )
            db.add(line)
            lines_to_add.append(line)

        await db.flush()

        job.status = "completed"
        job.completed_at = datetime.now(tz=timezone.utc)
        job.stage = "loaded"
        case.import_job_id = job.id
        case.file_name = filename

        await db.commit()

        return ParseResult(
            case_id=case_id,
            import_job_id=job.id,
            total_rows=total_rows,
            resolved_products=resolved_products,
            unresolved_products=unresolved_products,
            line_count=len(lines_to_add),
            warnings=warnings,
        )

    except Exception as exc:
        await db.rollback()
        job.status = "failed"
        job.error_summary = str(exc)
        job.completed_at = datetime.now(tz=timezone.utc)
        db.add(job)
        await db.commit()
        raise
