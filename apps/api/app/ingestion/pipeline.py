"""Import pipeline orchestration (MVP: synchronous, explainable stages)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.ingestion.infer import infer_schema, read_tabular
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct, DimRegion
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata, SourceDefinition
from app.models.mapping import EntityMappingQueue
from app.services.catalog.product_import_sync import sync_bulk_upsert_products_from_rows
from app.ingestion.pipeline_registry import extend_import_pipeline_handlers
from app.services.imports.distributor_sales_inventory import process_distributor_sales_inventory
from app.services.imports.import_job_background_metadata import persist_clear_background_task_metadata
from app.services.imports.shipment_evidence_import import process_shipment_evidence_import
from app.services.imports.historical_lineup import process_historical_lineup_import
from app.storage.local import get_storage_backend


STAGE_UPLOADED = "uploaded"
STAGE_RAW_STORED = "raw_stored"
STAGE_INFERRED = "schema_inferred"
STAGE_MAPPED = "fields_mapped"
STAGE_VALIDATED = "validated"
STAGE_LOADED = "loaded"
STAGE_FAILED = "failed"

ALLOWED_CUSTOMER_STATUS = {"active", "inactive", "onboarding", "blocked"}
ALLOWED_PARTNER_TIER = {"strategic", "tier_1", "tier_2", "tier_3", "core", "long_tail"}


def effective_mapping_template(source: SourceDefinition | None) -> dict[str, Any]:
    """Merge ImportTemplate.expected_columns with per-source overrides (alias shape)."""
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
            else:
                merged.setdefault(k, {"aliases": []})
    return merged


def default_field_mapping(inferred_columns: list[str], template: dict[str, Any] | None) -> dict[str, str]:
    """Map source column names to canonical fields using template aliases or heuristics."""
    template = template or {}
    aliases: dict[str, str] = {}
    for canonical, meta in template.items():
        for alias in meta.get("aliases", []) if isinstance(meta, dict) else []:
            aliases[alias.lower()] = canonical

    mapping: dict[str, str] = {}
    for col in inferred_columns:
        key = col.strip().lower()
        if key in aliases:
            mapping[col] = aliases[key]
            continue
        if key in {
            "customer_code",
            "customer_name",
            "distributor_code",
            "distributor_name",
            "customer_status",
            "partner_tier",
            "account_owner_internal",
            "region_code",
            "channel_code",
            "preferred_distributor_code",
            "notes_summary",
        }:
            mapping[col] = key
            continue
        if ("customer" in key and "code" in key) or key in {"account_code", "customer_id"}:
            mapping[col] = "customer_code"
        elif ("customer" in key and "name" in key) or key in {"account_name"}:
            mapping[col] = "customer_name"
        elif ("distributor" in key and "code" in key) or key in {"distributor_id"}:
            mapping[col] = "distributor_code"
        elif ("distributor" in key and "name" in key) or key in {"canonical_name"}:
            mapping[col] = "distributor_name"
        elif "customer_status" in key or key == "status":
            mapping[col] = "customer_status"
        elif "partner_tier" in key or key == "tier":
            mapping[col] = "partner_tier"
        elif "account_owner" in key:
            mapping[col] = "account_owner_internal"
        elif key == "region_code" or ("region" in key and "customer" not in key):
            mapping[col] = "region_code"
        elif key == "channel_code" or ("channel" in key and "customer" not in key):
            mapping[col] = "channel_code"
        elif "preferred_distributor" in key or key == "distributor_code":
            mapping[col] = "preferred_distributor_code"
        elif "notes" in key:
            mapping[col] = "notes_summary"
        elif "sku" in key or ("item" in key and "name" not in key):
            mapping[col] = "sku"
        elif key in ("product_identifier", "product_id", "item_code"):
            mapping[col] = "product_identifier"
        elif key in ("distributor_token",):
            mapping[col] = "distributor_token"
        elif key in ("quantity_sold", "sellout_qty"):
            mapping[col] = "quantity_sold"
        elif key in ("stock_on_hand", "soh", "inventory_qty"):
            mapping[col] = "stock_on_hand"
        elif key in ("transaction_date", "snapshot_date"):
            mapping[col] = key
        elif key in ("customer_dealer_token", "dealer_group_token"):
            mapping[col] = key
        elif "qty" in key or "quantity" in key or "on_hand" in key:
            mapping[col] = "quantity"
        elif "price" in key:
            mapping[col] = "price"
        elif key in ("name", "title", "product_name", "description") or ("name" in key and "sku" not in key):
            mapping[col] = "name"
        elif "category" in key or key == "cat":
            mapping[col] = "category"
        elif "channel" in key and "customer" not in key:
            mapping[col] = "channel_code"
        elif "form" in key or "factor" in key:
            mapping[col] = "form_factor"
        elif "price_band" in key or ("band" in key and "price" in key):
            mapping[col] = "price_band"
    return mapping


def _process_inventory_sku_gate(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    errors = 0
    if "sku" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_sku_mapping",
                message="Could not infer SKU column; manual mapping required.",
            )
        )
        return 1

    sku_col = next(k for k, v in mapping.items() if v == "sku")
    products = {p.sku.lower(): p for p in db.scalars(select(DimProduct)).all()}

    for idx, row in df.iterrows():
        raw_sku = str(row.get(sku_col, "")).strip()
        if not raw_sku:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="warning",
                    code="blank_sku",
                    message="Blank SKU in row",
                    raw_payload=row.where(pd.notnull(row), None).to_dict(),
                )
            )
            continue
        match = products.get(raw_sku.lower())
        if not match:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="error",
                    code="unmatched_product",
                    message=f"No master match for SKU '{raw_sku}'",
                    raw_payload=row.where(pd.notnull(row), None).to_dict(),
                )
            )
            db.add(
                EntityMappingQueue(
                    entity_type="product",
                    raw_value=raw_sku,
                    normalized_value=raw_sku.lower(),
                    suggested_entity_id=None,
                    match_method="none",
                    confidence_score=0,
                    status="review_required",
                    job_id=job.id,
                    context={"row": int(idx) + 1},
                )
            )
            errors += 1
    return errors


def _process_stub(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    db.add(
        ImportRowResult(
            job_id=job.id,
            row_number=0,
            severity="info",
            code="stub_pipeline",
            message="This import template is not wired to a full loader yet; file is stored and schema inferred only.",
        )
    )
    return 0


def _process_product_master(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    errors = 0
    if "sku" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_sku_mapping",
                message="Could not infer SKU column; check headers against the template.",
            )
        )
        return 1
    if "name" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_name_mapping",
                message="Could not infer product name column; expected name / product_name / title.",
            )
        )
        return 1

    sku_col = next(k for k, v in mapping.items() if v == "sku")
    name_col = next(k for k, v in mapping.items() if v == "name")
    cat_col = next((k for k, v in mapping.items() if v == "category"), None)
    ch_col = next((k for k, v in mapping.items() if v == "channel_code"), None)

    channels = {c.code.strip().lower(): c.id for c in db.scalars(select(DimChannel)).all()}
    payloads: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        sku = str(row.get(sku_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        if not sku:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="warning",
                    code="blank_sku",
                    message="Blank SKU in row",
                    raw_payload=row.where(pd.notnull(row), None).to_dict(),
                )
            )
            continue
        if not name:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=int(idx) + 1,
                    severity="error",
                    code="blank_name",
                    message="Blank product name in row",
                    raw_payload=row.where(pd.notnull(row), None).to_dict(),
                )
            )
            errors += 1
            continue
        cat = None
        if cat_col:
            v = row.get(cat_col)
            if v is not None and str(v).strip():
                cat = str(v).strip()
        ch_raw = None
        if ch_col:
            v = row.get(ch_col)
            if v is not None and str(v).strip():
                ch_raw = str(v).strip()
        if ch_raw and ch_raw.lower() not in channels:
            from app.services.imports.ai_resolver_wiring import try_ai_token_resolution

            ch_candidates = [
                {"id": int(cid), "code": code, "name": code}
                for code, cid in list(channels.items())[:20]
            ]
            ai_ch_id, _, _ = try_ai_token_resolution(
                raw_token=ch_raw,
                token_type="customer",
                candidates=ch_candidates,
                import_type="product_master",
                job_id=int(job.id),
                extra_context={"match_field": "channel_code"},
            )
            if ai_ch_id is not None:
                for code, cid in channels.items():
                    if int(cid) == int(ai_ch_id):
                        ch_raw = code
                        break
            else:
                db.add(
                    ImportRowResult(
                        job_id=job.id,
                        row_number=int(idx) + 1,
                        severity="error",
                        code="unknown_channel",
                        message=f"Unknown channel_code {ch_raw!r}",
                        raw_payload=row.where(pd.notnull(row), None).to_dict(),
                    )
                )
                errors += 1
                continue
        payloads.append({"sku": sku, "name": name, "category": cat, "channel_code": ch_raw})

    if errors:
        return errors

    if job.import_mode == "apply":
        stats = sync_bulk_upsert_products_from_rows(db, payloads)
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="product_master_applied",
                message=f"Applied product upsert: created={stats['created']}, updated={stats['updated']}, rows={stats['total']}.",
            )
        )
        job.stage = STAGE_LOADED
    else:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="product_master_validated",
                message=f"Validated {len(payloads)} product row(s); import_mode=validate — no catalog writes performed.",
            )
        )

    return 0


def _process_customer_master(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    errors = 0
    normalized_mapping = {col: ("customer_name" if target == "name" else target) for col, target in mapping.items()}
    if "customer_code" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_customer_code_mapping",
                message="Could not infer customer_code column; expected customer_code/code/account_code.",
            )
        )
        return 1
    if "customer_name" not in normalized_mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_customer_name_mapping",
                message="Could not infer customer_name column; expected customer_name/name/account_name.",
            )
        )
        return 1

    code_col = next(k for k, v in mapping.items() if v == "customer_code")
    name_col = next(k for k, v in normalized_mapping.items() if v == "customer_name")
    status_col = next((k for k, v in mapping.items() if v == "customer_status"), None)
    tier_col = next((k for k, v in mapping.items() if v == "partner_tier"), None)
    owner_col = next((k for k, v in mapping.items() if v == "account_owner_internal"), None)
    notes_col = next((k for k, v in mapping.items() if v == "notes_summary"), None)
    region_col = next((k for k, v in mapping.items() if v == "region_code"), None)
    channel_col = next((k for k, v in mapping.items() if v == "channel_code"), None)
    dist_col = next((k for k, v in mapping.items() if v == "preferred_distributor_code"), None)

    regions = {r.code.strip().lower(): r.id for r in db.scalars(select(DimRegion)).all()}
    channels = {c.code.strip().lower(): c.id for c in db.scalars(select(DimChannel)).all()}
    distributors = {d.code.strip().lower(): d.id for d in db.scalars(select(DimDistributor)).all()}
    existing = {c.code.strip().lower(): c for c in db.scalars(select(DimCustomer)).all()}
    seen_codes: set[str] = set()
    pending: list[dict[str, Any]] = []

    for idx, row in df.iterrows():
        row_number = int(idx) + 1
        code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        raw_payload = row.where(pd.notnull(row), None).to_dict()
        if not code:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=row_number,
                    severity="error",
                    code="blank_customer_code",
                    message="Blank customer_code in row",
                    raw_payload=raw_payload,
                )
            )
            errors += 1
            continue
        code_key = code.lower()
        if code_key in seen_codes:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=row_number,
                    severity="error",
                    code="duplicate_customer_code_in_file",
                    message=f"Duplicate customer_code in file: {code!r}",
                    raw_payload=raw_payload,
                )
            )
            errors += 1
            continue
        seen_codes.add(code_key)
        if not name:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=row_number,
                    severity="error",
                    code="blank_customer_name",
                    message="Blank customer_name in row",
                    raw_payload=raw_payload,
                )
            )
            errors += 1
            continue

        status = "active"
        if status_col:
            candidate = str(row.get(status_col, "")).strip().lower() or "active"
            if candidate not in ALLOWED_CUSTOMER_STATUS:
                db.add(
                    ImportRowResult(
                        job_id=job.id,
                        row_number=row_number,
                        severity="error",
                        code="invalid_customer_status",
                        message=f"Invalid customer_status {candidate!r}",
                        raw_payload=raw_payload,
                    )
                )
                errors += 1
                continue
            status = candidate

        partner_tier = None
        if tier_col:
            candidate = str(row.get(tier_col, "")).strip().lower()
            if candidate:
                if candidate not in ALLOWED_PARTNER_TIER:
                    db.add(
                        ImportRowResult(
                            job_id=job.id,
                            row_number=row_number,
                            severity="error",
                            code="invalid_partner_tier",
                            message=f"Invalid partner_tier {candidate!r}",
                            raw_payload=raw_payload,
                        )
                    )
                    errors += 1
                    continue
                partner_tier = candidate

        region_id = None
        if region_col:
            candidate = str(row.get(region_col, "")).strip()
            if candidate:
                region_id = regions.get(candidate.lower())
                if region_id is None:
                    from app.services.imports.ai_resolver_wiring import try_ai_token_resolution

                    reg_candidates = [
                        {"id": int(rid), "code": code, "name": code}
                        for code, rid in list(regions.items())[:20]
                    ]
                    ai_rid, _, _ = try_ai_token_resolution(
                        raw_token=candidate,
                        token_type="customer",
                        candidates=reg_candidates,
                        import_type="customer_master",
                        job_id=int(job.id),
                        extra_context={"match_field": "region_code"},
                    )
                    if ai_rid is not None:
                        region_id = ai_rid
                    else:
                        db.add(
                            ImportRowResult(
                                job_id=job.id,
                                row_number=row_number,
                                severity="error",
                                code="unknown_region_code",
                                message=f"Unknown region_code {candidate!r}",
                                raw_payload=raw_payload,
                            )
                        )
                        errors += 1
                        continue

        channel_id = None
        if channel_col:
            candidate = str(row.get(channel_col, "")).strip()
            if candidate:
                channel_id = channels.get(candidate.lower())
                if channel_id is None:
                    from app.services.imports.ai_resolver_wiring import try_ai_token_resolution

                    ch_candidates = [
                        {"id": int(cid), "code": code, "name": code}
                        for code, cid in list(channels.items())[:20]
                    ]
                    ai_cid, _, _ = try_ai_token_resolution(
                        raw_token=candidate,
                        token_type="customer",
                        candidates=ch_candidates,
                        import_type="customer_master",
                        job_id=int(job.id),
                        extra_context={"match_field": "channel_code"},
                    )
                    if ai_cid is not None:
                        channel_id = ai_cid
                    else:
                        db.add(
                            ImportRowResult(
                                job_id=job.id,
                                row_number=row_number,
                                severity="error",
                                code="unknown_channel_code",
                                message=f"Unknown channel_code {candidate!r}",
                                raw_payload=raw_payload,
                            )
                        )
                        errors += 1
                        continue

        preferred_distributor_id = None
        if dist_col:
            candidate = str(row.get(dist_col, "")).strip()
            if candidate:
                preferred_distributor_id = distributors.get(candidate.lower())
                if preferred_distributor_id is None:
                    from app.services.imports.ai_resolver_wiring import (
                        distributor_candidates,
                        try_ai_token_resolution,
                    )

                    ai_did, _, _ = try_ai_token_resolution(
                        raw_token=candidate,
                        token_type="distributor",
                        candidates=distributor_candidates(db, candidate),
                        import_type="customer_master",
                        job_id=int(job.id),
                        extra_context={"match_field": "preferred_distributor_code"},
                    )
                    if ai_did is not None:
                        preferred_distributor_id = ai_did
                    else:
                        db.add(
                            ImportRowResult(
                                job_id=job.id,
                                row_number=row_number,
                                severity="error",
                                code="unknown_preferred_distributor_code",
                                message=f"Unknown preferred_distributor_code {candidate!r}",
                                raw_payload=raw_payload,
                            )
                        )
                        errors += 1
                        continue

        pending.append(
            {
                "code": code,
                "name": name,
                "customer_status": status,
                "partner_tier": partner_tier,
                "account_owner_internal": str(row.get(owner_col, "")).strip() or None if owner_col else None,
                "notes_summary": str(row.get(notes_col, "")).strip() or None if notes_col else None,
                "region_id": region_id,
                "channel_id": channel_id,
                "preferred_distributor_id": preferred_distributor_id,
                "row_number": row_number,
                "exists": code_key in existing,
            }
        )

    if errors:
        return errors

    if job.import_mode == "apply":
        created = 0
        updated = 0
        for item in pending:
            current = existing.get(item["code"].lower())
            if current:
                current.name = item["name"]
                current.customer_status = item["customer_status"]
                current.partner_tier = item["partner_tier"]
                current.account_owner_internal = item["account_owner_internal"]
                current.notes_summary = item["notes_summary"]
                current.region_id = item["region_id"]
                current.channel_id = item["channel_id"]
                current.preferred_distributor_id = item["preferred_distributor_id"]
                updated += 1
            else:
                db.add(
                    DimCustomer(
                        code=item["code"],
                        name=item["name"],
                        customer_status=item["customer_status"],
                        partner_tier=item["partner_tier"],
                        account_owner_internal=item["account_owner_internal"],
                        notes_summary=item["notes_summary"],
                        region_id=item["region_id"],
                        channel_id=item["channel_id"],
                        preferred_distributor_id=item["preferred_distributor_id"],
                    )
                )
                created += 1
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="customer_master_applied",
                message=f"Applied customer upsert: created={created}, updated={updated}, rows={len(pending)}.",
            )
        )
        job.stage = STAGE_LOADED
        job.archived_at = datetime.now(timezone.utc)
    else:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="customer_master_validated",
                message=f"Validated {len(pending)} customer row(s); import_mode=validate — no writes performed.",
            )
        )
    return 0


def _process_distributor_master(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    errors = 0
    normalized_mapping = {col: ("distributor_name" if target == "name" else target) for col, target in mapping.items()}
    if "distributor_code" not in normalized_mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_distributor_code_mapping",
                message="Could not infer distributor_code column; expected distributor_code/code/distributor_id.",
            )
        )
        return 1
    if "distributor_name" not in normalized_mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_distributor_name_mapping",
                message="Could not infer distributor_name column; expected distributor_name/name/canonical_name.",
            )
        )
        return 1

    code_col = next(k for k, v in normalized_mapping.items() if v == "distributor_code")
    name_col = next(k for k, v in normalized_mapping.items() if v == "distributor_name")
    existing = {d.code.strip().lower(): d for d in db.scalars(select(DimDistributor)).all()}
    seen_codes: set[str] = set()
    pending: list[dict[str, Any]] = []

    for idx, row in df.iterrows():
        row_number = int(idx) + 1
        code = str(row.get(code_col, "")).strip()
        name = str(row.get(name_col, "")).strip()
        raw_payload = row.where(pd.notnull(row), None).to_dict()
        if not code:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=row_number,
                    severity="error",
                    code="blank_distributor_code",
                    message="Blank distributor_code in row",
                    raw_payload=raw_payload,
                )
            )
            errors += 1
            continue
        key = code.lower()
        if key in seen_codes:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=row_number,
                    severity="error",
                    code="duplicate_distributor_code_in_file",
                    message=f"Duplicate distributor_code in file: {code!r}",
                    raw_payload=raw_payload,
                )
            )
            errors += 1
            continue
        seen_codes.add(key)
        if not name:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=row_number,
                    severity="error",
                    code="blank_distributor_name",
                    message="Blank distributor_name in row",
                    raw_payload=raw_payload,
                )
            )
            errors += 1
            continue

        resolved_code = code
        exists_in_master = key in existing
        if not exists_in_master:
            from app.services.imports.ai_resolver_wiring import (
                distributor_candidates_from_dim_list,
                try_ai_token_resolution,
            )

            ai_did, _, _ = try_ai_token_resolution(
                raw_token=code,
                token_type="distributor",
                candidates=distributor_candidates_from_dim_list(list(existing.values()), code),
                import_type="distributor_master",
                job_id=int(job.id),
                extra_context={"match_field": "distributor_code"},
            )
            if ai_did is not None:
                for dist in existing.values():
                    dist_id = getattr(dist, "id", None)
                    if dist_id is not None and int(dist_id) == int(ai_did):
                        resolved_code = dist.code
                        exists_in_master = True
                        break

        pending.append({"code": resolved_code, "name": name})

    if errors:
        return errors

    if job.import_mode == "apply":
        created = 0
        updated = 0
        for item in pending:
            current = existing.get(item["code"].lower())
            if current:
                current.name = item["name"]
                updated += 1
            else:
                db.add(DimDistributor(code=item["code"], name=item["name"]))
                created += 1
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="distributor_master_applied",
                message=f"Applied distributor upsert: created={created}, updated={updated}, rows={len(pending)}.",
            )
        )
        job.stage = STAGE_LOADED
        job.archived_at = datetime.now(timezone.utc)
    else:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="info",
                code="distributor_master_validated",
                message=f"Validated {len(pending)} distributor row(s); import_mode=validate — no writes performed.",
            )
        )
    return 0


def process_import_job_sync(db: Session, job_id: int, on_progress: Any = None) -> ImportJob:
    job = db.scalar(
        select(ImportJob)
        .options(joinedload(ImportJob.source).joinedload(SourceDefinition.import_template))
        .where(ImportJob.id == job_id)
    )
    if not job:
        raise ValueError("job not found")

    # Product Master jobs using the mapping workflow store file_headers; do not run legacy one-shot pipeline.
    if job.template_slug == "product_master" and job.file_headers is not None:
        db.refresh(job)
        return job

    try:
        storage = get_storage_backend()
        raw = db.scalars(select(RawFileMetadata).where(RawFileMetadata.job_id == job_id)).one()
        data = storage.read(raw.storage_key)

        job.stage = STAGE_RAW_STORED
        job.started_at = datetime.now(timezone.utc)
        job.status = "running"
        from app.services.imports.import_job_background_metadata import persist_pipeline_worker_started_at

        persist_pipeline_worker_started_at(db, job)
        db.flush()

        source = job.source

        tpl = source.import_template if source else None
        fallback_handlers_by_slug = {
            "distributor_master": "distributor_master_upsert",
            "customer_master": "customer_master_upsert",
            "product_master": "product_master_upsert",
            "distributor_inventory": "distributor_sales_inventory",
            "historical_lineup": "historical_lineup_workbook",
            "inbound_shipments": "shipment_evidence_import",
        }
        raw_handler = (tpl.pipeline_handler if tpl else None) or fallback_handlers_by_slug.get(
            job.template_slug or "", "inventory_sku_gate"
        )
        handler = str(raw_handler or "").strip()
        handler_aliases = {
            "historical_lineup": "historical_lineup_workbook",
        }
        handler = handler_aliases.get(handler, handler)

        if handler == "historical_lineup_workbook":
            errors = process_historical_lineup_import(db, job, job.file_name, data)
            job.stage = STAGE_VALIDATED
            job.status = "completed_with_errors" if errors else "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.error_summary = f"{errors} rows require attention" if errors else None
            if not errors and job.import_mode == "apply":
                job.stage = STAGE_LOADED
            persist_clear_background_task_metadata(db, job)
            db.commit()
            db.refresh(job)
            return job

        if (job.template_slug or "") == "inbound_shipments":
            df = pd.DataFrame()
            mapping = dict(job.field_mapping or {})
            job.stage = STAGE_MAPPED
        else:
            df = read_tabular(job.file_name, data)
            schema = infer_schema(df)
            job.inferred_schema = schema
            job.stage = STAGE_INFERRED

            cols = [c["name"] for c in schema["columns"]]
            template = effective_mapping_template(source)
            mapping = job.field_mapping or default_field_mapping(cols, template)
            if job.template_slug == "distributor_inventory":
                from app.services.imports.dsi_mapping_workflow import (
                    apply_exact_raw_customer_header_overrides,
                    apply_dsi_customer_column_target_resolution,
                    apply_dsi_product_identifier_sample_inference,
                    column_samples_from_schema_dict,
                    sanitize_dsi_field_mapping,
                )

                if not job.field_mapping:
                    samp = column_samples_from_schema_dict(schema)
                    mapping = apply_exact_raw_customer_header_overrides(cols, mapping)
                    mapping = apply_dsi_customer_column_target_resolution(cols, mapping)
                    mapping = apply_dsi_product_identifier_sample_inference(cols, mapping, samp)
                mapping, _ = sanitize_dsi_field_mapping(cols, mapping)
            job.field_mapping = mapping
            job.stage = STAGE_MAPPED

        handlers = {
            "stub_noop": _process_stub,
            "distributor_master_upsert": _process_distributor_master,
            "customer_master_upsert": _process_customer_master,
            "product_master_upsert": _process_product_master,
            "inventory_sku_gate": _process_inventory_sku_gate,
            "distributor_sales_inventory": process_distributor_sales_inventory,
            "shipment_evidence_import": process_shipment_evidence_import,
            "historical_lineup_workbook": lambda _db, _job, _df, _mapping: process_historical_lineup_import(
                _db, _job, _job.file_name, data
            ),
        }
        extend_import_pipeline_handlers(handlers)
        processor = handlers.get(handler)
        if processor is None:
            db.add(
                ImportRowResult(
                    job_id=job.id,
                    row_number=0,
                    severity="error",
                    code="unknown_pipeline_handler",
                    message=f"Unrecognized pipeline handler {handler!r} for template {job.template_slug!r}.",
                )
            )
            errors = 1
        elif handler in ("distributor_sales_inventory", "shipment_evidence_import") and on_progress is not None:
            errors = processor(db, job, df, mapping, on_progress=on_progress)
        else:
            errors = processor(db, job, df, mapping)

        meta_after = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
        if handler == "customer_sell_through" and meta_after.get("customer_sellthrough_error"):
            job.stage = STAGE_FAILED
            job.status = "completed_with_errors"
            if not job.error_summary:
                err = meta_after.get("customer_sellthrough_error")
                if isinstance(err, dict) and err.get("message"):
                    job.error_summary = str(err["message"])[:500]
        else:
            if handler == "customer_sell_through" and (job.import_mode or "").strip().lower() == "apply" and not errors:
                job.stage = STAGE_LOADED
            else:
                job.stage = STAGE_VALIDATED
            job.status = "completed_with_errors" if errors else "completed"
            job.error_summary = f"{errors} rows require attention" if errors else None
        job.completed_at = datetime.now(timezone.utc)
        persist_clear_background_task_metadata(db, job)
        db.commit()
        db.refresh(job)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(ImportJob, job_id)
        if job:
            job.status = "failed"
            job.stage = STAGE_FAILED
            job.error_summary = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            persist_clear_background_task_metadata(db, job)
            db.commit()
            db.refresh(job)
        return job

    if (job.template_slug or "") == "distributor_inventory" and (job.import_mode or "").strip() == "validate":
        from app.ingestion.dsi_validate_post_sync import run_dsi_validate_post_import_orchestration

        run_dsi_validate_post_import_orchestration(db, job.id)
        db.commit()
        db.refresh(job)

    return job
