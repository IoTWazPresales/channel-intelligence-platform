from __future__ import annotations

import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session_sync import SessionLocal
from app.main import app
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata, SourceDefinition
from app.ingestion.pipeline import process_import_job_sync
from app.services.imports.historical_lineup import _build_header_map, parse_historical_workbook
from app.services.seed_demo import _seed_import_core
from app.storage.local import get_storage_backend


def _build_workbook_bytes() -> bytes:
    data_lineup = pd.DataFrame(
        [
            {
                "Customer": "CUST-HL-01",
                "Distributor": "DIST-HL-01",
                "Channel": "RET",
                "Period": "2026-04-01",
                "SKU": "SKU-HL-01",
                "Qty": "12",
                "MSRP": "100",
                "Promo Price": "90",
                "Disti Margin": "8",
                "Notes": "valid row",
            },
            {
                "Customer": "UNKNOWN-CUST",
                "Distributor": "DIST-HL-01",
                "Channel": "RET",
                "Period": "bad-date",
                "SKU": "SKU-NOPE",
                "Qty": "abc",
                "MSRP": "100",
                "Promo Price": "80",
                "Disti Margin": "7",
                "Dealer Margin": "2",
                "Notes": "bad row",
            },
            {
                "Customer": "Grand Total",
                "Distributor": None,
                "Channel": None,
                "Period": None,
                "SKU": None,
                "Qty": "999",
                "MSRP": None,
                "Promo Price": None,
            },
        ]
    )
    summary = pd.DataFrame([{"Some": "summary"}])
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        data_lineup.to_excel(writer, sheet_name="Historical Lineup Apr", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)
    return bio.getvalue()


def _build_nb_style_workbook_bytes() -> bytes:
    nb_rows = [
        ["", "", "", "", "", "2026 Q2 NEW PLAN"],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        [
            "Product Line",
            "Country",
            "Customer",
            "Segment",
            "Model name",
            "Part Number",
            "Base Unit",
            "Qty",
            "MSRP",
        ],
        ["NB", "ZA", "CUST-HL-01", "Vivobook", "M-NB-1", "SKU-HL-01", "BU-01", "12", "999"],
        ["NB", "ZA", "UNKNOWN-CUST", "Vivobook", "M-NB-2", "SKU-NOPE", "BU-02", "abc", "1000"],
    ]
    nb = pd.DataFrame(nb_rows)
    sheet1 = pd.DataFrame()
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        nb.to_excel(writer, sheet_name="NB", header=False, index=False)
        sheet1.to_excel(writer, sheet_name="Sheet1", header=False, index=False)
    return bio.getvalue()


def _ensure_historical_seed() -> int:
    with SessionLocal() as db:
        _seed_import_core(db)
        ch = db.scalar(select(DimChannel).where(DimChannel.code == "RET"))
        if not ch:
            ch = DimChannel(code="RET", name="Retail")
            db.add(ch)
            db.flush()
        if not db.scalar(select(DimDistributor).where(DimDistributor.code == "DIST-HL-01")):
            db.add(DimDistributor(code="DIST-HL-01", name="Dist HL"))
        if not db.scalar(select(DimCustomer).where(DimCustomer.code == "CUST-HL-01")):
            db.add(DimCustomer(code="CUST-HL-01", name="Cust HL", channel_id=ch.id))
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-HL-01")):
            db.add(DimProduct(sku="SKU-HL-01", name="Hist Product", category="Audio"))
        db.commit()

        src = db.scalar(select(SourceDefinition).where(SourceDefinition.code == "historical_lineup_default"))
        assert src is not None
        return src.id


def test_parse_historical_workbook_detects_candidate_sheet_and_summary_rows() -> None:
    sheets, schema = parse_historical_workbook("historical_lineup.xlsx", _build_workbook_bytes())
    assert schema["selected_sheets"] == ["Historical Lineup Apr"]
    assert "Summary" in schema["skipped_sheets"]
    dropped_codes = [r.diagnostics for r in sheets[0].rows if r.status == "dropped"]
    assert any("summary_row_dropped" in row_codes for row_codes in dropped_codes)


def test_parse_historical_workbook_detects_nb_sheet_with_header_row_4() -> None:
    sheets, schema = parse_historical_workbook("asus.xlsx", _build_nb_style_workbook_bytes())
    assert schema["selected_sheets"] == ["NB"]
    skipped = {x["sheet_name"]: x["reason"] for x in schema["skipped_sheet_details"]}
    assert skipped["Sheet1"] == "empty_sheet"
    assert sheets[0].header_row_number == 4
    assert schema["selected_sheet_details"][0]["header_row_number"] == 4
    assert schema["selected_sheet_details"][0]["row_count"] >= 2


