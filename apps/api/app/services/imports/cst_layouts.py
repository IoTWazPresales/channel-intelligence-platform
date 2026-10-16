"""Customer sell-through upload: reporting customers and saved column layouts (N-0111).

Warren 2026-10-16: an upload picks a reporting customer, not a source. Every file loads into the
one sell-through table with its standard columns. The only per-customer configuration is the
column layout: header -> standard column. The first upload of an unrecognised header set goes
through the column-mapping step and the layout is saved for that customer; later uploads match a
saved layout by headers. This module reuses the parser's own header detection and column
resolution (``customer_sell_through_flat``) and the job's ``field_mapping``; it adds no second
mapping system.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.dimensions import DimCustomer
from app.models.customer_report_config import CustomerReportConfig
from app.models.customer_sellthrough_layout import CustomerSellthroughLayout
from app.models.ingestion import ImportTemplate, SourceDefinition
from app.services.imports.parsers.customer_sell_through_flat import (
    CANONICAL_FIELDS,
    _build_alias_index,
    _normalize_text,
    _read_workbook_sheets,
    _resolve_source_columns,
    _select_sheet_with_header,
    normalize_cst_expected_columns,
)

CST_TEMPLATE_SLUG = "customer_sell_through"
ANCHOR_SOURCE_CODE = "cst_customer_upload"
ANCHOR_SOURCE_NAME = "Customer sell-through upload"
DEFAULT_STRUCTURE = "flat"

# Labels shown in the column-mapping step: the standard sell-through columns.
CANONICAL_LABELS: dict[str, str] = {
    "raw_product_token": "Product (code, barcode or SKU)",
    "raw_location_token": "Store / site",
    "raw_period_ref": "Period (week, month or sale date)",
    "units_sold": "Units sold",
    "unit_sell_price": "Unit sell price",
    "unit_cost": "Unit cost",
    "unit_mac": "Unit MAC",
    "reported_soh": "On-hand (stock)",
    "raw_article_token": "Customer article code",
    "listing_external_id": "Listing ID (ASIN, TSIN, web ID)",
    "listing_marketplace": "Marketplace",
    "total_sell_amount": "Sales value",
    "total_cost_amount": "Cost value",
    "total_soh_value": "On-hand value",
    "in_transit_units": "In transit units",
    "on_order_units": "On order units",
}

_UNNAMED_RE = re.compile(r"^(unnamed:\s*\d+|col_\d+)$")
# Currency / unit stubs under a measure label in dual-header exports: not part of a layout.
_STUB_RE = re.compile(r"^(zar|usd|eur|gbp|r|\$|%|ea|each|uom|pc|pcs|unit)$")
# Columns named for a period (a week, a month, a day) change from file to file; the layout is the
# columns that stay. "49-2025", "027.2026", "2026-w14", "wk 14", "week 14 2026", "jan 2026", "2026-03-30".
_PERIOD_HEADER_RES = (
    re.compile(r"^\d{1,3}[-./]\d{4}$"),
    re.compile(r"^\d{4}[-./]w?\d{1,2}([-./]\d{1,2})?$"),
    re.compile(r"^(wk|w|week|wek)\s*\d{1,2}(\s*[-./]?\s*\d{2,4})?$"),
    re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*[\s\-./]*\d{2,4}$"),
)
_MEASURE_PERIOD_RE = re.compile(r"^(?P<measure>.+?)\s+(\d{1,3}[-./]\d{4}|\d{4}-w\d{1,2})$")


def normalize_header(value: Any) -> str:
    """Case, spacing and blank-insensitive header text."""
    text = _normalize_text(value) or ""
    return re.sub(r"\s+", " ", text).strip().lower()


def meaningful_headers(columns: list[Any]) -> list[str]:
    """Normalised header labels with blank / auto-named columns left out, in file order."""
    out: list[str] = []
    for c in columns:
        n = normalize_header(c)
        if n and not _UNNAMED_RE.match(n):
            out.append(n)
    return out


def _signature_token(header: str) -> str | None:
    """What a header contributes to the layout fingerprint; ``None`` when it contributes nothing."""
    if _STUB_RE.match(header):
        return None
    if any(r.match(header) for r in _PERIOD_HEADER_RES):
        return "<period>"
    m = _MEASURE_PERIOD_RE.match(header)
    if m:
        return f"{m.group('measure')} <period>"
    return header


def signature_tokens(columns: list[Any]) -> set[str]:
    return {t for t in (_signature_token(h) for h in meaningful_headers(columns)) if t}


def layout_signature(columns: list[Any]) -> str:
    """Fingerprint of a header set: order, case, blank columns, unit stubs and period-named columns do not matter."""
    return hashlib.sha256("\n".join(sorted(signature_tokens(columns))).encode("utf-8")).hexdigest()[:16]


def cst_template_expected_columns(db: Session) -> dict[str, Any]:
    tpl = db.scalar(select(ImportTemplate).where(ImportTemplate.slug == CST_TEMPLATE_SLUG))
    return normalize_cst_expected_columns(tpl.expected_columns if tpl and tpl.expected_columns else {})


def _fallback_header_row(raw: pd.DataFrame) -> int | None:
    """Row of the first ten with the most filled cells (a header the aliases do not recognise)."""
    best_row, best_count = None, 1
    for i in range(min(10, len(raw))):
        filled = sum(1 for c in raw.iloc[i].tolist() if _normalize_text(c))
        if filled > best_count:
            best_row, best_count = i, filled
    return best_row


def sniff_columns(
    filename: str,
    raw_bytes: bytes,
    expected_columns: dict[str, Any],
    field_mapping: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Columns the parser would read: the header row its alias match finds, else the fullest of the first rows.

    Returns ``{"columns": [...], "samples": {column: [first values]}}`` or ``None`` when the file
    cannot be read or holds no header.
    """
    expected = normalize_cst_expected_columns(expected_columns)
    alias_index = _build_alias_index(dict(field_mapping or {}), expected)
    try:
        df, _first = _select_sheet_with_header(raw_bytes, filename, alias_index)
    except Exception:
        return None
    if df is None:
        try:
            sheets = _read_workbook_sheets(raw_bytes, filename)
        except Exception:
            return None
        for _name, raw in sheets:
            if raw is None or raw.empty:
                continue
            row = _fallback_header_row(raw)
            if row is None:
                continue
            headers = [_normalize_text(c) or f"col_{i}" for i, c in enumerate(raw.iloc[row].tolist())]
            df = raw.iloc[row + 1 :].copy()
            df.columns = headers
            df = df.reset_index(drop=True)
            break
    if df is None:
        return None
    columns = [str(c) for c in df.columns]
    samples: dict[str, list[str]] = {}
    for col in columns:
        vals: list[str] = []
        series = df[col]
        if isinstance(series, pd.DataFrame):  # duplicate header names
            series = series.iloc[:, 0]
        for v in series.tolist():
            text = _normalize_text(v)
            if text:
                vals.append(text[:60])
            if len(vals) >= 3:
                break
        samples[col] = vals
    return {"columns": columns, "samples": samples}


