from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.ingestion import ImportJob, ImportRowResult


_SHEET_SKIP_WORDS = ("summary", "recap", "pivot", "notes")
_SHEET_ALLOW_WORDS = ("lineup", "plan", "history", "historical", "assortment")
_SUMMARY_ROW_MARKERS = ("total", "subtotal", "grand total", "summary")
_HEADER_SCAN_MAX_ROWS = 12

_CANONICAL_ALIASES: dict[str, list[str]] = {
    "customer_token": ["customer", "customer_code", "account", "account_name", "end customer", "buyer", "sold to", "reseller"],
    "distributor_token": ["distributor", "disti", "distributor_code", "partner"],
    "channel_token": ["channel", "route_to_market", "rtm"],
    "period_label": ["period", "month", "quarter", "fiscal"],
    "period_start": ["period_start", "start_date", "date"],
    "country_code": ["country", "country_code"],
    "currency_code": ["currency", "currency_code"],
    # base_unit is intentionally excluded from sku_raw — "Base Unit" is a product descriptor
    # (retail/box form factor), not a product identity key. It belongs in base_unit_raw only.
    "sku_raw": ["sku", "item", "product_sku"],
    "part_number_raw": ["part_number", "mpn", "part no", "part number", "sales part number", "sales_part_number"],
    "model_raw": ["model", "model_name", "model name", "series"],
    "base_unit_raw": ["base_unit", "baseunit", "base unit"],
    "msrp_local": ["msrp", "list_price", "rrp"],
    "promo_price_local": ["promo_price", "promo", "sell_price", "street_price"],
    "quantity_units": ["qty", "quantity", "units", "forecast_qty"],
    "dap_local": ["dap"],
    "actual_dap_local": ["actual_dap", "actual dap"],
    "disti_cost_local": ["disti_cost", "distributor_cost", "cost"],
    "disti_margin_pct": ["disti_margin", "distributor_margin"],
    "rebate_pct": ["rebate", "rebate_pct"],
    "dealer_margin_pct": ["dealer_margin", "dealer_margin_pct"],
    "vat_pct": ["vat", "tax_pct"],
    "customer_feedback": ["customer_feedback", "feedback", "reason"],
    "workflow_notes": ["notes", "comment", "remarks"],
}
_HEADER_SIGNATURE_TOKENS = {
    "productline",
    "country",
    "customer",
    "modelname",
    "partnumber",
    "baseunit",
}

# Diagnostics that escalate a row to severity=error and take precedence as the primary code.
_ERROR_LEVEL_CODES = frozenset({
    "missing_key_fields",
    "unknown_product",
    "unknown_customer",
    "invalid_quantity",
    "unknown_distributor",
    "ambiguous_product_match",
    "ambiguous_customer_match",
})