def test_historical_lineup_validate_reports_row_diagnostics_and_partial_success() -> None:
    source_id = _ensure_historical_seed()
    workbook = _build_workbook_bytes()
    storage = get_storage_backend()
    with SessionLocal() as db:
        job = ImportJob(
            source_id=source_id,
            template_slug="historical_lineup",
            import_mode="validate",
            status="pending",
            stage="uploaded",
            file_name="historical_lineup.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        db.add(job)
        db.flush()
        key = f"imports/test/{job.id}/historical_lineup.xlsx"
        storage.save(key, workbook, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(workbook), checksum=None))
        db.commit()

        processed = process_import_job_sync(db, job.id)
        assert processed.template_slug == "historical_lineup"
        assert processed.stage == "validated"
        rows = db.scalars(select(ImportRowResult).where(ImportRowResult.job_id == processed.id)).all()
        codes = {row.code for row in rows}
        assert "historical_lineup_processed" in codes
        assert "historical_lineup_sheet_summary" in codes
        assert any(code in codes for code in {"unknown_customer", "unknown_product", "invalid_numeric", "invalid_quantity"})


def _build_custom_column_workbook_bytes(customer_col_name: str = "Buyer") -> bytes:
    """Workbook with a non-standard customer column name for mapping override tests."""
    rows = pd.DataFrame(
        [
            {
                customer_col_name: "CUST-HL-01",
                "Distributor": "DIST-HL-01",
                "Period": "2026-04-01",
                "Model name": "M-NB-1",
                "Part Number": "SKU-HL-01",
                "Qty": "5",
            },
            {
                customer_col_name: "UNKNOWN-CUST",
                "Distributor": "DIST-HL-01",
                "Period": "2026-04-01",
                "Model name": "M-NB-2",
                "Part Number": "SKU-NOPE",
                "Qty": "3",
            },
        ]
    )
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        rows.to_excel(writer, sheet_name="Historical Lineup Apr", index=False)
    return bio.getvalue()


def _build_ilike_customer_workbook_bytes(customer_value: str) -> bytes:
    """Workbook with a single data row using a given customer token."""
    rows = pd.DataFrame(
        [
            {
                "Customer": customer_value,
                "Distributor": "DIST-HL-01",
                "Period": "2026-04-01",
                "SKU": "SKU-HL-01",
                "Qty": "5",
            }
        ]
    )
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        rows.to_excel(writer, sheet_name="Historical Lineup Apr", index=False)
    return bio.getvalue()


def test_inferred_schema_includes_source_columns() -> None:
    """selected_sheet_details must include source_columns (raw workbook header tokens)."""
    sheets, schema = parse_historical_workbook("historical_lineup.xlsx", _build_workbook_bytes())
    assert sheets, "Expected at least one selected sheet"
    detail = schema["selected_sheet_details"][0]
    assert "source_columns" in detail, "source_columns missing from selected_sheet_details"
    source_cols = detail["source_columns"]
    assert isinstance(source_cols, list) and len(source_cols) > 0
    # The test workbook has columns: Customer, Distributor, Channel, Period, SKU, Qty, MSRP, …
    assert "Customer" in source_cols
    assert "SKU" in source_cols


def test_mapping_override_fixes_undetected_column() -> None:
    """If a workbook uses a non-standard column name, mapping_override should bind it.

    'Purchasing Contact' is not in _CANONICAL_ALIASES, so auto-detection will not
    find customer_token. The override explicitly maps it.
    """
    col = "Purchasing Contact"
    sheets_auto, _ = parse_historical_workbook(
        "lineup.xlsx", _build_custom_column_workbook_bytes(col)
    )
    assert sheets_auto, "Expected sheet"
    payloads_auto = [r.payload for r in sheets_auto[0].rows if r.status != "dropped"]
    # Without override, customer_token should not be present in the payload (not mapped).
    assert all(r.get("customer_token") is None for r in payloads_auto), (
        "Expected customer_token to be absent without override"
    )

    # With override, customer_token should be populated from the column.
    override = {"Historical Lineup Apr": {"customer_token": col}}
    sheets_override, _ = parse_historical_workbook(
        "lineup.xlsx", _build_custom_column_workbook_bytes(col), mapping_override=override
    )
    assert sheets_override
    payloads_override = [r.payload for r in sheets_override[0].rows if r.status != "dropped"]
    assert any(r.get("customer_token") is not None for r in payloads_override), (
        "Expected customer_token to be populated with override"
    )
    customer_values = [r.get("customer_token") for r in payloads_override if r.get("customer_token")]
    assert "CUST-HL-01" in customer_values