def detect_mapping(columns: list[str], expected_columns: dict[str, Any]) -> dict[str, str]:
    """Header -> standard column, as the parser would resolve this file with no saved layout."""
    resolved = _resolve_source_columns(list(columns), {}, normalize_cst_expected_columns(expected_columns))
    out: dict[str, str] = {}
    for canon, col in resolved.items():
        if col is not None and col not in out:
            out[col] = canon
    return out


def validate_field_mapping(columns: list[str], field_mapping: dict[str, str]) -> dict[str, str]:
    """Keep only entries whose header is in the file and whose target is a standard column; raise on a gap."""
    by_norm = {normalize_header(c): c for c in columns}
    clean: dict[str, str] = {}
    for header, target in (field_mapping or {}).items():
        if not target:
            continue
        if target not in CANONICAL_FIELDS:
            raise ValueError(f"'{target}' is not a standard sell-through column")
        file_header = by_norm.get(normalize_header(header))
        if file_header is None:
            raise ValueError(f"Column '{header}' is not in the file")
        clean[file_header] = target
    targets = set(clean.values())
    if "raw_product_token" not in targets:
        raise ValueError("Map the product column (code, barcode or SKU) before uploading")
    if not targets & {"units_sold", "reported_soh", "total_sell_amount"}:
        raise ValueError("Map at least units sold or on-hand before uploading")
    return clean


# ---------------------------------------------------------------- reporting customers

