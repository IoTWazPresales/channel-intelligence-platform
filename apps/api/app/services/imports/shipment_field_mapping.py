"""Inbound shipment import: header discovery + field_mapping (mirrors DSI infer flow)."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.ingestion import ImportJob, RawFileMetadata, SourceDefinition
from app.services.imports.pm_mapping_memory import MEMORY_SCHEMA_VERSION, load_by_header_norm, norm_header_key
from app.storage.local import get_storage_backend


def _effective_mapping_template(source: SourceDefinition | None) -> dict[str, Any]:
    """Same merge rules as ``pipeline.effective_mapping_template`` (kept local to avoid import cycles)."""
    merged: dict[str, Any] = {}
    tpl = source.import_template if source else None
    if tpl and tpl.expected_columns:
        for k, v in tpl.expected_columns.items():
            if isinstance(v, dict):
                merged[k] = {"aliases": list(v.get("aliases", []))}
    if source and source.expected_template:
        for k, v in source.expected_template.items():
            if isinstance(v, dict):
                merged.setdefault(k, {"aliases": list(v.get("aliases", []))})
    return merged


SHIPMENT_CANONICAL_TARGETS: tuple[str, ...] = (
    "operating_unit",
    "bill_to_raw",
    "ship_to_raw",
    "distributor_token",
    "order_no",
    "order_line",
    "delivery_no",
    "invoice_line",
    "item_code",
    "sales_model_name",
    "customer_item",
    "ean_code",
    "upc_code",
    "mpor_item_no",
    "quantity",
    "unit_price",
    "amount",
    "currency_code",
    "ship_confirm_date",
    "schedule_ship_date",
    "promise_date",
    "exwork_date",
    "erd_date",
    "est_pod_date",
    "pod_date",
    "customer_dealer_token",
)

# Longer helper text for mapping UI (aligned with DSI column-mapping hints where concepts match).
SHIPMENT_FIELD_TARGET_DESCRIPTIONS: dict[str, str] = {
    "distributor_token": (
        "Distributor name or code as printed in the file (same role as DSI distributor_token). "
        "Values are stored on the Bill To column for resolution when Bill To is not mapped separately."
    ),
    "bill_to_raw": "Bill-to party text used for distributor resolution when no separate distributor column is mapped.",
    "ship_to_raw": "Ship-to party text used for distributor resolution when Bill To does not resolve.",
    "customer_dealer_token": (
        "Secondary label from the file: the raw customer / channel-partner name as printed "
        "(e.g. Customer Remarks). Same concept as DSI Source customer name."
    ),
    "item_code": "Manufacturer item / SKU code used as a primary product identifier for matching.",
    "sales_model_name": "Commercial sales model name used as an alternate product identifier for matching.",
    "est_pod_date": (
        "Estimated Proof of Delivery: the expected delivery date before the shipment is confirmed delivered "
        "(null until known)."
    ),
    "pod_date": (
        "Actual Proof of Delivery: the confirmed delivery date once the shipment is delivered (null until known)."
    ),
}


def _norm_header(h: str) -> str:
    return (h or "").strip().lower()


def merge_shipment_mapping_memory(db: Session, *, source_id: int, field_mapping: dict[str, str]) -> None:
    """Persist confirmed shipment column → canonical mappings on the source (by normalized header)."""
    src = db.get(SourceDefinition, source_id)
    if src is None:
        return
    allowed = set(SHIPMENT_CANONICAL_TARGETS)
    root: dict[str, Any] = dict(src.column_mapping_memory or {})
    bh: dict[str, Any] = dict(root.get("by_header_norm") or {})

    for header, tgt in field_mapping.items():
        nh = norm_header_key(str(header))
        if not nh:
            continue
        if tgt not in allowed:
            continue
        prev = bh.get(nh) if isinstance(bh.get(nh), dict) else {}
        bh[nh] = {
            "target": tgt,
            "confirmations": int(prev.get("confirmations", 0)) + 1,
        }

    root["by_header_norm"] = bh
    root["schema_version"] = root.get("schema_version") or MEMORY_SCHEMA_VERSION
    root["shipment_mapping"] = True
    src.column_mapping_memory = root
    db.add(src)


def build_initial_shipment_field_mapping(headers: list[str], source: SourceDefinition | None) -> dict[str, str]:
    """Map file header -> canonical shipment field using saved source memory, template aliases, and heuristics."""
    template = _effective_mapping_template(source)
    aliases: dict[str, str] = {}
    for canonical, meta in template.items():
        if canonical not in SHIPMENT_CANONICAL_TARGETS:
            continue
        if not isinstance(meta, dict):
            continue
        for a in meta.get("aliases", []) or []:
            if isinstance(a, str) and a.strip():
                aliases[_norm_header(a)] = canonical

    allowed_targets = set(SHIPMENT_CANONICAL_TARGETS)
    memory = load_by_header_norm(source) if source else {}
    mapping: dict[str, str] = {}
    for col in headers:
        if not isinstance(col, str) or not col.strip():
            continue
        nh = norm_header_key(col)
        if nh:
            entry = memory.get(nh)
            if isinstance(entry, dict):
                tgt = entry.get("target")
                if tgt and str(tgt).strip() in allowed_targets:
                    mapping[col] = str(tgt).strip()

    for col in headers:
        if not isinstance(col, str) or not col.strip():
            continue
        if col in mapping:
            continue
        key = _norm_header(col)
        if key in aliases:
            mapping[col] = aliases[key]
            continue
        # Heuristics for common OEM spellings (subset of legacy ``_extract_common`` names).
        if key in ("bill to", "bill_to"):
            mapping[col] = "bill_to_raw"
        elif key in ("ship to", "ship_to"):
            mapping[col] = "ship_to_raw"
        elif key in (
            "disti",
            "distributor",
            "distributor code",
            "distributor name",
            "distributor_name",
            "distributor_code",
            "disti_code",
            "disti name",
            "disti_name",
        ):
            mapping[col] = "distributor_token"
        elif key in ("operating unit", "ou name", "ou_name"):
            mapping[col] = "operating_unit"
        elif key in ("order no.", "order no", "order number", "order_no"):
            mapping[col] = "order_no"
        elif key in ("order line", "order_line"):
            mapping[col] = "order_line"
        elif key in ("delivery no", "delivery no.", "delivery number", "delivery_no", "delivery no "):
            mapping[col] = "delivery_no"
        elif key in ("invoice line", "invoice_line"):
            mapping[col] = "invoice_line"
        elif key == "item":
            mapping[col] = "item_code"
        elif key in ("sales model name", "sales_model_name"):
            mapping[col] = "sales_model_name"
        elif key in ("customer item", "customer_item"):
            mapping[col] = "customer_item"
        elif key in ("ean code", "ean_code"):
            mapping[col] = "ean_code"
        elif key in ("upc code", "upc_code"):
            mapping[col] = "upc_code"
        elif key in ("mpor item no.", "mpor item no", "mpor_item_no"):
            mapping[col] = "mpor_item_no"
        elif key in ("qty", "qty "):
            mapping[col] = "quantity"
        elif key in ("unit price", "unit_price"):
            mapping[col] = "unit_price"
        elif key == "amount":
            mapping[col] = "amount"
        elif key == "currency":
            mapping[col] = "currency_code"
        elif key in ("ship confirm date", "ship_confirm_date"):
            mapping[col] = "ship_confirm_date"
        elif key in ("schedule ship date", "schedule_ship_date"):
            mapping[col] = "schedule_ship_date"
        elif key in ("promise date", "promise_date"):
            mapping[col] = "promise_date"
        elif key in ("exwork date", "exwork date ", "exwork_date"):
            mapping[col] = "exwork_date"
        elif "erd" in key and "revenue" in key:
            mapping[col] = "erd_date"
        elif key in (
            "est pod date",
            "est_pod_date",
            "estimated pod date",
            "estimated proof of delivery",
            "expected delivery date",
            "expected delivery",
        ):
            mapping[col] = "est_pod_date"
        elif key in (
            "pod date",
            "pod_date",
            "proof of delivery",
            "actual delivery date",
            "actual delivery",
            "delivery confirmed date",
        ):
            mapping[col] = "pod_date"
        elif key in (
            "customer remarks",
            "customer remark",
            "customer_remarks",
        ):
            mapping[col] = "customer_dealer_token"
    return mapping


def sanitize_shipment_field_mapping(headers: list[str], raw: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Drop unknown headers / targets; return (clean_mapping, notices)."""
    notices: list[dict[str, str]] = []
    header_set = {h for h in headers if isinstance(h, str) and h.strip()}
    allowed = set(SHIPMENT_CANONICAL_TARGETS)
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or k not in header_set:
            continue
        if not isinstance(v, str) or not v.strip():
            continue
        tgt = v.strip()
        if tgt not in allowed:
            notices.append({"code": "unknown_shipment_target", "message": f"Ignored unknown target {tgt!r} for column {k!r}."})
            continue
        out[k] = tgt
    return out, notices