def test_mapping_override_merges_not_replaces() -> None:
    """Override only replaces the specified field; auto-detected fields are preserved."""
    override = {"Historical Lineup Apr": {"customer_token": "Buyer"}}
    sheets, _ = parse_historical_workbook(
        "lineup.xlsx", _build_custom_column_workbook_bytes("Buyer"), mapping_override=override
    )
    assert sheets
    # The mapping should include auto-detected fields (e.g. distributor_token, period_label)
    # as well as the overridden customer_token.
    effective_mapping = sheets[0].mapping
    assert "customer_token" in effective_mapping, "Overridden field should be in mapping"
    assert effective_mapping["customer_token"] == "Buyer"
    # At least one auto-detected field should still be present.
    auto_detected_present = any(
        k in effective_mapping for k in ("distributor_token", "period_label", "quantity_units")
    )
    assert auto_detected_present, "Auto-detected fields should be preserved after override"


def test_mapping_decisions_written_after_processing() -> None:
    """After process_import_job_sync, job.mapping_decisions holds the final effective mapping."""
    source_id = _ensure_historical_seed()
    workbook = _build_workbook_bytes()
    storage = get_storage_backend()
    with SessionLocal() as db:
        job = ImportJob(
            source_id=source_id,
            template_slug="historical_lineup",
            import_mode="validate",
            status="pending",
            stage="uploaded",
            file_name="historical_lineup.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        db.add(job)
        db.flush()
        key = f"imports/test/{job.id}/historical_lineup.xlsx"
        storage.save(key, workbook, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(workbook), checksum=None))
        db.commit()

        processed = process_import_job_sync(db, job.id)
        assert processed.mapping_decisions is not None
        assert isinstance(processed.mapping_decisions, dict)
        # mapping_decisions should contain sheet name(s) as keys.
        assert len(processed.mapping_decisions) > 0


def test_customer_ilike_fallback_resolves_partial_match() -> None:
    """Customer ILIKE fallback resolves when exactly one customer matches the partial token."""
    with SessionLocal() as db:
        _seed_import_core(db)
        ch = db.scalar(select(DimChannel).where(DimChannel.code == "RET"))
        if not ch:
            ch = DimChannel(code="RET", name="Retail")
            db.add(ch)
            db.flush()
        # Seed a customer with a distinct long name.
        ilike_code = "ILIKE-CUST-UNQ"
        ilike_name = "Unique ILIKE Customer Corp ZZZ"
        if not db.scalar(select(DimCustomer).where(DimCustomer.code == ilike_code)):
            db.add(DimCustomer(code=ilike_code, name=ilike_name, channel_id=ch.id))
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-HL-01")):
            db.add(DimProduct(sku="SKU-HL-01", name="Hist Product", category="Audio"))
        if not db.scalar(select(DimDistributor).where(DimDistributor.code == "DIST-HL-01")):
            db.add(DimDistributor(code="DIST-HL-01", name="Dist HL"))
        db.commit()

        src = db.scalar(select(SourceDefinition).where(SourceDefinition.code == "historical_lineup_default"))
        assert src is not None

        # Workbook uses partial match token "ILIKE Customer Corp" which won't exact-match.
        workbook = _build_ilike_customer_workbook_bytes("ILIKE Customer Corp ZZZ")
        job = ImportJob(
            source_id=src.id,
            template_slug="historical_lineup",
            import_mode="validate",
            status="pending",
            stage="uploaded",
            file_name="ilike_test.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        db.add(job)
        db.flush()
        storage = get_storage_backend()
        key = f"imports/test/{job.id}/ilike_test.xlsx"
        storage.save(key, workbook, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(workbook), checksum=None))
        db.commit()

        processed = process_import_job_sync(db, job.id)
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        messages = " ".join(r.message for r in rows)
        codes = {r.code for r in rows}
        # ILIKE should resolve the customer; no unknown_customer for that row.
        assert "unknown_customer" not in codes or "customer_matched_by_ilike" in messages, (
            f"Expected customer_matched_by_ilike in messages. codes={codes}"
        )


