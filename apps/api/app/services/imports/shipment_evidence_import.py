"""Import processor: shipment / order evidence (XXOMRPT0025/0027, ACZA-style workbooks).

Auto-detects report shape from headers. Perserves each source row in ``raw_source_row``.
Product resolution: strongest token first (Item → EAN → UPC → sales model), reusing DSI
``_resolve_product`` / ``ProductResolutionIndex``. Stops at first **ambiguous** outcome.
Distributor: Bill To, then Ship To via ``_resolve_distributor_strict`` (alias + exact dim only).
"""

from __future__ import annotations

import io
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.distributor_sales_inventory import (
    ProductResolutionIndex,
    _load_product_resolution_index,
    _norm_key,
    _resolve_distributor_strict,
    _resolve_product,
)
from app.services.imports.shipment_evidence_resolution_plan import (
    SHIPMENT_DISTRIBUTOR_ENTITY,
    enrich_shipment_distributor_candidates,
)
from app.services.imports.shipment_evidence_source_keys import (
    ShipmentEvidenceSourceKeyError,
    stable_source_key_for_row,
)
from app.services.imports.shipment_evidence_report_detect import (
    LINE_OPEN_ORDER,
    LINE_SHIPPED,
    REPORT_ACZA_SHIPPED,
    REPORT_ACZA_UNSHIP,
    REPORT_UNKNOWN,
    REPORT_XXOMRPT0025,
    REPORT_XXOMRPT0027,
    _ean_upc_str,
    detect_report_type,
)
from app.storage.local import get_storage_backend
from app.utils.json_safe import to_jsonable


def _norm_cols(cols: list[str]) -> set[str]:
    return {str(c).strip() for c in cols if c is not None}


def _cell_str(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, str):
        t = v.strip()
        return t or None
    if hasattr(v, "isoformat"):
        return None
    return str(v).strip() or None


def _parse_date(v: Any) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return None
    if isinstance(ts, pd.Timestamp):
        return ts.date()
    return None


def _row_dict(series: pd.Series) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in series.index:
        out[str(k)] = to_jsonable(series.get(k))
    return out


def _normalized_identifier_cell(v: Any) -> Any:
    """Prefer normalized string; fall back to original cell for numeric EAN/UPC cells."""
    nu = normalize_shipment_cell_value(v)
    return nu if nu is not None else v


def _extract_common(row: pd.Series) -> dict[str, Any]:
    def col(*names: str) -> Any:
        for n in names:
            if n in row.index:
                return row.get(n)
        return None

    bill = col("Bill To", "bill to")
    ship = col("Ship To", "ship to")
    ou = col("Operating Unit", "OU NAME", "ou name")
    return {
        "operating_unit": normalize_shipment_cell_value(ou),
        "bill_to_raw": normalize_shipment_cell_value(bill),
        "ship_to_raw": normalize_shipment_cell_value(ship),
        "order_no": normalize_shipment_cell_value(col("Order No.", "Order No")),
        "order_line": normalize_shipment_cell_value(col("Order Line")),
        "delivery_no": normalize_shipment_cell_value(col("Delivery No")),
        "invoice_line": normalize_shipment_cell_value(col("Invoice Line")),
        "item_code": normalize_shipment_cell_value(col("Item")),
        "sales_model_name": normalize_shipment_cell_value(col("Sales Model Name")),
        "customer_item": normalize_shipment_cell_value(col("Customer Item")),
        "ean_code": _ean_upc_str(_normalized_identifier_cell(col("EAN Code"))),
        "upc_code": _ean_upc_str(_normalized_identifier_cell(col("UPC Code"))),
        "mpor_item_no": normalize_shipment_cell_value(col("MPOR Item No.")),
        "quantity": row.get("Qty") if "Qty" in row.index else row.get("Qty "),
        "unit_price": row.get("Unit Price") if "Unit Price" in row.index else None,
        "amount": row.get("Amount") if "Amount" in row.index else None,
        "currency_code": normalize_shipment_cell_value(col("Currency")),
        "ship_confirm_date": _parse_date(col("Ship Confirm Date")),
        "schedule_ship_date": _parse_date(col("Schedule Ship Date")),
        "promise_date": _parse_date(col("Promise Date")),
        "exwork_date": _parse_date(col("Exwork Date")),
        "erd_date": _parse_date(col("ERD (Est Revenue Date)")),
    }


