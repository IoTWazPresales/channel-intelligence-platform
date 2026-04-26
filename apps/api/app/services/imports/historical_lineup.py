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
    "customer_token": ["customer", "customer_code", "account", "account_name", "end customer"],
    "distributor_token": ["distributor", "disti", "distributor_code", "partner"],
    "channel_token": ["channel", "route_to_market", "rtm"],
    "period_label": ["period", "month", "quarter", "fiscal"],
    "period_start": ["period_start", "start_date", "date"],
    "country_code": ["country", "country_code"],
    "currency_code": ["currency", "currency_code"],
    "sku_raw": ["sku", "item", "product_sku", "base_unit"],
    "part_number_raw": ["part_number", "mpn", "part no", "part number"],
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
    matched_aliases = 0
    total_aliases = 0
    for target, opts in _CANONICAL_ALIASES.items():
        total_aliases += 1
        for alias in opts:
            actual = normalized_cols.get(_norm_token(alias))
            if actual:
                mapping[target] = actual
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


def parse_historical_workbook(filename: str, raw_bytes: bytes) -> tuple[list[ParsedSheet], dict[str, Any]]:
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
    parsed_sheets, schema = parse_historical_workbook(filename, raw_bytes)
    job.inferred_schema = schema
    job.field_mapping = {s.sheet_name: s.mapping for s in parsed_sheets}
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
                # 4. Unique model_name / sales_model_name (ambiguous entries excluded at
                #    dict-build time above).
                if model_raw and not product_id:
                    _p = product_by_model_name.get(model_raw.lower()) or product_by_sales_model_name.get(
                        model_raw.lower()
                    )
                    if _p:
                        product_id = _p.id
                # 5. ILIKE fallback — only resolves when exactly one match exists.
                if not product_id:
                    _ilike_tok = sku_raw or part_number_raw or model_raw
                    _ambiguous = db.scalars(
                        select(DimProduct).where(
                            or_(
                                DimProduct.name.ilike(f"%{_ilike_tok}%"),
                                DimProduct.sku.ilike(f"%{_ilike_tok}%"),
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

            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=parsed.row_number,
                    severity=severity,
                    code=diagnostics[0] if diagnostics else "historical_lineup_row_ok",
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