def test_customer_ilike_ambiguous_emits_diagnostic() -> None:
    """When ILIKE returns multiple matches, ambiguous_customer_match is emitted (no silent pick)."""
    with SessionLocal() as db:
        _seed_import_core(db)
        ch = db.scalar(select(DimChannel).where(DimChannel.code == "RET"))
        if not ch:
            ch = DimChannel(code="RET", name="Retail")
            db.add(ch)
            db.flush()
        common_token = "TechGroup"
        # Seed two customers whose names both contain the common token.
        for idx in range(1, 3):
            code = f"TECHGRP-{idx}"
            name = f"{common_token} Branch {idx}"
            if not db.scalar(select(DimCustomer).where(DimCustomer.code == code)):
                db.add(DimCustomer(code=code, name=name, channel_id=ch.id))
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-HL-01")):
            db.add(DimProduct(sku="SKU-HL-01", name="Hist Product", category="Audio"))
        if not db.scalar(select(DimDistributor).where(DimDistributor.code == "DIST-HL-01")):
            db.add(DimDistributor(code="DIST-HL-01", name="Dist HL"))
        db.commit()

        src = db.scalar(select(SourceDefinition).where(SourceDefinition.code == "historical_lineup_default"))
        assert src is not None

        workbook = _build_ilike_customer_workbook_bytes(common_token)
        job = ImportJob(
            source_id=src.id,
            template_slug="historical_lineup",
            import_mode="validate",
            status="pending",
            stage="uploaded",
            file_name="ambig_ilike.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        db.add(job)
        db.flush()
        storage = get_storage_backend()
        key = f"imports/test/{job.id}/ambig_ilike.xlsx"
        storage.save(key, workbook, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(workbook), checksum=None))
        db.commit()

        processed = process_import_job_sync(db, job.id)
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        messages = " ".join(r.message for r in rows)
        assert "ambiguous_customer_match" in messages, (
            f"Expected ambiguous_customer_match. messages={messages}"
        )
        assert "customer_matched_by_ilike" not in messages, (
            "Should NOT resolve ambiguous ILIKE match silently"
        )


def test_historical_lineup_apply_writes_headers_lines_and_lineage() -> None:
    source_id = _ensure_historical_seed()
    workbook = _build_nb_style_workbook_bytes()
    storage = get_storage_backend()
    with SessionLocal() as db:
        job = ImportJob(
            source_id=source_id,
            template_slug="historical_lineup",
            import_mode="apply",
            status="pending",
            stage="uploaded",
            file_name="historical_lineup.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        db.add(job)
        db.flush()
        key = f"imports/test/{job.id}/historical_lineup.xlsx"
        storage.save(key, workbook, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(workbook), checksum=None))
        db.commit()

        processed = process_import_job_sync(db, job.id)
        assert processed.stage == "validated"
        assert processed.status == "completed_with_errors"

        headers = db.scalars(
            select(HistoricalLineupImportHeader).where(HistoricalLineupImportHeader.import_job_id == processed.id)
        ).all()
        assert headers
        assert headers[0].source_id is not None
        lines = db.scalars(
            select(HistoricalLineupImportLine).where(HistoricalLineupImportLine.header_id == headers[0].id)
        ).all()
        assert lines
        assert any(line.quantity_units is not None for line in lines)
        assert any(line.diagnostic_codes for line in lines)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3B — alias precedence tests
# ─────────────────────────────────────────────────────────────────────────────


def test_base_unit_maps_to_base_unit_raw_not_sku_raw() -> None:
    """'Base Unit' is a product descriptor, not a product identity key.
    It must map to base_unit_raw, never to sku_raw.
    """
    mapping, _ = _build_header_map(["Base Unit"])
    assert "base_unit_raw" in mapping, (
        f"'Base Unit' should map to base_unit_raw; got mapping={mapping}"
    )
    assert "sku_raw" not in mapping, (
        f"'Base Unit' must NOT map to sku_raw; got mapping={mapping}"
    )