def list_reporting_customers(db: Session) -> list[dict[str, Any]]:
    """Customers ticked as reporting customers.

    The tick is ``customer_report_config.reports_expected`` - the same list
    ``cst_d1.advance_cst_report_slots`` walks to open the due / late / missing slots (that job also
    skips customers that are not key accounts; the picker does not, so a ticked customer can always
    be uploaded for). A customer merged into another is not listed.
    """
    rows = db.execute(
        select(DimCustomer.id, DimCustomer.name, DimCustomer.is_key_account, CustomerReportConfig.expected_cadence)
        .join(CustomerReportConfig, CustomerReportConfig.customer_id == DimCustomer.id)
        .where(
            CustomerReportConfig.reports_expected.is_(True),
            DimCustomer.merged_into_customer_id.is_(None),
        )
        .order_by(DimCustomer.name)
    ).all()
    counts: dict[int, int] = {}
    for cid, n in db.execute(
        select(CustomerSellthroughLayout.customer_id, CustomerSellthroughLayout.id).where(
            CustomerSellthroughLayout.is_hidden.is_(False)
        )
    ).all():
        counts[int(cid)] = counts.get(int(cid), 0) + 1
    return [
        {
            "id": int(r.id),
            "name": r.name,
            "is_key_account": bool(r.is_key_account),
            "expected_cadence": r.expected_cadence,
            "layout_count": counts.get(int(r.id), 0),
        }
        for r in rows
    ]


def is_reporting_customer(db: Session, customer_id: int) -> bool:
    return any(c["id"] == int(customer_id) for c in list_reporting_customers(db))


# ---------------------------------------------------------------- layouts

def layout_to_dict(layout: CustomerSellthroughLayout) -> dict[str, Any]:
    return {
        "id": int(layout.id),
        "customer_id": int(layout.customer_id),
        "name": layout.name,
        "header_signature": layout.header_signature,
        "headers": list(layout.headers or []),
        "field_mapping": dict(layout.field_mapping or {}),
        "report_structure_type": layout.report_structure_type or DEFAULT_STRUCTURE,
        "origin": layout.origin,
        "is_hidden": bool(layout.is_hidden),
    }


def list_layouts(db: Session, customer_id: int, *, include_hidden: bool = False) -> list[CustomerSellthroughLayout]:
    stmt = select(CustomerSellthroughLayout).where(CustomerSellthroughLayout.customer_id == int(customer_id))
    if not include_hidden:
        stmt = stmt.where(CustomerSellthroughLayout.is_hidden.is_(False))
    return list(db.scalars(stmt.order_by(CustomerSellthroughLayout.id)).all())


def find_matching_layout(db: Session, customer_id: int, columns: list[str]) -> CustomerSellthroughLayout | None:
    sig = layout_signature(columns)
    return db.scalar(
        select(CustomerSellthroughLayout).where(
            CustomerSellthroughLayout.customer_id == int(customer_id),
            CustomerSellthroughLayout.header_signature == sig,
            CustomerSellthroughLayout.is_hidden.is_(False),
        )
    )


def closest_layout(
    db: Session, customer_id: int, columns: list[str], *, minimum: float = 0.5
) -> CustomerSellthroughLayout | None:
    """The customer's saved layout whose header set is most like this file's (to prefill the mapping step)."""
    mine = signature_tokens(columns)
    best, best_score = None, minimum
    for lay in list_layouts(db, customer_id):
        theirs = signature_tokens(list(lay.headers or []))
        if not mine or not theirs:
            continue
        score = len(mine & theirs) / len(mine | theirs)
        if score >= best_score:
            best, best_score = lay, score
    return best


def _free_name(db: Session, customer_id: int, name: str) -> str:
    base = (name or "").strip()[:240] or "Layout"
    taken = {n.lower() for n in db.scalars(
        select(CustomerSellthroughLayout.name).where(CustomerSellthroughLayout.customer_id == int(customer_id))
    ).all()}
    if base.lower() not in taken:
        return base
    n = 2
    while f"{base} ({n})".lower() in taken:
        n += 1
    return f"{base} ({n})"


