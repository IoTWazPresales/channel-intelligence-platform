# Plan (Phase 1a flat parser):
# - Pattern: shipment_evidence reads bytes + sheet scan; product_master uses read_tabular +
#   column mapping. This module is parser-only (ParseResult, no DB).
# - Header: score first 10 rows against template aliases + job field_mapping keys.
# - Columns: job field_mapping overrides template expected_columns aliases.
# - Period: column date → filename range → single date → week number → None + warning.
# - No retailer/customer names in code — aliases come from mapping/template only.

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd

from app.services.imports.cst_d1 import apply_listing_seed_fields
from app.services.imports.parsers.customer_sell_through_measures import (
    apply_unit_total_derivation,
    apply_unit_total_derivation_many,
)
from app.utils.json_safe import to_jsonable

# Internal key for template aliases passed from pipeline handler (not a file column).
EXPECTED_COLUMNS_META_KEY = "__expected_columns__"

CANONICAL_FIELDS = (
    "raw_product_token",
    "raw_location_token",
    "raw_period_ref",
    "units_sold",
    "unit_sell_price",
    "unit_cost",
    "unit_mac",
    "reported_soh",
    "raw_article_token",
    "listing_external_id",
    "listing_marketplace",
    # Optional line totals — derived to/from unit fields via units_sold / reported_soh.
    "total_sell_amount",
    "total_cost_amount",
    "total_soh_value",
)

# Import-template / steward keys historically used synonyms; parsers resolve CANONICAL_FIELDS.
_TEMPLATE_KEY_TO_CANONICAL = {
    "product_identifier": "raw_product_token",
    "location_token": "raw_location_token",
    "period_ref": "raw_period_ref",
}

_PERIOD_RANGE_RE = re.compile(r"(\d{8})[_\-\s]+(\d{8})")
_PERIOD_SINGLE_RE = re.compile(r"(\d{8})")
_WEEK_RE = re.compile(r"week[\s_]*(\d{1,2})|w(\d{1,2})", re.IGNORECASE)
_ISO_WEEK_RE = re.compile(r"(\d{4})-W(\d{1,2})", re.IGNORECASE)


@dataclass
class ParseResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    period_start_date: date | None = None
    period_type: str = "weekly"
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def _normalize_text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1].strip()
    elif s.startswith("='") and s.endswith("'"):
        s = s[2:-1].strip()
    else:
        while s and s[0] in ("=", "'", '"'):
            s = s[1:].lstrip()
        if s.endswith('"') and s.count('"') == 1:
            s = s[:-1].rstrip()
    s = s.strip()
    return s if s and s.lower() != "nan" else None