def test_base_unit_not_dual_mapped_with_realistic_columns() -> None:
    """Regression: realistic ASUS-style workbook headers must not assign 'Base Unit'
    to both sku_raw AND base_unit_raw simultaneously.

    Acceptance criteria (from failed manual test after commit 3d21972):
    - base_unit_raw  == 'Base Unit'
    - part_number_raw == 'Part Number'
    - model_raw       == 'Model name'
    - sku_raw is absent (no true SKU column present in this workbook subset)
    - No source column is shared across two canonical fields.
    """
    columns = ["Customer", "Base Unit", "Part Number", "Model name", "Qty"]
    mapping, _ = _build_header_map(columns)

    assert mapping.get("base_unit_raw") == "Base Unit", (
        f"base_unit_raw must be 'Base Unit'; got {mapping.get('base_unit_raw')!r}"
    )
    assert mapping.get("part_number_raw") == "Part Number", (
        f"part_number_raw must be 'Part Number'; got {mapping.get('part_number_raw')!r}"
    )
    assert mapping.get("model_raw") == "Model name", (
        f"model_raw must be 'Model name'; got {mapping.get('model_raw')!r}"
    )
    assert mapping.get("customer_token") == "Customer", (
        f"customer_token must be 'Customer'; got {mapping.get('customer_token')!r}"
    )
    # sku_raw must NOT claim 'Base Unit' — this was the acceptance failure.
    assert mapping.get("sku_raw") != "Base Unit", (
        "sku_raw must NOT be 'Base Unit' — regression from alias precedence bug"
    )
    # With no explicit SKU column in the input, sku_raw should be absent entirely.
    assert "sku_raw" not in mapping, (
        f"sku_raw should be absent when no SKU-named column exists; got mapping={mapping}"
    )
    # Defense: no source column appears as the value for more than one canonical.
    source_values = list(mapping.values())
    assert len(source_values) == len(set(source_values)), (
        f"Duplicate source column assigned to multiple canonicals: {mapping}"
    )


def _build_asus_style_workbook_bytes() -> bytes:
    """Build an in-memory XLSX mimicking the real ASUS NB sheet layout.

    Row 0 — title row (no recognised header tokens)
    Row 1 — empty
    Row 2 — numeric totals row (no recognised header tokens)
    Row 3 — ACTUAL HEADER (header detection must select this row)
    Row 4+ — data rows

    This mirrors the real workbook probe output:
      row 0: ['2026 Q2 NEW PLAN', 'Total', 'TTL Revenue']
      row 3: ['Product Line', 'Country', 'Customer', ... 'Part Number', 'Base Unit', 'Qty', ...]
    """
    header_cols = [
        "Product Line", "Country", "Customer", "Segment",
        "Model name", "Part Number", "Base Unit",
        "Qty", "DAP", "Disti Cost", "Disti margin", "Rebate",
        "Dealer margin", "VAT", "Promo Price", "Customer Feedback",
    ]
    n = len(header_cols)
    title_row   = ["2026 Q2 NEW PLAN", "Total", "TTL Revenue"] + [None] * (n - 3)
    empty_row   = [None] * n
    numbers_row = ["22427", "9857", "9945", "2625"] + [None] * (n - 4)
    data_row    = [
        "NB", "ZA", "Amazon", "Vivobook Go",
        "Vivobook 15", "90NB1542-M007D0", "NB",
        "216", "375.89", "6277.30", "0.0724", "0.06",
        "0.08", "0.15", "7999", "upfront",
    ]
    frame = pd.DataFrame([title_row, empty_row, numbers_row, header_cols, data_row])
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="NB", index=False, header=False)
    return bio.getvalue()