def _decimal_or_none(v: Any) -> Decimal | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return Decimal(str(v).replace(",", ""))
    except Exception:
        return None


def resolve_product_for_evidence(
    idx: ProductResolutionIndex,
    *,
    item_code: str | None,
    ean_code: str | None,
    upc_code: str | None,
    sales_model_name: str | None,
) -> tuple[int | None, str, str | None, str | None]:
    """(product_id, status, token_used, detail)."""
    tokens: list[tuple[str, str]] = []
    if item_code:
        tokens.append(("item", item_code))
    if ean_code:
        tokens.append(("ean", ean_code))
    if upc_code:
        tokens.append(("upc", upc_code))
    if sales_model_name:
        tokens.append(("sales_model", sales_model_name))
    if not tokens:
        return None, "no_identifier", None, None

    last_detail: str | None = None
    for _role, raw in tokens:
        pid, perr, tag, ev = _resolve_product(raw, idx, None)
        if pid is not None and perr is None:
            return int(pid), "resolved_unique", raw, tag or "resolved"
        if perr in ("ambiguous_product_match", "ambiguous_product_alias"):
            return None, "ambiguous", raw, perr
        if ev is not None and getattr(ev, "ambiguous_eligible", None):
            return None, "ambiguous", raw, "ambiguous_eligible"
        if perr == "unresolved_product_inactive_only":
            last_detail = perr
            continue
        last_detail = perr or tag or "unresolved"
    if last_detail == "unresolved_product_inactive_only":
        return None, "inactive_only", tokens[0][1], last_detail
    return None, "no_match", tokens[-1][1], last_detail


def resolve_distributor_for_evidence(
    db: Session,
    source_id: int | None,
    *,
    bill_to: str | None,
    ship_to: str | None,
) -> tuple[int | None, str, str | None]:
    if bill_to:
        did, err = _resolve_distributor_strict(db, bill_to, source_id)
        if did is not None:
            return int(did), "resolved", bill_to
        if err:
            pass
    if ship_to:
        did, err = _resolve_distributor_strict(db, ship_to, source_id)
        if did is not None:
            return int(did), "resolved", ship_to
    if not (bill_to or ship_to):
        return None, "skipped_empty", None
    return None, "unresolved", bill_to or ship_to