def shipment_mapping_gate_errors(mapping: dict[str, str]) -> list[dict[str, str]]:
    """Blocking issues before running shipment validation."""
    inv = {v for v in mapping.values()}
    errs: list[dict[str, str]] = []
    if not inv.intersection({"item_code", "ean_code", "upc_code", "sales_model_name"}):
        errs.append(
            {
                "code": "missing_product_column",
                "message": "Map at least one product column (Item, EAN, UPC, or Sales model name).",
            }
        )
    if not inv.intersection({"bill_to_raw", "ship_to_raw", "distributor_token"}):
        errs.append(
            {
                "code": "missing_distributor_party",
                "message": "Map at least one of Bill To, Ship To, or Distributor for distributor resolution.",
            }
        )
    return errs


def _union_frame_headers(frames: list[tuple[Any, Any, str, str]]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for _sn, frame, _rt, _ls in frames:
        if frame is None or not len(frame.columns):
            continue
        for c in frame.columns:
            s = str(c).strip() if c is not None else ""
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
    return out


def infer_shipment_import_job_sync(db: Session, job_id: int) -> ImportJob:
    """Read stored raw file, infer headers, set initial field_mapping (no evidence line writes)."""
    job = db.scalar(
        select(ImportJob)
        .options(joinedload(ImportJob.source).joinedload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
    )
    if not job or (job.template_slug or "") != "inbound_shipments":
        raise ValueError("infer_shipment_import_job_sync requires an inbound_shipments import job")

    raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job_id)).first()
    if not raw:
        raise ValueError("infer_shipment_import_job_sync requires raw file metadata")

    storage = get_storage_backend()
    data = storage.read(raw.storage_key)
    from app.ingestion.infer import infer_schema
    from app.services.imports.dsi_mapping_workflow import column_samples_from_schema_dict
    from app.services.imports.shipment_evidence_import import _load_frames_for_job

    frames = _load_frames_for_job(job, pd.DataFrame(), data)

    headers = _union_frame_headers(frames)
    mapping = build_initial_shipment_field_mapping(headers, job.source)
    mapping, notices = sanitize_shipment_field_mapping(headers, mapping)

    meta_reports: list[dict[str, Any]] = []
    tabular_column_infer: dict[str, Any] | None = None
    for sn, frame, rt, ls in frames:
        meta_reports.append(
            {
                "sheet": sn,
                "columns": [str(c) for c in (frame.columns if frame is not None else [])],
                "report_type": rt,
                "line_state": ls,
                "row_count": int(len(frame)) if frame is not None else 0,
            }
        )
        if tabular_column_infer is None and frame is not None and len(frame.columns) > 0 and len(frame) > 0:
            try:
                tabular_column_infer = infer_schema(frame)
            except Exception:
                tabular_column_infer = None

    inferred: dict[str, Any] = {
        "kind": "shipment_workbook",
        "sheets": meta_reports,
        "mapping_notices": notices,
    }
    if tabular_column_infer is not None:
        inferred["tabular_column_infer"] = tabular_column_infer
        inferred["column_samples"] = column_samples_from_schema_dict(tabular_column_infer)

    job.file_headers = headers
    job.field_mapping = mapping
    job.inferred_schema = inferred
    job.stage = "shipment_mapping_ready"
    job.status = "pending"
    job.error_summary = None
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def shipment_mapping_state_dict(job: ImportJob) -> dict[str, Any]:
    from app.services.imports.dsi_mapping_workflow import column_samples_from_schema_dict

    headers = list(job.file_headers or [])
    raw_mapping = dict(job.field_mapping or {})
    mapping, notices = sanitize_shipment_field_mapping(headers, raw_mapping)
    gate = shipment_mapping_gate_errors(mapping)
    inf = job.inferred_schema if isinstance(job.inferred_schema, dict) else {}
    sch = inf.get("tabular_column_infer")
    samples: dict[str, list[str]] = {}
    if isinstance(sch, dict):
        samples = column_samples_from_schema_dict(sch)
    elif isinstance(inf.get("column_samples"), dict):
        raw_s = inf["column_samples"]
        samples = {str(k): list(v) for k, v in raw_s.items() if isinstance(k, str) and isinstance(v, list)}
    return {
        "id": job.id,
        "stage": job.stage,
        "status": job.status,
        "error_summary": job.error_summary,
        "file_headers": headers,
        "field_mapping": mapping,
        "canonical_targets": list(SHIPMENT_CANONICAL_TARGETS),
        "blocking_mapping_errors": gate,
        "mapping_valid": len(gate) == 0,
        "mapping_adjustment_notices": notices,
        "column_samples": samples,
        "field_target_descriptions": dict(SHIPMENT_FIELD_TARGET_DESCRIPTIONS),
    }