def test_parse_historical_workbook_asus_style_base_unit_not_in_sku_raw() -> None:
    """Full parse-path regression through parse_historical_workbook.

    Tests the COMPLETE path (header detection → _build_header_map → mapping storage)
    NOT just _build_header_map in isolation.

    The workbook mimics the real ASUS NB sheet: title rows above the header, with
    columns including 'Base Unit' and 'Part Number' but NO explicit SKU column.

    Required acceptance criteria:
    - Sheet NB is selected (header detected at the correct row)
    - base_unit_raw  = 'Base Unit'
    - part_number_raw = 'Part Number'
    - model_raw       = 'Model name'
    - customer_token  = 'Customer'
    - sku_raw is ABSENT from the mapping (no SKU-named column present)
    - No source column appears under two different canonical fields
    """
    sheets, schema = parse_historical_workbook(
        "asus_nb_lineup.xlsx", _build_asus_style_workbook_bytes()
    )

    assert len(sheets) == 1, f"Expected 1 selected sheet; got {[s.sheet_name for s in sheets]}"
    sheet = sheets[0]
    assert sheet.sheet_name == "NB"

    m = sheet.mapping
    assert m.get("base_unit_raw") == "Base Unit", (
        f"base_unit_raw must be 'Base Unit'; got {m.get('base_unit_raw')!r} — mapping={m}"
    )
    assert m.get("part_number_raw") == "Part Number", (
        f"part_number_raw must be 'Part Number'; got {m.get('part_number_raw')!r}"
    )
    assert m.get("model_raw") == "Model name", (
        f"model_raw must be 'Model name'; got {m.get('model_raw')!r}"
    )
    assert m.get("customer_token") == "Customer", (
        f"customer_token must be 'Customer'; got {m.get('customer_token')!r}"
    )
    # Critical regression: sku_raw must NOT claim 'Base Unit'.
    assert m.get("sku_raw") != "Base Unit", (
        "sku_raw must NOT be 'Base Unit' — alias precedence regression detected in full parse path"
    )
    # With no explicit SKU column, sku_raw must be absent entirely.
    assert "sku_raw" not in m, (
        f"sku_raw should be absent when no SKU-named column exists; got mapping keys={list(m.keys())}"
    )
    # Invariant: no source column assigned to more than one canonical.
    source_values = list(m.values())
    assert len(source_values) == len(set(source_values)), (
        f"Duplicate source column in full-parse-path mapping: {m}"
    )

    # Verify the schema records the correct sheet as selected.
    assert schema["selected_sheets"] == ["NB"]
    detail = schema["selected_sheet_details"][0]
    assert "Base Unit" in detail["source_columns"]
    assert "Part Number" in detail["source_columns"]
    assert "sku_raw" not in detail["mapped_fields"], (
        f"sku_raw must not appear in mapped_fields: {detail['mapped_fields']}"
    )
    assert "base_unit_raw" in detail["mapped_fields"]


# ─────────────────────────────────────────────────────────────────────────────
# Lineup Commercial Semantics — MSRP, promo, monthly phasing
# ─────────────────────────────────────────────────────────────────────────────


def test_q2_msrp_and_promo_price_map_to_separate_canonical_fields() -> None:
    """Q2 MSRP → msrp_local (pattern fallback);  Promo Price → promo_price_local (alias).

    Root-cause fix: "Q2 MSRP" normalises to "q2msrp" which doesn't match the alias "msrp"
    exactly but does end with the root "msrp" and contains no promo disqualifier.
    """
    columns = [
        "Customer", "Model name", "Part Number", "Base Unit",
        "Qty", "Q2 MSRP", "Promo Price",
    ]
    mapping, _ = _build_header_map(columns)

    assert mapping.get("msrp_local") == "Q2 MSRP", (
        f"Q2 MSRP must map to msrp_local via pattern fallback; got {mapping.get('msrp_local')!r}"
    )
    assert mapping.get("promo_price_local") == "Promo Price", (
        f"Promo Price must map to promo_price_local; got {mapping.get('promo_price_local')!r}"
    )
    # The two fields must not share a source column.
    assert mapping["msrp_local"] != mapping["promo_price_local"], (
        "msrp_local and promo_price_local must map to different source columns"
    )


def test_standard_msrp_list_price_aliases_map_to_msrp_local() -> None:
    """SRP, RRP, List Price, Retail Price, New MSRP all map to msrp_local."""
    cases = [
        ("SRP", "SRP"),
        ("RRP", "RRP"),
        ("List Price", "List Price"),
        ("Retail Price", "Retail Price"),
        ("New MSRP", "New MSRP"),
    ]
    for col_name, expected_source in cases:
        mapping, _ = _build_header_map([col_name])
        assert mapping.get("msrp_local") == expected_source, (
            f"'{col_name}' should map to msrp_local; got {mapping!r}"
        )


def test_promo_aliases_map_to_promo_price_local() -> None:
    """Promo SRP, Deal Price, Special Price, Suggested Promo Price all map to promo_price_local."""
    cases = [
        "Promo SRP",
        "Deal Price",
        "Special Price",
        "Suggested Promo Price",
    ]
    for col_name in cases:
        mapping, _ = _build_header_map([col_name])
        assert mapping.get("promo_price_local") == col_name, (
            f"'{col_name}' should map to promo_price_local; got {mapping!r}"
        )