def _rebuild_shipment_distributor_candidates(db: Session, job: ImportJob) -> None:
    """Replace ``shipment_distributor`` candidates for this job from unresolved evidence lines."""
    jid = int(job.id)
    sid = int(job.source_id) if job.source_id else None

    db.execute(
        delete(ImportEntityMappingCandidate).where(
            ImportEntityMappingCandidate.import_job_id == jid,
            ImportEntityMappingCandidate.entity_type == SHIPMENT_DISTRIBUTOR_ENTITY,
        )
    )
    db.flush()

    lines = list(db.scalars(select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.import_job_id == jid)).all())
    buckets: dict[str, dict[str, Any]] = {}

    for line in lines:
        if line.distributor_id is not None:
            continue
        if (line.distributor_resolution_status or "") != "unresolved":
            continue
        raw: str | None = None
        party: str | None = None
        btr = line.bill_to_raw
        strw = line.ship_to_raw
        if btr and str(btr).strip():
            raw = str(btr).strip()
            party = "bill_to"
        elif strw and str(strw).strip():
            raw = str(strw).strip()
            party = "ship_to"
        else:
            continue
        nk = _norm_key(raw)
        if not nk:
            continue
        bucket = buckets.setdefault(
            nk,
            {"line_ids": [], "samples": [], "parties": set(), "qty": Decimal(0), "amt": Decimal(0)},
        )
        bucket["line_ids"].append(int(line.id))
        if party:
            bucket["parties"].add(party)
        if len(bucket["samples"]) < 5 and raw not in bucket["samples"]:
            bucket["samples"].append(raw[:512])
        if line.quantity is not None:
            bucket["qty"] += Decimal(str(line.quantity))
        if line.amount is not None:
            bucket["amt"] += Decimal(str(line.amount))

    for nk, bucket in buckets.items():
        primary_party = "bill_to" if "bill_to" in bucket["parties"] else "ship_to"
        cand = ImportEntityMappingCandidate(
            import_job_id=jid,
            source_definition_id=sid,
            entity_type=SHIPMENT_DISTRIBUTOR_ENTITY,
            normalized_key=nk[:512],
            dealer_group_token=None,
            row_count=len(bucket["line_ids"]),
            total_units=float(bucket["qty"]) if bucket["qty"] else None,
            total_reported_value=float(bucket["amt"]) if bucket["amt"] else None,
            sample_raw_values=to_jsonable(bucket["samples"][:5]),
            status="needs_review",
            context=to_jsonable({"party": primary_party, "line_ids": bucket["line_ids"]}),
        )
        db.add(cand)
    db.flush()
    enrich_shipment_distributor_candidates(db, import_job_id=jid, source_definition_id=sid)