def save_layout(
    db: Session,
    *,
    customer_id: int,
    name: str,
    columns: list[str],
    field_mapping: dict[str, str],
    report_structure_type: str | None = None,
    origin: str = "upload",
    origin_source_id: int | None = None,
    origin_import_job_id: int | None = None,
) -> tuple[CustomerSellthroughLayout, bool]:
    """Save a layout for a customer and header set. Returns ``(layout, created)``.

    A header set the customer already has is returned unchanged (never overwritten); a hidden one is
    brought back with the mapping given.
    """
    sig = layout_signature(columns)
    existing = db.scalar(
        select(CustomerSellthroughLayout).where(
            CustomerSellthroughLayout.customer_id == int(customer_id),
            CustomerSellthroughLayout.header_signature == sig,
        )
    )
    if existing is not None:
        if existing.is_hidden:
            existing.is_hidden = False
            existing.field_mapping = dict(field_mapping)
            db.add(existing)
            db.flush()
        return existing, False
    layout = CustomerSellthroughLayout(
        customer_id=int(customer_id),
        name=_free_name(db, customer_id, name),
        header_signature=sig,
        headers=meaningful_headers(columns),
        field_mapping=dict(field_mapping),
        report_structure_type=report_structure_type or DEFAULT_STRUCTURE,
        origin=origin,
        origin_source_id=origin_source_id,
        origin_import_job_id=origin_import_job_id,
    )
    db.add(layout)
    db.flush()
    return layout, True


# ---------------------------------------------------------------- the one internal source

def get_or_create_anchor_source(db: Session) -> SourceDefinition:
    """The single internal source every sell-through upload hangs its job on (never shown to users).

    A job needs a source row; the customer is carried on the job (``staged_metadata.customer_id``).
    """
    src = db.scalar(
        select(SourceDefinition)
        .options(joinedload(SourceDefinition.import_template))
        .where(SourceDefinition.code == ANCHOR_SOURCE_CODE)
    )
    if src is not None:
        return src
    tpl = db.scalar(select(ImportTemplate).where(ImportTemplate.slug == CST_TEMPLATE_SLUG))
    if tpl is None:
        raise ValueError("The customer sell-through import template is missing")
    src = SourceDefinition(
        import_template_id=tpl.id,
        code=ANCHOR_SOURCE_CODE,
        name=ANCHOR_SOURCE_NAME,
        source_kind="file",
        expected_template=None,
        is_active=True,
        is_hidden=True,
    )
    db.add(src)
    db.flush()
    db.refresh(src)
    return src


# ---------------------------------------------------------------- upload: inspect and create

def inspect_files_for_customer(
    db: Session, customer_id: int, files: list[tuple[str, bytes]]
) -> list[dict[str, Any]]:
    """Per file: its columns, the saved layout of this customer that matches them, else a detected mapping."""
    expected = cst_template_expected_columns(db)
    out: list[dict[str, Any]] = []
    for filename, raw in files:
        info = sniff_columns(filename, raw, expected)
        if info is None:
            out.append(
                {
                    "filename": filename,
                    "readable": False,
                    "unreadable_reason": "The file could not be read or has no header row",
                    "columns": [],
                    "layout_signature": None,
                    "layout": None,
                    "detected_mapping": {},
                    "samples": {},
                }
            )
            continue
        columns = info["columns"]
        layout = find_matching_layout(db, customer_id, columns)
        detected: dict[str, str] = {}
        similar = None
        if layout is None:
            detected = detect_mapping(columns, expected)
            similar = closest_layout(db, customer_id, columns)
            if similar is not None:
                by_norm = {normalize_header(c): c for c in columns}
                for header, target in (similar.field_mapping or {}).items():
                    present = by_norm.get(normalize_header(header))
                    if present is not None and target in CANONICAL_FIELDS:
                        detected[present] = target
        out.append(
            {
                "filename": filename,
                "readable": True,
                "unreadable_reason": None,
                "columns": columns,
                "layout_signature": layout_signature(columns),
                "layout": {"id": int(layout.id), "name": layout.name} if layout else None,
                "similar_layout": {"id": int(similar.id), "name": similar.name} if similar else None,
                "detected_mapping": detected,
                "samples": info["samples"],
            }
        )
    return out


def _union_mapping(layouts: list[CustomerSellthroughLayout]) -> dict[str, str]:
    """One header -> column dict for a job; the same header mapped two ways is refused."""
    merged: dict[str, str] = {}
    seen: dict[str, tuple[str, str]] = {}
    for lay in layouts:
        for header, target in (lay.field_mapping or {}).items():
            key = normalize_header(header)
            if key in seen and seen[key][0] != target:
                raise ValueError(
                    f"Column '{header}' is mapped to '{seen[key][0]}' by layout '{seen[key][1]}' and to "
                    f"'{target}' by layout '{lay.name}'. Upload these files separately."
                )
            seen[key] = (target, lay.name)
            merged[header] = target
    return merged