def test_promo_columns_win_over_msrp_pattern_fallback() -> None:
    """'Promo SRP' must map to promo_price_local, NOT msrp_local.

    'Promo SRP' normalises to 'promosrp' which ends with 'srp' (an MSRP pattern root).
    The disqualifier check ('promo' in 'promosrp') must prevent it from landing in msrp_local.
    The alias match for promo_price_local ('promo_srp') must claim it first.
    """
    columns = ["Q2 MSRP", "Promo SRP", "Customer", "Qty"]
    mapping, _ = _build_header_map(columns)

    assert mapping.get("promo_price_local") == "Promo SRP", (
        f"Promo SRP must map to promo_price_local; got {mapping!r}"
    )
    assert mapping.get("msrp_local") == "Q2 MSRP", (
        f"Q2 MSRP must map to msrp_local; got {mapping!r}"
    )
    # Invariant: no source column shared between canonicals.
    source_values = list(mapping.values())
    assert len(source_values) == len(set(source_values)), (
        f"Duplicate source column in mapping: {mapping}"
    )


def test_month_split_columns_captured_in_payload_and_persisted() -> None:
    """Apr / May / Jun month columns are detected and stored in month_split_json.

    Month columns must not collide with the canonical mapping (e.g. they must
    not be claimed by period_label or quantity_units).
    """
    def _build_month_split_workbook() -> bytes:
        rows = pd.DataFrame([
            {
                "Customer": "CUST-HL-01",
                "Model name": "M-NB-1",
                "Part Number": "SKU-HL-01",
                "Base Unit": "NB",
                "Qty": "12",
                "Q2 MSRP": "999",
                "Promo Price": "899",
                "Apr": "4",
                "May": "4",
                "Jun": "4",
            }
        ])
        bio = io.BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            rows.to_excel(writer, sheet_name="Historical Lineup Apr", index=False)
        return bio.getvalue()

    sheets, _ = parse_historical_workbook("month_split.xlsx", _build_month_split_workbook())
    assert sheets, "Expected one selected sheet"
    rows_accepted = [r for r in sheets[0].rows if r.status != "dropped"]
    assert rows_accepted, "Expected at least one accepted row"

    row_payload = rows_accepted[0].payload
    assert "_month_split" in row_payload, (
        f"_month_split must be present when month columns exist; payload keys: {list(row_payload.keys())}"
    )
    ms = row_payload["_month_split"]
    assert isinstance(ms, dict), f"_month_split must be a dict; got {type(ms)}"
    assert "Apr" in ms, f"Apr must be in month_split; got {ms}"
    assert "May" in ms, f"May must be in month_split; got {ms}"
    assert "Jun" in ms, f"Jun must be in month_split; got {ms}"
    # The values should be string representations of the numeric data.
    assert ms["Apr"] == "4", f"Apr value must be '4'; got {ms['Apr']!r}"

    # Also verify that Q2 MSRP maps correctly in this workbook (combined scenario).
    m = sheets[0].mapping
    assert m.get("msrp_local") == "Q2 MSRP", (
        f"Q2 MSRP must map to msrp_local in the same workbook; got {m.get('msrp_local')!r}"
    )
    assert m.get("promo_price_local") == "Promo Price", (
        f"Promo Price must map to promo_price_local; got {m.get('promo_price_local')!r}"
    )


def test_buyer_and_sold_to_aliases_map_to_customer_token() -> None:
    """'Buyer' and 'Sold To' are common customer column names in vendor workbooks."""
    for col_name in ("Buyer", "Sold To", "Reseller"):
        mapping, _ = _build_header_map([col_name])
        assert "customer_token" in mapping, (
            f"'{col_name}' should map to customer_token; got mapping={mapping}"
        )