def _execute_shipment_line_upsert(db: Session, values: dict[str, Any]) -> None:
    """Insert or update one line keyed by (import_job_id, source_key).

    On conflict, refreshes source-derived columns only; ``id``, ``created_at``, and all
    product/distributor resolution columns on the existing row are left unchanged (see
    post-loop ``_resolve_unresolved_shipment_lines_for_job`` for unresolved ids).
    """
    t = ShipmentEvidenceLine.__table__
    ins = pg_insert(t).values(**values)
    ex = ins.excluded
    stmt = ins.on_conflict_do_update(
        constraint="uq_shipment_evidence_line_import_job_source_key",
        set_={
            "source_sheet": ex.source_sheet,
            "source_row_number": ex.source_row_number,
            "report_type": ex.report_type,
            "line_state": ex.line_state,
            "raw_source_row": ex.raw_source_row,
            "operating_unit": ex.operating_unit,
            "bill_to_raw": ex.bill_to_raw,
            "ship_to_raw": ex.ship_to_raw,
            "order_no": ex.order_no,
            "order_line": ex.order_line,
            "delivery_no": ex.delivery_no,
            "invoice_line": ex.invoice_line,
            "item_code": ex.item_code,
            "sales_model_name": ex.sales_model_name,
            "customer_item": ex.customer_item,
            "ean_code": ex.ean_code,
            "upc_code": ex.upc_code,
            "mpor_item_no": ex.mpor_item_no,
            "quantity": ex.quantity,
            "unit_price": ex.unit_price,
            "amount": ex.amount,
            "currency_code": ex.currency_code,
            "ship_confirm_date": ex.ship_confirm_date,
            "schedule_ship_date": ex.schedule_ship_date,
            "promise_date": ex.promise_date,
            "exwork_date": ex.exwork_date,
            "erd_date": ex.erd_date,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)


def _resolve_unresolved_shipment_lines_for_job(
    db: Session,
    job: ImportJob,
    idx: ProductResolutionIndex,
    source_id: int | None,
) -> None:
    """Re-run product and/or distributor resolution only where the corresponding id is still null."""
    jid = int(job.id)
    lines = list(
        db.scalars(
            select(ShipmentEvidenceLine).where(
                ShipmentEvidenceLine.import_job_id == jid,
                or_(ShipmentEvidenceLine.product_id.is_(None), ShipmentEvidenceLine.distributor_id.is_(None)),
            )
        ).all()
    )
    for line in lines:
        if line.product_id is None:
            pid, pstatus, ptoken, pdetail = resolve_product_for_evidence(
                idx,
                item_code=line.item_code,
                ean_code=line.ean_code,
                upc_code=line.upc_code,
                sales_model_name=line.sales_model_name,
            )
            line.product_id = pid
            line.product_resolution_status = pstatus
            line.product_resolution_token = ptoken
            line.product_resolution_detail = pdetail
            db.add(line)
        if line.distributor_id is None:
            did, dstatus, dtoken = resolve_distributor_for_evidence(
                db,
                source_id,
                bill_to=line.bill_to_raw,
                ship_to=line.ship_to_raw,
            )
            line.distributor_id = did
            line.distributor_resolution_status = dstatus
            line.distributor_resolution_token = dtoken
            db.add(line)
    db.flush()


def _load_frames_for_job(job: ImportJob, df_passed: pd.DataFrame, raw_bytes: bytes) -> list[tuple[str | None, pd.DataFrame, str, str]]:
    """List of (sheet_name, dataframe, report_type, line_state)."""
    fn = job.file_name or ""
    lower = fn.lower()
    out: list[tuple[str | None, pd.DataFrame, str, str]] = []

    if lower.endswith(".csv"):
        cols = _norm_cols(list(df_passed.columns))
        rt, ls = detect_report_type(cols, sheet_name=None, file_name=fn)
        out.append((None, df_passed, rt, ls))
        return out

    if lower.endswith((".xlsx", ".xlsm")):
        xl = pd.ExcelFile(io.BytesIO(raw_bytes), engine="openpyxl")
        for sheet in xl.sheet_names:
            sdf = pd.read_excel(io.BytesIO(raw_bytes), sheet_name=sheet, engine="openpyxl")
            cols = _norm_cols(list(sdf.columns))
            rt, ls = detect_report_type(cols, sheet_name=sheet, file_name=fn)
            if rt == REPORT_UNKNOWN and sheet.lower() in ("shipped", "unship"):
                rt = REPORT_ACZA_SHIPPED if sheet.lower() == "shipped" else REPORT_ACZA_UNSHIP
                ls = LINE_SHIPPED if sheet.lower() == "shipped" else LINE_OPEN_ORDER
            out.append((sheet, sdf, rt, ls))
        return out

    cols = _norm_cols(list(df_passed.columns))
    rt, ls = detect_report_type(cols, sheet_name=None, file_name=fn)
    out.append((None, df_passed, rt, ls))
    return out


def process_shipment_evidence_import(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    """Parse file(s), write ``ShipmentEvidenceLine`` rows. Returns blocking error count."""
    _ = mapping
    raw_meta = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job.id)).first()
    if not raw_meta:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_raw_file",
                message="No raw file metadata for this import job.",
            )
        )
        return 1

    storage = get_storage_backend()
    raw_bytes = storage.read(raw_meta.storage_key)
    frames = _load_frames_for_job(job, df, raw_bytes)

    idx = _load_product_resolution_index(db)
    source_id = int(job.source_id) if job.source_id else None

    blocking = 0
    global_row = 0
    unknown_reports = 0

    for sheet_name, frame, report_type, line_state in frames:
        if frame is None or len(frame) == 0:
            continue
        if report_type == REPORT_UNKNOWN:
            unknown_reports += 1
            continue

        for pos, (_, row) in enumerate(frame.iterrows(), start=2):
            global_row += 1
            try:
                series = row if isinstance(row, pd.Series) else pd.Series(row, index=frame.columns)
                raw_payload = _row_dict(series)
                ex = _extract_common(series)
                source_key = stable_source_key_for_row(report_type=report_type, sheet_name=sheet_name, ex=ex)

                pid, pstatus, ptoken, pdetail = resolve_product_for_evidence(
                    idx,
                    item_code=ex["item_code"],
                    ean_code=ex["ean_code"],
                    upc_code=ex["upc_code"],
                    sales_model_name=ex["sales_model_name"],
                )
                did, dstatus, dtoken = resolve_distributor_for_evidence(
                    db,
                    source_id,
                    bill_to=ex["bill_to_raw"],
                    ship_to=ex["ship_to_raw"],
                )

                q_dec = _decimal_or_none(ex["quantity"])
                row_values: dict[str, Any] = {
                    "import_job_id": int(job.id),
                    "source_key": source_key,
                    "source_sheet": sheet_name,
                    "source_row_number": pos,
                    "report_type": report_type,
                    "line_state": line_state,
                    "raw_source_row": raw_payload,
                    "operating_unit": ex["operating_unit"],
                    "bill_to_raw": ex["bill_to_raw"],
                    "ship_to_raw": ex["ship_to_raw"],
                    "order_no": ex["order_no"],
                    "order_line": ex["order_line"],
                    "delivery_no": ex["delivery_no"],
                    "invoice_line": ex["invoice_line"],
                    "item_code": ex["item_code"],
                    "sales_model_name": ex["sales_model_name"],
                    "customer_item": ex["customer_item"],
                    "ean_code": ex["ean_code"],
                    "upc_code": ex["upc_code"],
                    "mpor_item_no": ex["mpor_item_no"],
                    "quantity": float(q_dec) if q_dec is not None else None,
                    "unit_price": float(v) if (v := _decimal_or_none(ex["unit_price"])) is not None else None,
                    "amount": float(v) if (v := _decimal_or_none(ex["amount"])) is not None else None,
                    "currency_code": ex["currency_code"],
                    "ship_confirm_date": ex["ship_confirm_date"],
                    "schedule_ship_date": ex["schedule_ship_date"],
                    "promise_date": ex["promise_date"],
                    "exwork_date": ex["exwork_date"],
                    "erd_date": ex["erd_date"],
                    "product_id": pid,
                    "product_resolution_status": pstatus,
                    "product_resolution_token": ptoken,
                    "product_resolution_detail": pdetail,
                    "distributor_id": did,
                    "distributor_resolution_status": dstatus,
                    "distributor_resolution_token": dtoken,
                }
                _execute_shipment_line_upsert(db, row_values)
            except ShipmentEvidenceSourceKeyError as exc:
                blocking += 1
                db.add(
                    ImportRowResult(
                        job_id=job.id,
                        row_number=global_row,
                        severity="error",
                        code="shipment_evidence_source_key",
                        message=str(exc)[:2000],
                        raw_payload={"sheet": sheet_name, "row_index": pos, "report_type": report_type},
                    )
                )
            except Exception as exc:  # noqa: BLE001
                blocking += 1
                db.add(
                    ImportRowResult(
                        job_id=job.id,
                        row_number=global_row,
                        severity="error",
                        code="shipment_evidence_row_error",
                        message=str(exc)[:2000],
                        raw_payload={"sheet": sheet_name, "row_index": pos},
                    )
                )

    db.flush()
    _resolve_unresolved_shipment_lines_for_job(db, job, idx, source_id)

    if unknown_reports == len(frames) and global_row == 0:
        blocking += 1
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="shipment_evidence_unknown_format",
                message="Could not detect a supported shipment / order report from headers.",
            )
        )

    db.flush()
    _rebuild_shipment_distributor_candidates(db, job)

    meta = dict(job.staged_metadata or {})
    meta["shipment_evidence"] = to_jsonable(
        {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "sheets": [s for s, *_ in frames],
            "total_lines_written_estimate": global_row,
        }
    )
    job.staged_metadata = to_jsonable(meta)

    summary = {
        "lines": global_row,
        "blocking": blocking,
        "sheets": len(frames),
    }
    db.add(
        ImportRowResult(
            job_id=job.id,
            row_number=0,
            severity="info" if blocking == 0 else "warning",
            code="shipment_evidence_summary",
            message=json.dumps(summary),
        )
    )
    return 1 if blocking else 0