def _parse_decimal(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = _normalize_text(value)
    if not s:
        return None
    # Takealot / ZA currency cells: "R  1 486.00", "R1,999.00"
    s = s.replace(",", "")
    s = re.sub(r"^[^\d\-]+", "", s)
    s = re.sub(r"\s+", "", s)
    if not s or s in {".", "-", "-."}:
        return None
    try:
        return float(Decimal(s))
    except (InvalidOperation, ValueError):
        return None


def _alias_folds(alias: str) -> set[str]:
    """Match 'Transaction Week' to alias 'transaction_week' (and the reverse)."""
    a = alias.strip().lower()
    if not a:
        return set()
    return {a, a.replace("_", " "), a.replace(" ", "_")}


def normalize_cst_expected_columns(expected_columns: dict[str, Any] | None) -> dict[str, Any]:
    """Map template synonym keys onto parser CANONICAL_FIELDS and merge aliases."""
    out: dict[str, Any] = {}
    for key, meta in (expected_columns or {}).items():
        if not isinstance(meta, dict):
            continue
        canon = _TEMPLATE_KEY_TO_CANONICAL.get(str(key), str(key))
        aliases: list[str] = []
        seen: set[str] = set()
        for a in meta.get("aliases") or []:
            if not isinstance(a, str) or not a.strip():
                continue
            low = a.strip().lower()
            if low in seen:
                continue
            aliases.append(a.strip())
            seen.add(low)
        if canon in out and isinstance(out[canon], dict):
            existing = list(out[canon].get("aliases") or [])
            for a in aliases:
                low = a.lower()
                if low not in {str(x).lower() for x in existing}:
                    existing.append(a)
            merged = dict(out[canon])
            merged["aliases"] = existing
            if meta.get("required"):
                merged["required"] = True
            out[canon] = merged
        else:
            out[canon] = {
                "aliases": aliases,
                "required": bool(meta.get("required", False)),
            }
    return out


def _aliases_for_canonical(
    canonical: str,
    field_mapping: dict[str, str],
    expected_columns: dict[str, Any],
) -> list[str]:
    """Ordered alias folds — first match wins when resolving source columns."""
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        for fold in _alias_folds(raw):
            if fold not in seen:
                ordered.append(fold)
                seen.add(fold)

    for src_col, tgt in field_mapping.items():
        if src_col == EXPECTED_COLUMNS_META_KEY:
            continue
        if tgt == canonical:
            _add(str(src_col))
    meta = expected_columns.get(canonical)
    if isinstance(meta, dict):
        for a in meta.get("aliases") or []:
            if isinstance(a, str) and a.strip():
                _add(a)
    _add(canonical)
    return ordered


def _build_alias_index(
    field_mapping: dict[str, str],
    expected_columns: dict[str, Any],
) -> dict[str, set[str]]:
    expected = normalize_cst_expected_columns(expected_columns)
    return {
        c: set(_aliases_for_canonical(c, field_mapping, expected))
        for c in CANONICAL_FIELDS
    }


# Identity canons outweigh repeated measure hits (Game 2026 week band = 6× "Sales U TY").
_HEADER_IDENTITY_CANONS = frozenset(
    {"raw_product_token", "raw_location_token", "raw_article_token", "listing_external_id"}
)


def _score_header_row(row_values: list[Any], alias_index: dict[str, set[str]]) -> int:
    """Score by distinct canonical coverage — not per-cell hits.

    Repeated measure labels (``Sales U TY`` × N) must not beat a dimension row
    that only hits Article + Site once each.
    """
    hit_canons: set[str] = set()
    for cell in row_values:
        norm = _normalize_text(cell)
        if not norm:
            continue
        key = norm.lower()
        for canon, aliases in alias_index.items():
            if key in aliases:
                hit_canons.add(canon)
                break
    score = len(hit_canons)
    for canon in hit_canons:
        if canon in _HEADER_IDENTITY_CANONS:
            score += 2
    return score


def _detect_header_row(df_raw: pd.DataFrame, alias_index: dict[str, set[str]]) -> int | None:
    best_row: int | None = None
    best_score = 0
    limit = min(10, len(df_raw))
    for i in range(limit):
        row = df_raw.iloc[i].tolist()
        score = _score_header_row(row, alias_index)
        if score > best_score:
            best_score = score
            best_row = i
    if best_row is None or best_score < 2:
        return None
    return best_row


def _excel_engine_for_filename(filename: str) -> str | None:
    """Pandas Excel engine for CST workbooks — same contract as DSI (openpyxl / xlrd)."""
    lower = (filename or "").lower()
    if lower.endswith((".xlsx", ".xlsm")):
        return "openpyxl"
    if lower.endswith(".xls"):
        return "xlrd"
    return None


def _read_workbook_sheets(file_bytes: bytes, filename: str) -> list[tuple[str, pd.DataFrame]]:
    lower = (filename or "").lower()
    bio = io.BytesIO(file_bytes)
    if lower.endswith(".csv"):
        return [("Sheet1", pd.read_csv(bio, header=None, dtype=object))]
    engine = _excel_engine_for_filename(filename)
    if engine is not None:
        book = pd.ExcelFile(bio, engine=engine)
        return [
            (name, pd.read_excel(book, sheet_name=name, header=None, dtype=object))
            for name in book.sheet_names
        ]
    raise ValueError("Unsupported file type; use .csv, .xlsx, .xlsm, or .xls")


# Currency / UOM stubs that sit under measure labels in SAP dual-header exports.
_WEAK_HEADER_RE = re.compile(
    r"^(zar|usd|eur|gbp|r|\$|%|ea|each|uom|pc|pcs|unit)$",
    re.IGNORECASE,
)
# Period-band titles / week codes — not measure names; never promote into blank/weak cells.
_PERIOD_BAND_RE = re.compile(
    r"^(fiscal week|calendar day|calendar week|\d{3}\.\d{4}|\d{4}-w\d{1,2})$",
    re.IGNORECASE,
)


def _is_period_band_label(text: str | None) -> bool:
    if not text:
        return False
    return bool(_PERIOD_BAND_RE.match(text.strip()))


def _merge_dual_header_labels(raw_df: pd.DataFrame, header_row: int) -> list[str]:
    """Fill blank/weak header cells from prior rows (Game WEEK dual-/triple-header).

    Curr wins when it is a real label. Immediate prior wins for blanks.
    Any prior row may replace a weak currency/UOM stub (``ZAR``, ``EA``) with a
    measure label (``Sales R TY`` / ``Sales U TY``) — never a period-band title.

    Duplicate measure names are disambiguated from higher period-band rows
    (e.g. Fiscal Week codes ``027.2026``); the rightmost duplicate keeps the
    bare measure label so existing field_mapping aliases still resolve.
    """
    curr = [_normalize_text(c) for c in raw_df.iloc[header_row].tolist()]
    width = len(curr)
    prior_rows: list[list[str | None]] = []
    for r in range(header_row - 1, -1, -1):
        prior_rows.append([_normalize_text(c) for c in raw_df.iloc[r].tolist()])
    immediate = prior_rows[0] if prior_rows else []
    out: list[str] = []
    for i in range(width):
        c = curr[i] if i < len(curr) else None
        priors_at_i = [(row[i] if i < len(row) else None) for row in prior_rows]
        imm = immediate[i] if i < len(immediate) else None
        chosen: str | None = None
        if c and not _WEAK_HEADER_RE.match(c):
            chosen = c
        elif c and _WEAK_HEADER_RE.match(c):
            for p in priors_at_i:
                if not p or _WEAK_HEADER_RE.match(p) or _is_period_band_label(p):
                    continue
                chosen = p
                break
            if chosen is None:
                chosen = c
        else:
            # Blank: only the immediate prior (avoids pulling Fiscal Week into desc cols).
            if imm and not _is_period_band_label(imm):
                chosen = imm
        out.append(chosen or f"col_{i}")

    return _disambiguate_duplicate_headers(out, prior_rows)


def _disambiguate_duplicate_headers(
    headers: list[str],
    prior_rows: list[list[str | None]],
) -> list[str]:
    """Make duplicate labels unique using period-band values; bare name stays on last hit."""
    counts: dict[str, int] = {}
    for h in headers:
        counts[h] = counts.get(h, 0) + 1
    dup_names = {h for h, n in counts.items() if n > 1 and not h.startswith("col_")}
    if not dup_names:
        return headers

    last_index: dict[str, int] = {}
    for i, h in enumerate(headers):
        if h in dup_names:
            last_index[h] = i

    out = list(headers)
    for i, h in enumerate(headers):
        if h not in dup_names:
            continue
        if last_index.get(h) == i:
            continue  # keep bare measure label on rightmost week column
        band: str | None = None
        for row in prior_rows:
            if i >= len(row):
                continue
            cell = row[i]
            if not cell or cell.lower() == h.lower():
                continue
            if _WEAK_HEADER_RE.match(cell):
                continue
            band = cell
            break
        if band:
            out[i] = f"{h} {band}"
        else:
            out[i] = f"{h}__{i}"
    return out


def _apply_feed_row_filters(df: pd.DataFrame, feed_profile: dict[str, Any] | None) -> pd.DataFrame:
    """Optional equality filters from feed_profile.row_filters: [{column, equals}, ...]."""
    if df is None or df.empty or not isinstance(feed_profile, dict):
        return df
    filters = feed_profile.get("row_filters")
    if not isinstance(filters, list) or not filters:
        return df
    out = df
    col_lower = {str(c).strip().lower(): str(c) for c in out.columns}
    for spec in filters:
        if not isinstance(spec, dict):
            continue
        col_name = spec.get("column")
        equals = spec.get("equals")
        if not col_name or equals is None:
            continue
        src = col_lower.get(str(col_name).strip().lower())
        if src is None:
            continue
        want = str(equals).strip().lower()
        mask = out[src].map(lambda v: (_normalize_text(v) or "").lower() == want)
        out = out.loc[mask].reset_index(drop=True)
    return out


def _select_sheet_with_header(
    file_bytes: bytes,
    filename: str,
    alias_index: dict[str, set[str]],
    *,
    feed_profile: dict[str, Any] | None = None,
    preferred_sheet_names: list[str] | None = None,
) -> tuple[pd.DataFrame, int] | tuple[None, None]:
    sheets = _read_workbook_sheets(file_bytes, filename)
    prefer = {str(n).strip().lower() for n in (preferred_sheet_names or []) if n}
    ordered = sheets
    if prefer:
        ordered = sorted(
            sheets,
            key=lambda pair: (0 if str(pair[0]).strip().lower() in prefer else 1, str(pair[0])),
        )
    dual = bool(isinstance(feed_profile, dict) and feed_profile.get("dual_header_merge"))
    for _name, raw_df in ordered:
        if raw_df is None or raw_df.empty:
            continue
        header_row = _detect_header_row(raw_df, alias_index)
        if header_row is not None:
            if dual:
                headers = _merge_dual_header_labels(raw_df, header_row)
            else:
                headers = [_normalize_text(c) or f"col_{i}" for i, c in enumerate(raw_df.iloc[header_row].tolist())]
            body = raw_df.iloc[header_row + 1 :].copy()
            body.columns = headers
            body = body.reset_index(drop=True)
            body = _apply_feed_row_filters(body, feed_profile)
            return body, header_row + 2
    return None, None


def _resolve_source_columns(
    columns: list[str],
    field_mapping: dict[str, str],
    expected_columns: dict[str, Any],
) -> dict[str, str | None]:
    """Map canonical field -> source column name in the dataframe."""
    expected = normalize_cst_expected_columns(expected_columns)
    col_lower = {str(c).strip().lower(): str(c) for c in columns}
    resolved: dict[str, str | None] = {c: None for c in CANONICAL_FIELDS}

    for src, canon in field_mapping.items():
        if src == EXPECTED_COLUMNS_META_KEY:
            continue
        if canon in resolved and src.strip().lower() in col_lower:
            resolved[canon] = col_lower[src.strip().lower()]

    for canon in CANONICAL_FIELDS:
        if resolved[canon] is not None:
            continue
        for alias in _aliases_for_canonical(canon, field_mapping, expected):
            if alias in col_lower:
                resolved[canon] = col_lower[alias]
                break
    return resolved


def _first_matching_column(col_lower: dict[str, str], alias_names: list[str]) -> str | None:
    for name in alias_names:
        for fold in _alias_folds(name):
            if fold in col_lower:
                return col_lower[fold]
    return None


def enrich_flat_rows_from_companion_soh(
    file_bytes: bytes,
    filename: str,
    rows: list[dict[str, Any]],
    feed_profile: dict[str, Any] | None,
    warnings: list[str],
) -> list[dict[str, Any]]:
    """Fill missing sell/cost/SOH from a companion SOH sheet described by feed_profile.

    Takealot WEEK workbooks carry qty on the sales sheet and prices/SOH on ``soh``.
    Join key defaults to barcode (override via ``soh_join_columns``).
    """
    if not rows or not isinstance(feed_profile, dict):
        return rows
    soh_names = {
        str(n).strip().lower()
        for n in (feed_profile.get("soh_sheet_names") or [])
        if isinstance(n, str) and n.strip()
    }
    if not soh_names:
        return rows

    join_names = [
        str(n)
        for n in (
            feed_profile.get("soh_join_columns")
            or ["barcode", "ean/upc", "ean", "article"]
        )
        if n
    ]
    cost_names = [
        str(n)
        for n in (feed_profile.get("soh_cost_columns") or ["Cost Price", "Weighted Average Cost Price"])
        if n
    ]
    sell_names = [
        str(n)
        for n in (feed_profile.get("soh_sell_price_columns") or ["Selling Price Inc", "List Price Inc"])
        if n
    ]
    soh_qty_names = [
        str(n)
        for n in (feed_profile.get("soh_qty_columns") or ["Qty Sellable", "total_sellable_soh", "soh"])
        if n
    ]
    soh_cost_total_names = [str(n) for n in (feed_profile.get("soh_cost_total_columns") or []) if n]
    soh_sell_total_names = [str(n) for n in (feed_profile.get("soh_sell_total_columns") or []) if n]
    dual = bool(feed_profile.get("dual_header_merge"))

    soh_body: pd.DataFrame | None = None
    try:
        sheets = _read_workbook_sheets(file_bytes, filename)
    except ValueError:
        warnings.append("Companion SOH enrichment skipped: unsupported workbook type")
        return rows

    for name, raw_df in sheets:
        if raw_df is None or raw_df.empty:
            continue
        if str(name).strip().lower() not in soh_names:
            continue
        # Prefer a header that includes the join column; fall back to row 0.
        header_idx = 0
        for i in range(min(5, len(raw_df))):
            cells = [_normalize_text(c) or "" for c in raw_df.iloc[i].tolist()]
            lowers = {c.lower() for c in cells if c}
            if any(fold in lowers for jn in join_names for fold in _alias_folds(jn)):
                header_idx = i
                break
        if dual:
            headers = _merge_dual_header_labels(raw_df, header_idx)
        else:
            headers = [_normalize_text(c) or f"col_{i}" for i, c in enumerate(raw_df.iloc[header_idx].tolist())]
        body = raw_df.iloc[header_idx + 1 :].copy()
        body.columns = headers
        soh_body = body.reset_index(drop=True)
        break

    if soh_body is None or soh_body.empty:
        warnings.append("Companion SOH sheet not found for price enrichment")
        return rows

    col_lower = {str(c).strip().lower(): str(c) for c in soh_body.columns}
    join_col = _first_matching_column(col_lower, join_names)
    if join_col is None:
        warnings.append("Companion SOH enrichment skipped: join column not found")
        return rows
    cost_col = _first_matching_column(col_lower, cost_names)
    sell_col = _first_matching_column(col_lower, sell_names)
    soh_col = _first_matching_column(col_lower, soh_qty_names)
    cost_total_col = _first_matching_column(col_lower, soh_cost_total_names) if soh_cost_total_names else None
    sell_total_col = _first_matching_column(col_lower, soh_sell_total_names) if soh_sell_total_names else None

    by_token: dict[str, dict[str, float | None]] = {}
    for pos in range(len(soh_body)):
        series = soh_body.iloc[pos]
        tok = _normalize_text(series.get(join_col))
        if not tok:
            continue
        key = tok.strip().lower()
        if key in by_token:
            continue
        hit: dict[str, float | None] = {
            "unit_cost": _parse_decimal(series.get(cost_col)) if cost_col else None,
            "unit_sell_price": _parse_decimal(series.get(sell_col)) if sell_col else None,
            "reported_soh": _parse_decimal(series.get(soh_col)) if soh_col else None,
            # Sales-line totals only — not SOH sheet value (that would divide by sell qty).
            "total_cost_amount": None,
            "total_sell_amount": _parse_decimal(series.get(sell_total_col)) if sell_total_col else None,
            "total_soh_value": _parse_decimal(series.get(cost_total_col)) if cost_total_col else None,
        }
        by_token[key] = hit

    if not by_token:
        warnings.append("Companion SOH enrichment found no join keys")
        return rows

    filled = 0
    for row in rows:
        candidates: list[str] = []
        tok = _normalize_text(row.get("raw_product_token"))
        if tok:
            candidates.append(tok.strip().lower())
        payload = row.get("raw_row_payload")
        if isinstance(payload, dict):
            for key in ("Barcode", "barcode", "EAN", "ean", "EAN/UPC"):
                alt = _normalize_text(payload.get(key))
                if alt:
                    candidates.append(alt.strip().lower())
        hit = None
        for key in candidates:
            hit = by_token.get(key)
            if hit:
                break
        if not hit:
            continue
        changed = False
        if row.get("unit_cost") is None and hit.get("unit_cost") is not None:
            row["unit_cost"] = hit["unit_cost"]
            changed = True
        if row.get("unit_sell_price") is None and hit.get("unit_sell_price") is not None:
            row["unit_sell_price"] = hit["unit_sell_price"]
            changed = True
        if row.get("reported_soh") is None and hit.get("reported_soh") is not None:
            row["reported_soh"] = hit["reported_soh"]
            changed = True
        if row.get("total_cost_amount") is None and hit.get("total_cost_amount") is not None:
            row["total_cost_amount"] = hit["total_cost_amount"]
            changed = True
        if row.get("total_sell_amount") is None and hit.get("total_sell_amount") is not None:
            row["total_sell_amount"] = hit["total_sell_amount"]
            changed = True
        if row.get("total_soh_value") is None and hit.get("total_soh_value") is not None:
            row["total_soh_value"] = hit["total_soh_value"]
            changed = True
        if changed:
            filled += 1

    if filled:
        warnings.append(f"Companion SOH enriched {filled} sales row(s) with price/SOH")
    else:
        warnings.append("Companion SOH present but no sales rows matched on join key")
    return rows


def _monday_of_week(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _parse_date_value(value: Any) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return _monday_of_week(value.date())
    if isinstance(value, date):
        return _monday_of_week(value)
    s = _normalize_text(value)
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d"):
        try:
            return _monday_of_week(datetime.strptime(s[:10], fmt).date())
        except ValueError:
            continue
    try:
        parsed = pd.to_datetime(s, errors="coerce")
        if pd.isna(parsed):
            return None
        return _monday_of_week(parsed.date())
    except Exception:
        return None


def _parse_yyyymmdd(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def _extract_period(
    *,
    filename: str,
    period_col: str | None,
    df: pd.DataFrame,
    warnings: list[str],
) -> date | None:
    if period_col and period_col in df.columns:
        for val in df[period_col].tolist():
            d = _parse_date_value(val)
            if d is not None:
                return d

    base = filename or ""
    m_range = _PERIOD_RANGE_RE.search(base)
    if m_range:
        d0 = _parse_yyyymmdd(m_range.group(1))
        if d0 is not None:
            return d0

    singles = _PERIOD_SINGLE_RE.findall(base)
    if len(singles) == 1:
        d = _parse_yyyymmdd(singles[0])
        if d is not None:
            return _monday_of_week(d)

    m_week = _WEEK_RE.search(base)
    if m_week:
        week_no = int(m_week.group(1) or m_week.group(2))
        year = date.today().year
        try:
            return date.fromisocalendar(year, week_no, 1)
        except ValueError:
            pass

    if period_col and period_col in df.columns:
        for val in df[period_col].tolist():
            text = _normalize_text(val)
            if not text:
                continue
            m_iso = _ISO_WEEK_RE.search(text)
            if m_iso:
                try:
                    return date.fromisocalendar(int(m_iso.group(1)), int(m_iso.group(2)), 1)
                except ValueError:
                    pass
            m = _WEEK_RE.search(text)
            if m:
                week_no = int(m.group(1) or m.group(2))
                try:
                    return date.fromisocalendar(date.today().year, week_no, 1)
                except ValueError:
                    pass

    warnings.append("Period could not be extracted from file or filename — manual entry required")
    return None


def _row_dict(series: pd.Series) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in series.items():
        out[str(k)] = to_jsonable(v)
    return out


def parse_flat_report(
    file_bytes: bytes,
    filename: str,
    field_mapping: dict,
    job_id: int,
    *,
    feed_profile: dict[str, Any] | None = None,
) -> ParseResult:
    """Parse a single-sheet flat sell-through file into staging-ready row dicts."""
    fm = dict(field_mapping or {})
    expected_columns = fm.pop(EXPECTED_COLUMNS_META_KEY, None)
    if not isinstance(expected_columns, dict):
        expected_columns = {}
    expected_columns = normalize_cst_expected_columns(expected_columns)

    alias_index = _build_alias_index(fm, expected_columns)
    prefer_sheets = None
    if isinstance(feed_profile, dict):
        raw_pref = feed_profile.get("sales_sheet_names") or feed_profile.get("preferred_sheet_names")
        if isinstance(raw_pref, list):
            prefer_sheets = [str(x) for x in raw_pref if x]
    try:
        df, first_data_row = _select_sheet_with_header(
            file_bytes,
            filename,
            alias_index,
            feed_profile=feed_profile,
            preferred_sheet_names=prefer_sheets,
        )
    except ValueError as exc:
        return ParseResult(error=str(exc))

    if df is None:
        return ParseResult(error="Could not detect header row")

    col_map = _resolve_source_columns(list(df.columns), fm, expected_columns)
    available = [str(c) for c in df.columns]

    if col_map["raw_product_token"] is None:
        return ParseResult(
            error=f"Required field product identifier could not be mapped. Available columns: {available}"
        )

    warnings: list[str] = []
    period_start = _extract_period(
        filename=filename,
        period_col=col_map["raw_period_ref"],
        df=df,
        warnings=warnings,
    )

    units_aliases = list(_aliases_for_canonical("units_sold", fm, expected_columns))
    # Include mapped source header so dual-header bare measure always matches.
    if col_map.get("units_sold"):
        units_aliases.append(str(col_map["units_sold"]))
    # Lazy import: period ↔ flat share helpers; avoid circular import at module load.
    from app.services.imports.parsers.customer_sell_through_period import (
        detect_wide_week_unit_columns,
    )

    week_unit_cols = detect_wide_week_unit_columns(
        available,
        units_aliases=units_aliases,
        focus_period=period_start,
    )
    if len(week_unit_cols) >= 2:
        return _parse_flat_wide_week_unpivot(
            df,
            first_data_row=first_data_row,
            col_map=col_map,
            week_unit_cols=week_unit_cols,
            job_id=job_id,
            feed_profile=feed_profile,
            warnings=warnings,
            file_bytes=file_bytes,
            filename=filename,
        )

    if col_map["units_sold"] is None:
        return ParseResult(
            error=f"Required field units_sold could not be mapped. Available columns: {available}",
            warnings=warnings,
        )

    rows: list[dict[str, Any]] = []
    skipped = 0
    for pos in range(len(df)):
        series = df.iloc[pos]
        source_row_number = first_data_row + pos
        units = _parse_decimal(series.get(col_map["units_sold"])) if col_map["units_sold"] else None
        product_tok = _normalize_text(series.get(col_map["raw_product_token"])) if col_map["raw_product_token"] else None
        if units is None or product_tok is None:
            skipped += 1
            continue

        period_ref = None
        if col_map["raw_period_ref"]:
            period_ref = _normalize_text(series.get(col_map["raw_period_ref"]))
        row_period = _parse_date_value(series.get(col_map["raw_period_ref"])) if col_map["raw_period_ref"] else None
        eff_period = row_period or period_start

        loc_tok = None
        if col_map["raw_location_token"]:
            loc_tok = _normalize_text(series.get(col_map["raw_location_token"]))

        row = {
            "import_job_id": int(job_id),
            "source_row_number": int(source_row_number),
            "raw_row_payload": _row_dict(series),
            "raw_customer_token": None,
            "raw_location_token": loc_tok,
            "site_label": loc_tok,
            "raw_product_token": product_tok,
            "raw_period_ref": period_ref,
            "period_start_date": eff_period,
            "period_type": "weekly",
            "units_sold": units,
            "raw_mtd_units": None,
            "is_mtd_estimate": False,
            "unit_sell_price": _parse_decimal(series.get(col_map["unit_sell_price"]))
            if col_map["unit_sell_price"]
            else None,
            "unit_cost": _parse_decimal(series.get(col_map["unit_cost"])) if col_map["unit_cost"] else None,
            "unit_mac": _parse_decimal(series.get(col_map["unit_mac"])) if col_map.get("unit_mac") else None,
            "reported_soh": _parse_decimal(series.get(col_map["reported_soh"]))
            if col_map["reported_soh"]
            else None,
            "total_sell_amount": _parse_decimal(series.get(col_map["total_sell_amount"]))
            if col_map.get("total_sell_amount")
            else None,
            "total_cost_amount": _parse_decimal(series.get(col_map["total_cost_amount"]))
            if col_map.get("total_cost_amount")
            else None,
            "total_soh_value": _parse_decimal(series.get(col_map["total_soh_value"]))
            if col_map.get("total_soh_value")
            else None,
            "raw_article_token": _normalize_text(series.get(col_map["raw_article_token"]))
            if col_map.get("raw_article_token")
            else None,
            "listing_external_id": _normalize_text(series.get(col_map["listing_external_id"]))
            if col_map.get("listing_external_id")
            else None,
            "listing_marketplace": _normalize_text(series.get(col_map["listing_marketplace"]))
            if col_map.get("listing_marketplace")
            else None,
            "resolution_status": "pending",
        }
        apply_listing_seed_fields(row, feed_profile)
        rows.append(row)

    if skipped:
        warnings.append(f"Skipped {skipped} row(s) with missing product token or units_sold")

    rows = enrich_flat_rows_from_companion_soh(
        file_bytes,
        filename,
        rows,
        feed_profile,
        warnings,
    )
    # After companion SOH may attach totals/MAC — derive unit↔total once.
    rows = apply_unit_total_derivation_many(rows)

    return ParseResult(
        rows=rows,
        period_start_date=period_start,
        period_type="weekly",
        warnings=warnings,
        error=None,
    )


def _parse_flat_wide_week_unpivot(
    df: pd.DataFrame,
    *,
    first_data_row: int,
    col_map: dict[str, str | None],
    week_unit_cols: list[tuple[str, date, str]],
    job_id: int,
    feed_profile: dict[str, Any] | None,
    warnings: list[str],
    file_bytes: bytes,
    filename: str,
) -> ParseResult:
    """Emit one staging row per product×week when dual-header exposes multiple unit weeks."""
    latest_period = max((p for _, p, _ in week_unit_cols), default=None)
    rows: list[dict[str, Any]] = []
    skipped_products = 0

    for pos in range(len(df)):
        series = df.iloc[pos]
        source_row_number = first_data_row + pos
        product_tok = (
            _normalize_text(series.get(col_map["raw_product_token"])) if col_map["raw_product_token"] else None
        )
        if not product_tok:
            skipped_products += 1
            continue

        loc_tok = None
        if col_map["raw_location_token"]:
            loc_tok = _normalize_text(series.get(col_map["raw_location_token"]))

        unit_cost = _parse_decimal(series.get(col_map["unit_cost"])) if col_map["unit_cost"] else None
        unit_mac = _parse_decimal(series.get(col_map["unit_mac"])) if col_map.get("unit_mac") else None
        unit_sell = (
            _parse_decimal(series.get(col_map["unit_sell_price"])) if col_map["unit_sell_price"] else None
        )
        soh_val = _parse_decimal(series.get(col_map["reported_soh"])) if col_map["reported_soh"] else None
        total_sell = (
            _parse_decimal(series.get(col_map["total_sell_amount"]))
            if col_map.get("total_sell_amount")
            else None
        )
        total_cost = (
            _parse_decimal(series.get(col_map["total_cost_amount"]))
            if col_map.get("total_cost_amount")
            else None
        )
        total_soh = (
            _parse_decimal(series.get(col_map["total_soh_value"])) if col_map.get("total_soh_value") else None
        )
        article_tok = (
            _normalize_text(series.get(col_map["raw_article_token"]))
            if col_map.get("raw_article_token")
            else None
        )
        listing_ext_id = (
            _normalize_text(series.get(col_map["listing_external_id"]))
            if col_map.get("listing_external_id")
            else None
        )
        listing_mkt = (
            _normalize_text(series.get(col_map["listing_marketplace"]))
            if col_map.get("listing_marketplace")
            else None
        )

        emitted = 0
        for col_name, period_date, period_type in week_unit_cols:
            units = _parse_decimal(series.get(col_name))
            if units is None or units <= 0:
                continue
            reported_soh = soh_val if latest_period and period_date == latest_period else None
            row = {
                "import_job_id": int(job_id),
                "source_row_number": int(source_row_number),
                "raw_row_payload": _row_dict(series),
                "raw_customer_token": None,
                "raw_location_token": loc_tok,
                "site_label": loc_tok,
                "raw_product_token": product_tok,
                "raw_period_ref": str(col_name),
                "period_start_date": period_date,
                "period_type": period_type,
                "units_sold": units,
                "raw_mtd_units": None,
                "is_mtd_estimate": False,
                "unit_sell_price": unit_sell,
                "unit_cost": unit_cost,
                "unit_mac": unit_mac,
                "reported_soh": reported_soh,
                "total_sell_amount": total_sell,
                "total_cost_amount": total_cost,
                "total_soh_value": total_soh if reported_soh is not None else None,
                "raw_article_token": article_tok,
                "listing_external_id": listing_ext_id,
                "listing_marketplace": listing_mkt,
                "resolution_status": "pending",
            }
            apply_listing_seed_fields(row, feed_profile)
            rows.append(apply_unit_total_derivation(row))
            emitted += 1
        if emitted == 0:
            skipped_products += 1

    if skipped_products:
        warnings.append(
            f"Skipped {skipped_products} row(s) with missing product token or no positive week units"
        )
    warnings.append(f"Wide-week unpivot: {len(week_unit_cols)} unit week column(s)")

    rows = enrich_flat_rows_from_companion_soh(
        file_bytes,
        filename,
        rows,
        feed_profile,
        warnings,
    )
    rows = apply_unit_total_derivation_many(rows)

    return ParseResult(
        rows=rows,
        period_start_date=latest_period,
        period_type="weekly",
        warnings=warnings,
        error=None,
    )