def test_sales_part_number_alias_maps_to_part_number_raw() -> None:
    """'Sales Part Number' is a common alias in vendor workbooks for the part number field."""
    for col_name in ("Sales Part Number", "sales_part_number"):
        mapping, _ = _build_header_map([col_name])
        assert "part_number_raw" in mapping, (
            f"'{col_name}' should map to part_number_raw; got mapping={mapping}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Sub-pass A — GET /imports/jobs/{job_id}/lineup-lines endpoint
# ─────────────────────────────────────────────────────────────────────────────


def _run_apply_job(source_id: int, workbook_bytes: bytes, filename: str = "apply.xlsx") -> int:
    """Creates and runs a historical_lineup apply job; returns the job id."""
    storage = get_storage_backend()
    with SessionLocal() as db:
        job = ImportJob(
            source_id=source_id,
            template_slug="historical_lineup",
            import_mode="apply",
            status="pending",
            stage="uploaded",
            file_name=filename,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        db.add(job)
        db.flush()
        key = f"imports/test/{job.id}/{filename}"
        storage.save(key, workbook_bytes, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(workbook_bytes), checksum=None))
        db.commit()
        process_import_job_sync(db, job.id)
        return job.id


def _run_validate_job_for_endpoint(source_id: int, workbook_bytes: bytes) -> int:
    """Creates and runs a validate job; returns the job id (no header/lines written)."""
    storage = get_storage_backend()
    with SessionLocal() as db:
        job = ImportJob(
            source_id=source_id,
            template_slug="historical_lineup",
            import_mode="validate",
            status="pending",
            stage="uploaded",
            file_name="validate.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        db.add(job)
        db.flush()
        key = f"imports/test/{job.id}/validate.xlsx"
        storage.save(key, workbook_bytes, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(workbook_bytes), checksum=None))
        db.commit()
        process_import_job_sync(db, job.id)
        return job.id


def test_lineup_lines_endpoint() -> None:
    """GET /imports/jobs/{job_id}/lineup-lines: apply job, validate job, product_id resolution.

    All three assertions run under a single TestClient to avoid asyncpg event-loop
    teardown races that occur when multiple TestClient instances are created sequentially
    within one pytest session.
    """
    source_id = _ensure_historical_seed()
    apply_job_id = _run_apply_job(source_id, _build_nb_style_workbook_bytes(), "lineup_api_apply.xlsx")
    validate_job_id = _run_validate_job_for_endpoint(source_id, _build_nb_style_workbook_bytes())
    pid_job_id = _run_apply_job(source_id, _build_nb_style_workbook_bytes(), "lineup_api_pid.xlsx")

    with TestClient(app) as client:
        # ── 1. Apply job returns non-empty list with required fields ──────────
        r = client.get(f"/api/v1/imports/jobs/{apply_job_id}/lineup-lines")
        assert r.status_code == 200, f"Expected 200 for apply job; got {r.status_code}: {r.text}"
        lines = r.json()
        assert isinstance(lines, list), "Response must be a list"
        assert len(lines) > 0, "Apply job must produce at least one lineup line"

        line = lines[0]
        assert "id" in line
        assert "source_row_number" in line
        assert "product_id" in line  # may be null for unresolved rows
        assert "part_number_raw" in line
        assert "model_raw" in line
        assert "quantity_units" in line
        assert "msrp_local" in line
        assert "sheet_name" in line
        assert "period_label" in line

        # Numeric fields must be float or null — never a Decimal string like "12.0000"
        qty = line["quantity_units"]
        if qty is not None:
            assert isinstance(qty, (int, float)), f"quantity_units must be numeric; got {type(qty)}: {qty!r}"

        # ── 1b. Resolution status fields (Sub-pass B audit surface) ───────────
        # diagnostic_codes must be a list (possibly empty for clean rows).
        assert "diagnostic_codes" in line, "diagnostic_codes must be present on each line"
        assert isinstance(line["diagnostic_codes"], list), (
            f"diagnostic_codes must be a list; got {type(line['diagnostic_codes'])}"
        )
        # customer_token key must always be present (value may be null for header-level customer).
        assert "customer_token" in line, "customer_token must be present on each line"

        # The NB-style workbook has 'UNKNOWN-CUST' which should produce an unknown_customer diagnostic
        # and retain the raw token string so the operator can see which token was unresolvable.
        unknown_lines = [ln for ln in lines if "unknown_customer" in ln["diagnostic_codes"]]
        if unknown_lines:
            ul = unknown_lines[0]
            assert ul["customer_token"] is not None, (
                f"Lines with unknown_customer diagnostic must carry the raw token; got None. line={ul}"
            )

        # ── 2. Validate-only job returns empty list ────────────────────────────
        rv = client.get(f"/api/v1/imports/jobs/{validate_job_id}/lineup-lines")
        assert rv.status_code == 200, f"Expected 200 for validate job; got {rv.status_code}: {rv.text}"
        assert rv.json() == [], f"Validate job must return []; got {rv.json()}"

        # ── 3. At least one line has a resolved product_id ────────────────────
        rp = client.get(f"/api/v1/imports/jobs/{pid_job_id}/lineup-lines")
        assert rp.status_code == 200
        pid_lines = rp.json()
        product_ids = [ln["product_id"] for ln in pid_lines]
        assert any(pid is not None for pid in product_ids), (
            f"Expected at least one line with resolved product_id; got product_ids={product_ids}"
        )