def _norm_token(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    return re.sub(r"[\s\-_]+", "", text)


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def _parse_decimal(value: Any) -> Decimal | None:
    raw = _clean_str(value)
    if raw is None:
        return None
    normalized = raw.replace(",", "").replace("$", "").replace("%", "").strip()
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except Exception:  # noqa: BLE001
        return None


def _parse_period_start(value: Any) -> date | None:
    if value is None or value == "":
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:  # noqa: BLE001
        return None
    if pd.isna(parsed):
        return None
    return parsed.date()


def _build_header_map(columns: list[str]) -> tuple[dict[str, str], float]:
    normalized_cols = {_norm_token(c): c for c in columns}
    mapping: dict[str, str] = {}
    # Track claimed source columns so no workbook column is assigned to more than one
    # canonical field.  First canonical (in _CANONICAL_ALIASES insertion order) wins.
    claimed_sources: set[str] = set()
    matched_aliases = 0
    total_aliases = 0
    for target, opts in _CANONICAL_ALIASES.items():
        total_aliases += 1
        for alias in opts:
            actual = normalized_cols.get(_norm_token(alias))
            if actual and actual not in claimed_sources:
                mapping[target] = actual
                claimed_sources.add(actual)
                matched_aliases += 1
                break
    confidence = (matched_aliases / total_aliases) if total_aliases else 0.0
    return mapping, confidence


@dataclass
class ParsedRow:
    row_number: int
    payload: dict[str, Any]
    diagnostics: list[str]
    status: str
    confidence: float


@dataclass
class ParsedSheet:
    sheet_name: str
    rows: list[ParsedRow]
    mapping: dict[str, str]
    mapping_confidence: float
    header_row_number: int


def _row_is_blank(row: pd.Series) -> bool:
    for value in row.values:
        if _clean_str(value):
            return False
    return True


def _row_is_summary(row: pd.Series) -> bool:
    first = _clean_str(row.iloc[0] if len(row.values) else None)
    if not first:
        return False
    t = first.lower()
    return any(marker in t for marker in _SUMMARY_ROW_MARKERS)


def _extract_row_tokens(row: pd.Series) -> list[str]:
    tokens: list[str] = []
    for value in row.values.tolist():
        text = _clean_str(value)
        if text:
            tokens.append(text)
    return tokens


def _detect_header_row(raw: pd.DataFrame) -> tuple[int | None, dict[str, str], float]:
    scan_max = min(len(raw), _HEADER_SCAN_MAX_ROWS)
    best_idx: int | None = None
    best_mapping: dict[str, str] = {}
    best_conf = 0.0
    best_score = -1.0
    for idx in range(scan_max):
        row = raw.iloc[idx]
        tokens = _extract_row_tokens(row)
        if not tokens:
            continue
        mapping, conf = _build_header_map(tokens)
        signature_hits = sum(1 for t in tokens if _norm_token(t) in _HEADER_SIGNATURE_TOKENS)
        score = float(len(mapping)) + (signature_hits * 0.5)
        if score > best_score:
            best_idx = idx
            best_mapping = mapping
            best_conf = conf
            best_score = score
    if best_idx is None:
        return None, {}, 0.0
    if len(best_mapping) < 2 and best_score < 2:
        return None, {}, 0.0
    return best_idx, best_mapping, best_conf


def parse_historical_workbook(
    filename: str,
    raw_bytes: bytes,
    mapping_override: dict[str, dict[str, str]] | None = None,
) -> tuple[list[ParsedSheet], dict[str, Any]]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        frames = {"csv": pd.read_csv(io.BytesIO(raw_bytes), header=None)}
    else:
        xls = pd.ExcelFile(io.BytesIO(raw_bytes), engine="openpyxl")
        frames = {sheet: pd.read_excel(xls, sheet_name=sheet, header=None) for sheet in xls.sheet_names}

    selected: list[ParsedSheet] = []
    skipped_sheets: list[str] = []
    selected_sheet_details: list[dict[str, Any]] = []
    skipped_sheet_details: list[dict[str, Any]] = []
    for sheet_name, frame in frames.items():
        if frame.empty or frame.shape[1] == 0:
            skipped_sheets.append(sheet_name)
            skipped_sheet_details.append({"sheet_name": sheet_name, "reason": "empty_sheet"})
            continue
        header_idx, mapping, map_conf = _detect_header_row(frame)
        if header_idx is None:
            skipped_sheets.append(sheet_name)
            skipped_sheet_details.append({"sheet_name": sheet_name, "reason": "no_header_signature"})
            continue
        sheet_name_lower = sheet_name.lower()
        likely_lineup = any(word in sheet_name_lower for word in _SHEET_ALLOW_WORDS) or (
            len(mapping) >= 3 and any(k in mapping for k in ("customer_token", "model_raw", "part_number_raw", "base_unit_raw"))
        )
        if any(word in sheet_name_lower for word in _SHEET_SKIP_WORDS) and not likely_lineup:
            skipped_sheets.append(sheet_name)
            skipped_sheet_details.append({"sheet_name": sheet_name, "reason": "sheet_name_skip_word"})
            continue
        if not likely_lineup:
            skipped_sheets.append(sheet_name)
            skipped_sheet_details.append({"sheet_name": sheet_name, "reason": "not_likely_lineup"})
            continue

        # Apply user column mapping override BEFORE row extraction.
        # User-specified fields win; unspecified auto-detected fields remain.
        if mapping_override and sheet_name in mapping_override:
            for canonical, source_col in mapping_override[sheet_name].items():
                if source_col:  # ignore blank overrides
                    mapping[canonical] = source_col
            # Recompute confidence based on effective mapping after override.
            map_conf = len(mapping) / max(len(_CANONICAL_ALIASES), 1)

        header_cells = frame.iloc[header_idx].tolist()
        header_tokens = [(_clean_str(v) or f"column_{i+1}") for i, v in enumerate(header_cells)]
        data = frame.iloc[header_idx + 1 :].copy()
        data.columns = header_tokens[: data.shape[1]]
        data = data.loc[:, [c for c in data.columns if _clean_str(c) is not None]]

        rows: list[ParsedRow] = []
        seen_row_keys: set[tuple[str, str, str, str]] = set()
        for idx, row in data.iterrows():
            diagnostics: list[str] = []
            if _row_is_blank(row):
                continue
            if _row_is_summary(row):
                diagnostics.append("summary_row_dropped")
                rows.append(
                    ParsedRow(
                        row_number=int(idx) + 1,
                        payload=row.where(pd.notnull(row), None).to_dict(),
                        diagnostics=diagnostics,
                        status="dropped",
                        confidence=map_conf,
                    )
                )
                continue

            payload = row.where(pd.notnull(row), None).to_dict()
            normalized: dict[str, Any] = {}
            for canonical, source_col in mapping.items():
                normalized[canonical] = row.get(source_col)

            sku_token = _clean_str(normalized.get("sku_raw"))
            part_token = _clean_str(normalized.get("part_number_raw"))
            model_token = _clean_str(normalized.get("model_raw"))
            qty = _parse_decimal(normalized.get("quantity_units"))
            if not any((sku_token, part_token, model_token)):
                diagnostics.append("missing_key_fields")
            if qty is None and _clean_str(normalized.get("quantity_units")):
                diagnostics.append("invalid_quantity")
            if map_conf < 0.25:
                diagnostics.append("low_mapping_confidence")
            row_key = (
                _norm_token(sku_token),
                _norm_token(part_token),
                _norm_token(model_token),
                _norm_token(_clean_str(normalized.get("customer_token"))),
            )
            if row_key in seen_row_keys and any(row_key):
                diagnostics.append("duplicate_row_within_sheet")
            seen_row_keys.add(row_key)
            margin_fields = (
                normalized.get("disti_margin_pct"),
                normalized.get("rebate_pct"),
                normalized.get("dealer_margin_pct"),
                normalized.get("vat_pct"),
            )
            non_empty_margin = [x for x in margin_fields if _clean_str(x)]
            if 0 < len(non_empty_margin) < len(margin_fields):
                diagnostics.append("partial_margin_stack")

            rows.append(
                ParsedRow(
                    row_number=int(idx) + 1,
                    payload={k: _clean_str(v) for k, v in normalized.items()},
                    diagnostics=diagnostics,
                    status="accepted" if "missing_key_fields" not in diagnostics else "rejected",
                    confidence=map_conf,
                )
            )
        selected.append(
            ParsedSheet(
                sheet_name=sheet_name,
                rows=rows,
                mapping=mapping,
                mapping_confidence=map_conf,
                header_row_number=header_idx + 1,
            )
        )
        selected_sheet_details.append(
            {
                "sheet_name": sheet_name,
                "header_row_number": header_idx + 1,
                "mapped_fields": sorted(mapping.keys()),
                "source_columns": header_tokens,
                "row_count": len(rows),
                "mapping_confidence": map_conf,
            }
        )

    schema = {
        "sheet_count": len(frames),
        "selected_sheets": [s.sheet_name for s in selected],
        "skipped_sheets": skipped_sheets,
        "selected_row_count": sum(len(s.rows) for s in selected),
        "selected_sheet_details": selected_sheet_details,
        "skipped_sheet_details": skipped_sheet_details,
    }
    return selected, schema


def process_historical_lineup_import(db: Session, job: ImportJob, filename: str, raw_bytes: bytes) -> int:
    # Read any user-supplied mapping override stored by the API layer before sync processing.
    # Shape: { sheet_name: { canonical_field: actual_workbook_column } }
    _raw_override = job.mapping_decisions
    mapping_override: dict[str, dict[str, str]] | None = None
    if isinstance(_raw_override, dict) and _raw_override:
        mapping_override = {k: v for k, v in _raw_override.items() if isinstance(v, dict)}

    parsed_sheets, schema = parse_historical_workbook(filename, raw_bytes, mapping_override=mapping_override)
    job.inferred_schema = schema
    job.field_mapping = {s.sheet_name: s.mapping for s in parsed_sheets}
    # Overwrite mapping_decisions with the final effective mapping actually used (for audit trail).
    job.mapping_decisions = {s.sheet_name: s.mapping for s in parsed_sheets}
    errors = 0

    customers = db.scalars(select(DimCustomer)).all()
    distributors = db.scalars(select(DimDistributor)).all()
    channels = db.scalars(select(DimChannel)).all()
    products = db.scalars(select(DimProduct)).all()

    customer_by_code = {c.code.lower(): c for c in customers}
    customer_by_name = {c.name.lower(): c for c in customers if c.name}
    distributor_by_code = {d.code.lower(): d for d in distributors}
    distributor_by_name = {d.name.lower(): d for d in distributors if d.name}
    channel_by_code = {c.code.lower(): c for c in channels}
    product_by_sku = {p.sku.lower(): p for p in products}
    # Part-number is UNIQUE — safe direct dict.
    product_by_part_number: dict[str, DimProduct] = {
        p.part_number.lower(): p for p in products if p.part_number
    }
    # model_name / sales_model_name are NOT unique — only index them when unambiguous.
    _model_name_cnt: dict[str, int] = {}
    _sales_model_cnt: dict[str, int] = {}
    for _p in products:
        if _p.model_name:
            _k = _p.model_name.lower()
            _model_name_cnt[_k] = _model_name_cnt.get(_k, 0) + 1
        if _p.sales_model_name:
            _k = _p.sales_model_name.lower()
            _sales_model_cnt[_k] = _sales_model_cnt.get(_k, 0) + 1
    product_by_model_name: dict[str, DimProduct] = {
        _p.model_name.lower(): _p
        for _p in products
        if _p.model_name and _model_name_cnt.get(_p.model_name.lower(), 0) == 1
    }
    product_by_sales_model_name: dict[str, DimProduct] = {
        _p.sales_model_name.lower(): _p
        for _p in products
        if _p.sales_model_name and _sales_model_cnt.get(_p.sales_model_name.lower(), 0) == 1
    }

    for sheet in parsed_sheets:
        accepted_rows = [r for r in sheet.rows if r.status != "dropped"]
        if not accepted_rows:
            continue

        header_customer_id: int | None = None
        header_distributor_id: int | None = None
        header_channel_id: int | None = None
        period_label = None
        period_start = None
        country_code = None
        currency_code = None

        if accepted_rows:
            period_label = accepted_rows[0].payload.get("period_label")
            period_start = _parse_period_start(accepted_rows[0].payload.get("period_start") or period_label)
            country_code = accepted_rows[0].payload.get("country_code")
            currency_code = accepted_rows[0].payload.get("currency_code")

        header = None
        if job.import_mode == "apply":
            header = HistoricalLineupImportHeader(
                import_job_id=job.id,
                source_id=job.source_id,
                workbook_name=filename,
                sheet_name=sheet.sheet_name,
                pm_domain=None,
                period_label=_clean_str(period_label),
                period_start=period_start,
                customer_id=header_customer_id,
                distributor_id=header_distributor_id,
                channel_id=header_channel_id,
                country_code=_clean_str(country_code),
                currency_code=_clean_str(currency_code),
                source_metadata={"mapping_confidence": sheet.mapping_confidence, "mapping": sheet.mapping},
            )
            db.add(header)
            db.flush()
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="historical_lineup_sheet_summary",
                message=(
                    f"Sheet {sheet.sheet_name!r} detected with header row {sheet.header_row_number}; "
                    f"mapped_fields={len(sheet.mapping)}; parsed_rows={len(sheet.rows)}."
                ),
            )
        )

        for parsed in sheet.rows:
            payload = parsed.payload
            diagnostics = list(parsed.diagnostics)
            severity = "warning"
            customer_id = None
            distributor_id = None
            channel_id = None
            product_id = None

            customer_token = _clean_str(payload.get("customer_token"))
            if customer_token:
                customer = customer_by_code.get(customer_token.lower()) or customer_by_name.get(customer_token.lower())
                if customer:
                    customer_id = customer.id
                else:
                    # ILIKE fallback — resolves only when exactly one customer matches.
                    # Do not silently pick when multiple records match.
                    _ilike_customers = db.scalars(
                        select(DimCustomer).where(
                            or_(
                                DimCustomer.code.ilike(f"%{customer_token}%"),
                                DimCustomer.name.ilike(f"%{customer_token}%"),
                            )
                        )
                    ).all()
                    if len(_ilike_customers) == 1:
                        customer_id = _ilike_customers[0].id
                        diagnostics.append("customer_matched_by_ilike")
                    elif len(_ilike_customers) > 1:
                        diagnostics.append("ambiguous_customer_match")
                        errors += 1
                    else:
                        diagnostics.append("unknown_customer")
                        errors += 1

            distributor_token = _clean_str(payload.get("distributor_token"))
            if distributor_token:
                distributor = distributor_by_code.get(distributor_token.lower()) or distributor_by_name.get(
                    distributor_token.lower()
                )
                if distributor:
                    distributor_id = distributor.id
                else:
                    diagnostics.append("unknown_distributor")
                    errors += 1

            channel_token = _clean_str(payload.get("channel_token"))
            if channel_token:
                channel = channel_by_code.get(channel_token.lower())
                if channel:
                    channel_id = channel.id
                else:
                    diagnostics.append("unknown_channel")
                    errors += 1

            sku_raw = _clean_str(payload.get("sku_raw"))
            part_number_raw = _clean_str(payload.get("part_number_raw"))
            model_raw = _clean_str(payload.get("model_raw"))
            if not (sku_raw or part_number_raw or model_raw):
                # No product identity token at all.
                if "missing_key_fields" not in diagnostics:
                    diagnostics.append("missing_key_fields")
                errors += 1
            else:
                # 5-step precedence: each step only runs when product_id is still unresolved.
                # 1. Exact SKU match.
                if sku_raw and not product_id:
                    _p = product_by_sku.get(sku_raw.lower())
                    if _p:
                        product_id = _p.id
                # 2. SKU-field value tried as part_number (NB-style workbooks put part_no
                #    in a "Part Number" column that canonical aliases bind to sku_raw).
                if sku_raw and not product_id:
                    _p = product_by_part_number.get(sku_raw.lower())
                    if _p:
                        product_id = _p.id
                # 3. Explicit part_number_raw column.
                if part_number_raw and not product_id:
                    _p = product_by_part_number.get(part_number_raw.lower())
                    if _p:
                        product_id = _p.id
                # 4. Unique model_name / sales_model_name (within-field duplicates excluded
                #    at dict-build time above).
                #    Cross-field guard: if model_raw resolves to product A via model_name
                #    AND to a *different* product B via sales_model_name, do not silently
                #    choose — emit ambiguous_product_match and skip the ILIKE step.
                #    If both dicts point to the *same* product, resolve it normally.
                _step4_diagnosed = False
                if model_raw and not product_id:
                    _by_model = product_by_model_name.get(model_raw.lower())
                    _by_sales = product_by_sales_model_name.get(model_raw.lower())
                    if _by_model and _by_sales and _by_model.id != _by_sales.id:
                        # Same token uniquely identifies two different products across fields.
                        diagnostics.append("ambiguous_product_match")
                        errors += 1
                        _step4_diagnosed = True
                    elif _by_model or _by_sales:
                        product_id = (_by_model or _by_sales).id
                # 5. ILIKE fallback — only resolves when exactly one product matches.
                #    Searches name, sku, part_number, model_name, and sales_model_name
                #    (nullable fields are safe in SQL OR — NULL never matches).
                #    Skipped when step 4 already emitted a terminal diagnostic.
                if not product_id and not _step4_diagnosed:
                    _ilike_tok = sku_raw or part_number_raw or model_raw
                    _ambiguous = db.scalars(
                        select(DimProduct).where(
                            or_(
                                DimProduct.name.ilike(f"%{_ilike_tok}%"),
                                DimProduct.sku.ilike(f"%{_ilike_tok}%"),
                                DimProduct.part_number.ilike(f"%{_ilike_tok}%"),
                                DimProduct.model_name.ilike(f"%{_ilike_tok}%"),
                                DimProduct.sales_model_name.ilike(f"%{_ilike_tok}%"),
                            )
                        )
                    ).all()
                    if len(_ambiguous) == 1:
                        product_id = _ambiguous[0].id
                        diagnostics.append("product_matched_by_ilike")
                    elif len(_ambiguous) > 1:
                        diagnostics.append("ambiguous_product_match")
                        errors += 1
                    else:
                        diagnostics.append("unknown_product")
                        errors += 1

            numeric_fields = [
                "msrp_local",
                "promo_price_local",
                "quantity_units",
                "dap_local",
                "actual_dap_local",
                "disti_cost_local",
                "disti_margin_pct",
                "rebate_pct",
                "dealer_margin_pct",
                "vat_pct",
            ]
            parsed_numeric: dict[str, Decimal | None] = {}
            for field in numeric_fields:
                parsed_numeric[field] = _parse_decimal(payload.get(field))
                if parsed_numeric[field] is None and _clean_str(payload.get(field)):
                    if field == "quantity_units":
                        # qty failure was already flagged in the parse pass; avoid double-count.
                        if "invalid_quantity" not in diagnostics:
                            diagnostics.append("invalid_quantity")
                            errors += 1
                    else:
                        # Optional commercial fields: flag but keep severity at warning.
                        diagnostics.append("invalid_numeric")
                        errors += 1

            per = _parse_period_start(payload.get("period_start") or payload.get("period_label"))
            if payload.get("period_start") and per is None:
                diagnostics.append("invalid_date")
                errors += 1

            if parsed.status == "dropped":
                severity = "info"
            elif any(code in diagnostics for code in ("missing_key_fields", "unknown_product", "invalid_quantity")):
                severity = "error"

            # code: prefer the first error-level diagnostic so the UI primary code reflects
            # the actual blocker (e.g. unknown_product beats partial_margin_stack even when
            # partial_margin_stack was appended first during the parse pass).
            primary_code = (
                next((d for d in diagnostics if d in _ERROR_LEVEL_CODES), None)
                or (diagnostics[0] if diagnostics else "historical_lineup_row_ok")
            )
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=parsed.row_number,
                    severity=severity,
                    code=primary_code,
                    message="; ".join(diagnostics) if diagnostics else "row accepted",
                    raw_payload=parsed.payload,
                )
            )

            if job.import_mode == "apply" and header is not None and parsed.status != "dropped":
                db.add(
                    HistoricalLineupImportLine(
                        header_id=header.id,
                        source_row_number=parsed.row_number,
                        product_id=product_id,
                        sku_raw=sku_raw,
                        part_number_raw=part_number_raw,
                        model_raw=model_raw,
                        base_unit_raw=_clean_str(payload.get("base_unit_raw")),
                        msrp_local=parsed_numeric["msrp_local"],
                        promo_price_local=parsed_numeric["promo_price_local"],
                        quantity_units=parsed_numeric["quantity_units"],
                        month_split_json=None,
                        dap_local=parsed_numeric["dap_local"],
                        actual_dap_local=parsed_numeric["actual_dap_local"],
                        disti_cost_local=parsed_numeric["disti_cost_local"],
                        disti_margin_pct=parsed_numeric["disti_margin_pct"],
                        rebate_pct=parsed_numeric["rebate_pct"],
                        dealer_margin_pct=parsed_numeric["dealer_margin_pct"],
                        vat_pct=parsed_numeric["vat_pct"],
                        customer_feedback=_clean_str(payload.get("customer_feedback")),
                        workflow_notes=_clean_str(payload.get("workflow_notes")),
                        row_status="accepted" if severity != "error" else "error",
                        mapping_confidence=parsed.confidence,
                        diagnostic_codes=diagnostics,
                        raw_row_payload=payload,
                    )
                )

    if not parsed_sheets:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="no_candidate_sheets",
                message=(
                    "Workbook did not contain candidate historical lineup sheets. "
                    f"Skipped: {[x.get('sheet_name') for x in schema.get('skipped_sheet_details', [])]}."
                ),
            )
        )
        return 1

    db.add(
        ImportRowResult(
            job_id=job.id,
            row_number=0,
            severity="info",
            code="historical_lineup_processed",
            message=f"Processed {len(parsed_sheets)} sheet(s) in {job.import_mode} mode.",
            raw_payload=schema,
        )
    )
    return errors