def create_customer_upload_jobs(
    db: Session,
    *,
    customer_id: int,
    filenames_and_bytes: list[tuple[str, bytes]],
    new_layouts: list[dict[str, Any]] | None = None,
    sales_only: bool = False,
    stock_only: bool = False,
    confirmed_year: int | None = None,
    import_mode: str = "validate",
) -> list[dict[str, Any]]:
    """Upload files for one reporting customer.

    Each file takes the customer's saved layout that matches its headers; a file with no match needs
    an entry in ``new_layouts`` (``signature``, ``name``, ``field_mapping``) from the column-mapping
    step, which is saved for the customer before the job is made. Files whose layouts share a report
    structure share one import job. Returns one outcome per job or failed file.
    """
    from app.services.imports.cst_batch import create_cst_batch_job_sync
    from app.services.merge_redirect import follow_customer_merge_redirect_sync

    cid = follow_customer_merge_redirect_sync(db, int(customer_id)) or int(customer_id)
    if not is_reporting_customer(db, cid):
        raise ValueError("This customer is not ticked as a reporting customer")

    expected = cst_template_expected_columns(db)
    spec_by_sig = {str(s.get("signature")): s for s in (new_layouts or []) if isinstance(s, dict)}
    outcomes: list[dict[str, Any]] = []
    placed: list[tuple[str, bytes, CustomerSellthroughLayout]] = []

    for filename, raw in filenames_and_bytes:
        info = sniff_columns(filename, raw, expected)
        if info is None:
            outcomes.append(
                {"outcome": "error", "filenames": [filename], "error": "The file could not be read or has no header row"}
            )
            continue
        columns = info["columns"]
        layout = find_matching_layout(db, cid, columns)
        if layout is None:
            spec = spec_by_sig.get(layout_signature(columns))
            if spec is None:
                outcomes.append(
                    {
                        "outcome": "error",
                        "filenames": [filename],
                        "error": "These columns are not mapped yet. Map them first; the layout is saved for this customer.",
                    }
                )
                continue
            try:
                clean = validate_field_mapping(columns, spec.get("field_mapping") or {})
            except ValueError as exc:
                outcomes.append({"outcome": "error", "filenames": [filename], "error": str(exc)})
                continue
            layout, _created = save_layout(
                db,
                customer_id=cid,
                name=str(spec.get("name") or "").strip() or f"{filename.rsplit('.', 1)[0]} layout",
                columns=columns,
                field_mapping=clean,
                report_structure_type=DEFAULT_STRUCTURE,
            )
            db.commit()
        placed.append((filename, raw, layout))

    by_structure: dict[str, list[tuple[str, bytes, CustomerSellthroughLayout]]] = {}
    for item in placed:
        by_structure.setdefault(item[2].report_structure_type or DEFAULT_STRUCTURE, []).append(item)

    for structure, items in by_structure.items():
        names = [it[0] for it in items]
        layouts = list({it[2].id: it[2] for it in items}.values())
        try:
            mapping = _union_mapping(layouts)
            job = create_cst_batch_job_sync(
                db,
                customer_id=cid,
                filenames_and_bytes=[(it[0], it[1]) for it in items],
                import_mode=import_mode,
                sales_only=sales_only,
                stock_only=stock_only,
                confirmed_year=confirmed_year,
                field_mapping=mapping,
                layout_ids=[int(lay.id) for lay in layouts],
                report_structure_type=structure,
            )
        except Exception as exc:  # one failed group must not hide the others
            outcomes.append({"outcome": "error", "filenames": names, "error": str(exc)})
            continue
        meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
        outcomes.append(
            {
                "outcome": "created",
                "import_job_id": int(job.id),
                "stage": job.stage,
                "filenames": names,
                "file_count": len(items),
                "layouts": [{"id": int(lay.id), "name": lay.name} for lay in layouts],
                "report_structure_type": structure,
                "cst_file_periods": meta.get("cst_file_periods"),
                "cst_year_required": meta.get("cst_year_required"),
            }
        )
    return outcomes
