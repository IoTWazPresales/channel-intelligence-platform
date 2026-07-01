"""Parser for current working lineup files uploaded to CommercialLineupCase.

Populates CommercialLineupLine rows from CSV or XLSX.
Creates an ImportJob audit record for every parse run.

Hard constraints (never violate):
- dap_evidence_local is stored as evidence only — never written to controlled_cost_amount.
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
from app.models.commercial_planner import (
    CommercialCustomerTerm,
    CommercialDistributorTerm,
    CommercialSkuAssumption,
)
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.services.commercial_planner.lineup_period_inference import (
    infer_case_product_line,
    infer_period_start,
)
from app.services.commercial_planner.lineup_pricing_resolution import (
    LineupTradeTermDefaults,
    resolve_lineup_pricing,
    sanitize_pct_evidence,
)

_PCT_EVIDENCE_FIELDS = (
    "rebate_pct_evidence",
    "dealer_margin_pct_evidence",
    "distributor_margin_pct_evidence",
    "import_tax_pct_evidence",
    "vat_pct_evidence",
)

from app.services.commercial_planner.current_lineup_seed import (
    CurrentLineupSourceNotConfiguredError,
    ensure_lineup_import_seed,
)
from app.services.commercial_planner.lineup_header_mapping import build_commercial_lineup_column_map
from app.services.commercial_planner.lineup_open_channel import (
    CHANNEL_ROUTE_UPLOADED_CELL_KEY,
    STAGING_OPEN_CHANNEL_KEY,
    extract_distributor_name_from_channel_customer_cell,
)

# ── Header detection (row scan) ─────────────────────────────────────────────────

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


@dataclass
class LineupParsePreview:
    """In-memory parse result (no DB writes)."""

    total_rows: int
    resolved_products: int
    unresolved_products: int
    unknown_customer_rows: int
    unknown_distributor_rows: int
    warnings: list[str]
    can_apply: bool
    rows: list[dict[str, Any]] = field(default_factory=list)


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


def _find_header_row(df: pd.DataFrame) -> int | None:
    """Scan first 12 rows for a header containing at least 2 of the known tokens."""
    for i in range(min(12, len(df))):
        row_vals = " ".join(str(v).lower() for v in df.iloc[i].values if pd.notna(v))
        hits = sum(1 for t in _HEADER_TOKENS if t in row_vals)
        if hits >= 2:
            return i
    return None


def _load_df(filename: str, file_bytes: bytes, *, sheet_name: str | None = None) -> pd.DataFrame:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("xlsx", "xlsm"):
        xl = pd.ExcelFile(io.BytesIO(file_bytes))
        sheets = xl.sheet_names
        if sheet_name and sheet_name in sheets:
            chosen = sheet_name
        else:
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


def _resolve_pricing_for_row_dict(
    rd: dict[str, Any],
    *,
    sku_assumptions: dict[int, CommercialSkuAssumption],
    customer_terms: dict[int, CommercialCustomerTerm],
    distributor_terms: dict[int, CommercialDistributorTerm],
) -> tuple[float | None, float | None, dict[str, Any] | None, list[str]]:
    """Run the backwards SRP -> DAP calculator for one parsed row.

    Uses file evidence first, then trade-term / sku-assumption fallbacks. Returns
    (calc_dap_cost_currency, calc_profit_total, pricing_chain_json, pricing_flags).
    No-op (all None) when there is no SRP to price from.
    """
    srp = rd.get("msrp_local")
    if srp is None:
        return None, None, None, []

    product_id = rd.get("product_id")
    customer_id = rd.get("customer_id")
    distributor_id = rd.get("distributor_id")

    assumption = sku_assumptions.get(product_id) if product_id is not None else None
    cust_term = customer_terms.get(customer_id) if customer_id is not None else None
    dist_term = distributor_terms.get(distributor_id) if distributor_id is not None else None

    defaults = LineupTradeTermDefaults(
        dealer_margin_pct=float(cust_term.customer_margin_pct) if cust_term else None,
        rebate_pct=float(cust_term.customer_rebate_pct) if cust_term else None,
        distributor_margin_pct=float(dist_term.distributor_margin_pct) if dist_term else None,
        vat_rate_pct=float(assumption.vat_rate_pct) if assumption else None,
        roe_local_per_cost_currency=(
            float(assumption.fx_plan_currency_per_cost_currency) if assumption else None
        ),
        controlled_cost_amount=float(assumption.controlled_cost_amount) if assumption else None,
    )

    resolution = resolve_lineup_pricing(
        srp_inc_vat_local=srp,
        quantity_units=rd.get("quantity_units"),
        file_vat_pct=rd.get("vat_pct_evidence"),
        file_dealer_margin_pct=rd.get("dealer_margin_pct_evidence"),
        file_rebate_pct=rd.get("rebate_pct_evidence"),
        file_distributor_margin_pct=rd.get("distributor_margin_pct_evidence"),
        file_import_tax_pct=rd.get("import_tax_pct_evidence"),
        file_roe=rd.get("roe_evidence"),
        defaults=defaults,
        evidence={
            "actual_dap_evidence_local": rd.get("actual_dap_evidence_local"),
            "dap_evidence_local": rd.get("dap_evidence_local"),
            "dealer_price_evidence_local": rd.get("dealer_price_evidence_local"),
            "net_price_evidence_local": rd.get("net_price_evidence_local"),
            "disti_cost_evidence_local": rd.get("disti_cost_evidence_local"),
            "old_srp_local": rd.get("old_srp_local"),
        },
    )
    return (
        resolution.result.calc_dap_cost_currency,
        resolution.result.calc_profit_total,
        resolution.pricing_chain,
        resolution.flags,
    )


def _parse_file_to_row_dicts(
    filename: str,
    file_bytes: bytes,
    *,
    product_map: dict[str, DimProduct],
    customer_map: dict[str, DimCustomer],
    distributor_map: dict[str, DimDistributor],
    row_limit: int | None = None,
    sheet_name: str | None = None,
) -> tuple[list[dict[str, Any]], list[str], int, int, int, int, int, list[str]]:
    """Parse tabular file into serialisable row dicts. Returns rows, warnings, counts, header."""
    warnings: list[str] = []
    raw_df = _load_df(filename, file_bytes, sheet_name=sheet_name)
    header_row = _find_header_row(raw_df)
    if header_row is None:
        header_row = 0
        warnings.append("Could not detect header row; using row 0 as header.")

    header = [str(v).strip() for v in raw_df.iloc[header_row].values]
    data_df = raw_df.iloc[header_row + 1 :].copy()
    data_df.columns = header  # type: ignore[assignment]
    data_df = data_df.reset_index(drop=True)
    col_map = build_commercial_lineup_column_map(header)
    if not col_map:
        warnings.append("No recognisable columns found in file; no lines would be written.")

    out: list[dict[str, Any]] = []
    total_rows = 0
    resolved_products = 0
    unresolved_products = 0
    unknown_customer_rows = 0
    unknown_distributor_rows = 0

    for row_idx, row in data_df.iterrows():
        if row_limit is not None and len(out) >= row_limit:
            break
        raw: dict[str, Any] = {}
        for dest_field, src_col in col_map.items():
            raw[dest_field] = row.get(src_col)

        all_empty = all(_safe_str(v) is None for v in raw.values())
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

        channel_dist_hint = extract_distributor_name_from_channel_customer_cell(customer_token_val)
        open_channel_row = channel_dist_hint is not None
        channel_uploaded_cell = customer_token_val if open_channel_row else None
        if open_channel_row:
            customer_token_val = None

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
                unknown_customer_rows += 1

        resolved_distributor: DimDistributor | None = None
        if distributor_token_val:
            resolved_distributor = distributor_map.get(distributor_token_val.lower())
            if resolved_distributor is None:
                diag.append("unknown_distributor")
                unknown_distributor_rows += 1
        elif open_channel_row and channel_dist_hint:
            resolved_distributor = distributor_map.get(channel_dist_hint.lower())
            if resolved_distributor is None:
                diag.append("unknown_distributor")
                unknown_distributor_rows += 1

        uploaded_by_header: dict[str, str] = {}
        for col in data_df.columns:
            cell = _safe_str(row.get(col))
            if cell:
                uploaded_by_header[str(col).strip()] = cell

        payload_keys = {
            "sku_raw",
            "part_number_raw",
            "model_raw",
            "customer_token",
            "distributor_token",
            "quantity_units",
            "msrp_local",
            "old_srp_local",
            "promo_price_evidence_local",
            "dap_evidence_local",
            "actual_dap_evidence_local",
            "dealer_price_evidence_local",
            "net_price_evidence_local",
            "disti_cost_evidence_local",
            "rebate_pct_evidence",
            "dealer_margin_pct_evidence",
            "distributor_margin_pct_evidence",
            "import_tax_pct_evidence",
            "roe_evidence",
            "vat_pct_evidence",
            "base_unit_raw",
        }
        raw_row_payload: dict[str, Any] = {
            dest: _safe_str(val) for dest, val in raw.items() if dest in payload_keys and val is not None
        }
        raw_row_payload["uploaded"] = uploaded_by_header
        if open_channel_row:
            raw_row_payload[STAGING_OPEN_CHANNEL_KEY] = True
            if channel_uploaded_cell:
                raw_row_payload[CHANNEL_ROUTE_UPLOADED_CELL_KEY] = channel_uploaded_cell
                raw_row_payload["customer_token"] = channel_uploaded_cell

        msrp_local = _safe_float(raw.get("msrp_local"))
        pct_evidence: dict[str, float | None] = {}
        for field in _PCT_EVIDENCE_FIELDS:
            raw_pct = _safe_float(raw.get(field))
            clean_pct = sanitize_pct_evidence(raw_pct, reference_price=msrp_local)
            if raw_pct is not None and clean_pct is None and "pct_evidence_out_of_range" not in diag:
                diag.append("pct_evidence_out_of_range")
            pct_evidence[field] = clean_pct

        out.append(
            {
                "source_row_number": int(row_idx) + 1,
                "product_id": resolved_product.id if resolved_product else None,
                "product_sku": resolved_product.sku if resolved_product else None,
                "customer_id": resolved_customer.id if resolved_customer else None,
                "customer_token": customer_token_val,
                "distributor_id": resolved_distributor.id if resolved_distributor else None,
                "sku_raw": sku_raw,
                "part_number_raw": part_number_raw,
                "model_raw": model_raw,
                "base_unit_raw": base_unit_raw,
                "quantity_units": _safe_float(raw.get("quantity_units")),
                "msrp_local": msrp_local,
                "old_srp_local": _safe_float(raw.get("old_srp_local")),
                "promo_price_evidence_local": _safe_float(raw.get("promo_price_evidence_local")),
                "dap_evidence_local": _safe_float(raw.get("dap_evidence_local")),
                "actual_dap_evidence_local": _safe_float(raw.get("actual_dap_evidence_local")),
                "dealer_price_evidence_local": _safe_float(raw.get("dealer_price_evidence_local")),
                "net_price_evidence_local": _safe_float(raw.get("net_price_evidence_local")),
                "disti_cost_evidence_local": _safe_float(raw.get("disti_cost_evidence_local")),
                "rebate_pct_evidence": pct_evidence["rebate_pct_evidence"],
                "dealer_margin_pct_evidence": pct_evidence["dealer_margin_pct_evidence"],
                "distributor_margin_pct_evidence": pct_evidence["distributor_margin_pct_evidence"],
                "import_tax_pct_evidence": pct_evidence["import_tax_pct_evidence"],
                "roe_evidence": _safe_float(raw.get("roe_evidence")),
                "vat_pct_evidence": pct_evidence["vat_pct_evidence"],
                "diagnostic_codes": diag,
                "row_status": "resolved" if resolved_product else "unresolved",
                "raw_row_payload": raw_row_payload,
            }
        )

    return (
        out,
        warnings,
        total_rows,
        resolved_products,
        unresolved_products,
        unknown_customer_rows,
        unknown_distributor_rows,
        list(data_df.columns),
    )


async def preview_current_lineup_file(
    db: AsyncSession,
    filename: str,
    file_bytes: bytes,
    *,
    sample_limit: int = 150,
) -> LineupParsePreview:
    """Parse file without writing lineup lines (preview before apply)."""
    products = (await db.execute(select(DimProduct))).scalars().all()
    customers = (await db.execute(select(DimCustomer))).scalars().all()
    distributors = (await db.execute(select(DimDistributor))).scalars().all()
    product_map = _build_product_map(list(products))
    customer_map = _build_customer_map(list(customers))
    distributor_map = _build_distributor_map(list(distributors))

    rows, warnings, total_rows, resolved_products, unresolved_products, unk_cust, unk_dist, _header = (
        _parse_file_to_row_dicts(
            filename,
            file_bytes,
            product_map=product_map,
            customer_map=customer_map,
            distributor_map=distributor_map,
            row_limit=sample_limit,
        )
    )
    return LineupParsePreview(
        total_rows=total_rows,
        resolved_products=resolved_products,
        unresolved_products=unresolved_products,
        unknown_customer_rows=unk_cust,
        unknown_distributor_rows=unk_dist,
        warnings=warnings,
        can_apply=total_rows > 0 and resolved_products > 0,
        rows=rows,
    )


async def parse_current_lineup_file(
    db: AsyncSession,
    case_id: int,
    filename: str,
    file_bytes: bytes,
    *,
    existing_import_job_id: int | None = None,
    template_slug: str = "current_lineup",
    source_code: str = "current_lineup_system",
    sheet_name: str | None = None,
    folder_path: str | None = None,
) -> ParseResult:
    """Parse an uploaded lineup file and write CommercialLineupLine rows.

    Creates an ImportJob audit record tagged ``template_slug`` (default ``current_lineup``; the
    unified Import-Centre path passes ``unified_lineup``).
    dap_evidence_local is stored as evidence only — never written to controlled_cost_amount.
    """
    now = datetime.now(tz=timezone.utc)

    case = await db.get(CommercialLineupCase, case_id)
    if case is None:
        raise ValueError(f"CommercialLineupCase id={case_id} not found")

    # Idempotent seed: upsert template + insert the system source if missing.
    await ensure_lineup_import_seed(db, template_slug=template_slug, source_code=source_code)

    # Resolve source_definition for the lineup template (required FK).
    source = await db.scalar(
        select(SourceDefinition)
        .join(ImportTemplate, ImportTemplate.id == SourceDefinition.import_template_id)
        .where(ImportTemplate.slug == template_slug, SourceDefinition.code == source_code)
        .limit(1)
    )
    if source is None:
        tpl = await db.scalar(select(ImportTemplate).where(ImportTemplate.slug == template_slug))
        remediation = (
            "From the apps/api directory run: alembic upgrade head "
            "(current_lineup seed 20260428_0021 / unified_lineup seed 20260628_0056 or later). "
            "If developing locally, ensure PYTHONPATH includes the app package."
        )
        if tpl is None:
            raise CurrentLineupSourceNotConfiguredError(
                f"Import template {template_slug!r} is missing after seed attempt.",
                remediation=remediation,
            )
        raise CurrentLineupSourceNotConfiguredError(
            f"SourceDefinition {source_code!r} is missing after seed attempt.",
            remediation=remediation,
        )
    source_id = source.id

    if existing_import_job_id is not None:
        job = await db.get(ImportJob, existing_import_job_id)
        if job is None:
            raise ValueError(f"ImportJob id={existing_import_job_id} not found for lineup parse")
        job.status = "running"
        job.file_name = filename
        job.error_summary = None
        job.started_at = now
        job.completed_at = None
    else:
        job = ImportJob(
            source_id=source_id,
            template_slug=template_slug,
            import_mode="apply",
            status="running",
            file_name=filename,
            started_at=now,
        )
        db.add(job)
    await db.flush()

    parse_opts: dict[str, Any] = {}
    if isinstance(job.staged_metadata, dict):
        raw_opts = job.staged_metadata.get("lineup_parse_options")
        if isinstance(raw_opts, dict):
            parse_opts = raw_opts
    effective_sheet = sheet_name or parse_opts.get("sheet_name")
    effective_folder = folder_path or parse_opts.get("folder_path")

    try:
        products = (await db.execute(select(DimProduct))).scalars().all()
        customers = (await db.execute(select(DimCustomer))).scalars().all()
        distributors = (await db.execute(select(DimDistributor))).scalars().all()
        product_map = _build_product_map(list(products))
        customer_map = _build_customer_map(list(customers))
        distributor_map = _build_distributor_map(list(distributors))

        row_dicts, warnings, total_rows, resolved_products, unresolved_products, _, _, header_cols = (
            _parse_file_to_row_dicts(
                filename,
                file_bytes,
                product_map=product_map,
                customer_map=customer_map,
                distributor_map=distributor_map,
                row_limit=None,
                sheet_name=effective_sheet,
            )
        )

        # Trade-term / sku-assumption fallback maps for backwards pricing (one query each).
        sku_assumptions = {
            a.product_id: a for a in (await db.execute(select(CommercialSkuAssumption))).scalars().all()
        }
        customer_terms = {
            t.customer_id: t for t in (await db.execute(select(CommercialCustomerTerm))).scalars().all()
        }
        distributor_terms = {
            t.distributor_id: t for t in (await db.execute(select(CommercialDistributorTerm))).scalars().all()
        }

        lines_to_add: list[CommercialLineupLine] = []
        for rd in row_dicts:
            diag = list(rd.get("diagnostic_codes") or [])
            calc_dap, calc_profit, pricing_chain, pricing_flags = _resolve_pricing_for_row_dict(
                rd,
                sku_assumptions=sku_assumptions,
                customer_terms=customer_terms,
                distributor_terms=distributor_terms,
            )
            for flag in pricing_flags:
                if flag not in diag:
                    diag.append(flag)
            line = CommercialLineupLine(
                case_id=case_id,
                source_row_number=rd["source_row_number"],
                product_id=rd.get("product_id"),
                customer_id=rd.get("customer_id"),
                distributor_id=rd.get("distributor_id"),
                customer_token=rd.get("customer_token"),
                sku_raw=rd.get("sku_raw"),
                part_number_raw=rd.get("part_number_raw"),
                model_raw=rd.get("model_raw"),
                base_unit_raw=rd.get("base_unit_raw"),
                quantity_units=rd.get("quantity_units"),
                msrp_local=rd.get("msrp_local"),
                promo_price_evidence_local=rd.get("promo_price_evidence_local"),
                dap_evidence_local=rd.get("dap_evidence_local"),
                rebate_pct_evidence=rd.get("rebate_pct_evidence"),
                distributor_margin_pct_evidence=rd.get("distributor_margin_pct_evidence"),
                vat_pct_evidence=rd.get("vat_pct_evidence"),
                raw_row_payload=rd.get("raw_row_payload"),
                row_status=rd.get("row_status") or "imported",
                diagnostic_codes=diag if diag else None,
                pricing_chain_json=pricing_chain,
                calc_dap_cost_currency=calc_dap,
                calc_profit_total=calc_profit,
            )
            db.add(line)
            lines_to_add.append(line)

        await db.flush()

        # Infer reporting period (label x month columns) and product line (catalogue majority,
        # filename fallback); never overwrite a value a steward already set on the case.
        inferred_start, period_flags = infer_period_start(case.period_label, header_cols)
        if inferred_start is not None and case.inferred_period_start is None:
            case.inferred_period_start = inferred_start
        if period_flags:
            for f in period_flags:
                if f not in warnings:
                    warnings.append(f)
        if case.product_line is None and lines_to_add:
            resolved_pids = sorted({int(l.product_id) for l in lines_to_add if l.product_id})
            pline_by_id: dict[int, str | None] = {}
            if resolved_pids:
                cat_rows = (
                    await db.execute(
                        select(DimProduct.id, DimProduct.product_line).where(
                            DimProduct.id.in_(resolved_pids)
                        )
                    )
                ).all()
                pline_by_id = {int(r[0]): r[1] for r in cat_rows}
            resolved_plines: list[str] = []
            for line in lines_to_add:
                if not line.product_id:
                    continue
                pl = pline_by_id.get(int(line.product_id))
                if pl and str(pl).strip():
                    resolved_plines.append(str(pl).strip())
            inferred_line = infer_case_product_line(
                filename=filename,
                total_rows=len(lines_to_add),
                resolved_product_lines=resolved_plines,
            )
            if inferred_line:
                case.product_line = inferred_line

        if case.business_unit is None and lines_to_add:
            import asyncio

            from app.db.session_sync import SessionLocal as SyncSessionLocal
            from app.services.commercial_planner.lineup_business_unit_resolution import (
                LineupRowProductTokens,
                load_business_unit_by_product_id,
                resolve_lineup_business_unit,
            )
            from app.services.imports.product_resolution_index_cache import get_product_resolution_index

            bu_by_pid = await load_business_unit_by_product_id(db)

            def _load_index() -> Any:
                with SyncSessionLocal() as sync_db:
                    return get_product_resolution_index(sync_db)

            product_index = await asyncio.to_thread(_load_index)
            token_rows = [
                LineupRowProductTokens(
                    sku_raw=ln.sku_raw,
                    part_number_raw=ln.part_number_raw,
                    model_raw=ln.model_raw,
                )
                for ln in lines_to_add
            ]
            bu_report = resolve_lineup_business_unit(
                rows=token_rows,
                product_index=product_index,
                business_unit_by_product_id=bu_by_pid,
                sheet_name=effective_sheet,
                folder_path=effective_folder,
                manual_business_unit=parse_opts.get("business_unit"),
            )
            if bu_report.business_unit:
                case.business_unit = bu_report.business_unit
            for flag in bu_report.flags:
                if flag not in warnings:
                    warnings.append(flag)
            meta = dict(job.staged_metadata) if isinstance(job.staged_metadata, dict) else {}
            meta["lineup_bu_resolution"] = bu_report.to_dict()
            job.staged_metadata = meta

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
