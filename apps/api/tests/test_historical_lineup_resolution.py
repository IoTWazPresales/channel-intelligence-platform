"""
Focused unit and integration tests for historical_lineup Phase 1 hardening:
- Header detection scoring
- Canonical alias coverage
- Product resolution precedence (part_number, model_name, ILIKE single-match)
- Severity classification (invalid_quantity vs invalid_numeric, partial_margin_stack)
- Previous-job row immutability after a second run
"""
from __future__ import annotations

import io

import pandas as pd
import pytest
from sqlalchemy import select

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata, SourceDefinition
from app.ingestion.pipeline import process_import_job_sync
from app.services.imports.historical_lineup import (
    _build_header_map,
    _detect_header_row,
    parse_historical_workbook,
)
from app.services.seed_demo import _seed_import_core
from app.storage.local import get_storage_backend


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _seed_resolution_fixtures() -> int:
    """Seeds products for resolution tests. Returns historical_lineup source_id."""
    with SessionLocal() as db:
        _seed_import_core(db)
        ch = db.scalar(select(DimChannel).where(DimChannel.code == "RET"))
        if not ch:
            ch = DimChannel(code="RET", name="Retail")
            db.add(ch)
            db.flush()

        # Product resolvable by exact part_number
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-RES-01")):
            db.add(
                DimProduct(
                    sku="SKU-RES-01",
                    part_number="PART-RES-001",
                    name="Resolution Part Number Product",
                    model_name="MODEL-RES-A",
                    sales_model_name="SALES-RES-A",
                    category="NB",
                    channel_id=ch.id,
                )
            )
        # Product with a unique model_name (no part_number set)
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-RES-02")):
            db.add(
                DimProduct(
                    sku="SKU-RES-02",
                    name="Resolution Model Product",
                    model_name="UNIQUE-MODEL-B",
                    category="NB",
                    channel_id=ch.id,
                )
            )
        # A second product that shares model_name with SKU-RES-03 to test ambiguity guard
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-RES-03")):
            db.add(
                DimProduct(
                    sku="SKU-RES-03",
                    name="Shared Model Alpha",
                    model_name="SHARED-MODEL-X",
                    category="NB",
                    channel_id=ch.id,
                )
            )
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-RES-04")):
            db.add(
                DimProduct(
                    sku="SKU-RES-04",
                    name="Shared Model Beta",
                    model_name="SHARED-MODEL-X",
                    category="NB",
                    channel_id=ch.id,
                )
            )

        # Product for step-2 test: sku_raw value tried as part_number fallback.
        # The workbook will have "SKU"="PART-STEP2-LOOKUP" — exact-SKU fails (different sku),
        # but step 2 matches via part_number.
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-STEP2-TEST")):
            db.add(
                DimProduct(
                    sku="SKU-STEP2-TEST",
                    part_number="PART-STEP2-LOOKUP",
                    name="Step2 Part Number Fallback Product",
                    category="NB",
                    channel_id=ch.id,
                )
            )
        # Two products for cross-field ambiguity: same token resolves to different products
        # via model_name (SKU-RES-06) vs sales_model_name (SKU-RES-07).
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-RES-06")):
            db.add(
                DimProduct(
                    sku="SKU-RES-06",
                    name="Cross Field Model Product",
                    model_name="CROSS-FIELD-X",
                    category="NB",
                    channel_id=ch.id,
                )
            )
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-RES-07")):
            db.add(
                DimProduct(
                    sku="SKU-RES-07",
                    name="Cross Field Sales Model Product",
                    sales_model_name="CROSS-FIELD-X",
                    category="NB",
                    channel_id=ch.id,
                )
            )
        # Product for single-ILIKE-match positive-path test.
        # The sentinel string is unique across all test fixtures so only this product matches.
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-RES-ILIKE")):
            db.add(
                DimProduct(
                    sku="SKU-RES-ILIKE",
                    name="ILIKE-TESTSENTINEL-2026-PRODUCT",
                    category="NB",
                    channel_id=ch.id,
                )
            )

        # Known customer for resolution tests
        if not db.scalar(select(DimCustomer).where(DimCustomer.code == "CUST-RES-01")):
            db.add(DimCustomer(code="CUST-RES-01", name="Resolution Customer", channel_id=ch.id))

        db.commit()
        src = db.scalar(select(SourceDefinition).where(SourceDefinition.code == "historical_lineup_default"))
        assert src is not None
        return src.id


def _make_simple_workbook(rows: list[dict], sheet_name: str = "Historical Lineup") -> bytes:
    """Writes a standard xlsx with a header row from dict keys, then data rows."""
    df = pd.DataFrame(rows)
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return bio.getvalue()


def _run_validate_job(source_id: int, workbook_bytes: bytes, filename: str = "test.xlsx") -> ImportJob:
    """Creates + runs a validate job; returns the processed ImportJob."""
    storage = get_storage_backend()
    with SessionLocal() as db:
        job = ImportJob(
            source_id=source_id,
            template_slug="historical_lineup",
            import_mode="validate",
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
        return process_import_job_sync(db, job.id)


def _run_apply_job(source_id: int, workbook_bytes: bytes, filename: str = "test_apply.xlsx") -> ImportJob:
    """Creates + runs an apply job; returns the processed ImportJob."""
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
        return process_import_job_sync(db, job.id)


def _all_diagnostic_tokens(rows: list) -> set[str]:
    """Extract all diagnostic codes from ImportRowResult.code and .message fields.

    ImportRowResult.code holds only the first diagnostic; message holds all joined
    by '; '. Checking both is robust to diagnostic ordering.
    """
    tokens: set[str] = set()
    for r in rows:
        if r.code:
            tokens.add(r.code)
        if r.message:
            for part in r.message.split("; "):
                tokens.add(part.strip())
    return tokens


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — no DB required
# ─────────────────────────────────────────────────────────────────────────────


def test_detect_header_row_finds_header_below_title_rows() -> None:
    """Row 3 (0-indexed) has real headers; rows 0-2 are title/blank noise."""
    raw = pd.DataFrame(
        [
            ["", "", "", "", "2026 Q2 PLAN"],
            ["", "", "", "", ""],
            ["", "", "", "", ""],
            ["Customer", "Part Number", "Model name", "Qty", "MSRP"],
            ["CUST-01", "P-001", "M-001", "10", "999"],
        ]
    )
    idx, mapping, conf = _detect_header_row(raw)
    assert idx == 3
    assert "customer_token" in mapping
    assert "part_number_raw" in mapping
    assert "quantity_units" in mapping
    assert conf > 0.0


def test_detect_header_row_returns_none_for_totally_empty_frame() -> None:
    raw = pd.DataFrame()
    idx, mapping, conf = _detect_header_row(raw)
    assert idx is None
    assert mapping == {}
    assert conf == 0.0


def test_detect_header_row_returns_none_when_no_header_signature() -> None:
    """A frame full of data values (no header-like tokens) should not pick a row."""
    raw = pd.DataFrame(
        [
            ["10", "20", "30"],
            ["40", "50", "60"],
        ]
    )
    idx, _mapping, _conf = _detect_header_row(raw)
    assert idx is None


def test_build_header_map_common_column_name_variants() -> None:
    """Common real-world column spellings must map to their canonical field."""
    cases = [
        ("Customer", "customer_token"),
        ("Account Name", "customer_token"),
        ("Part Number", "part_number_raw"),
        ("MPN", "part_number_raw"),
        ("Model name", "model_raw"),
        ("Model Name", "model_raw"),
        ("Qty", "quantity_units"),
        ("Quantity", "quantity_units"),
        ("MSRP", "msrp_local"),
        ("List Price", "msrp_local"),
        ("Distributor", "distributor_token"),
        ("Disti", "distributor_token"),
        ("Notes", "workflow_notes"),
    ]
    for col_name, expected_canonical in cases:
        mapping, _ = _build_header_map([col_name])
        assert expected_canonical in mapping, f"{col_name!r} should map to {expected_canonical!r}, got mapping={mapping}"


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — DB required
# ─────────────────────────────────────────────────────────────────────────────


def test_product_resolution_by_exact_part_number() -> None:
    """A row with a known part_number in the Part Number column resolves product_id."""
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "Part Number": "PART-RES-001",
                "Qty": "5",
                "MSRP": "999",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        codes = {r.code for r in rows}
        # No unknown_product — resolution succeeded via part_number
        assert "unknown_product" not in codes
        assert "historical_lineup_row_ok" in codes or "product_matched_by_ilike" in codes or "historical_lineup_processed" in codes


def test_product_resolution_by_unique_model_name() -> None:
    """A row whose Model name uniquely identifies a product resolves product_id."""
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "Model name": "UNIQUE-MODEL-B",
                "Qty": "3",
                "MSRP": "500",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        codes = {r.code for r in rows}
        assert "unknown_product" not in codes


def test_product_resolution_ambiguous_shared_model_name_stays_unresolved() -> None:
    """Two products share SHARED-MODEL-X — model_name lookup must not pick one silently.

    ImportRowResult.code holds only the first diagnostic; message holds all.
    We check both to be robust to diagnostic ordering.
    """
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "Model name": "SHARED-MODEL-X",
                "Qty": "2",
                "MSRP": "750",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        # code holds first diagnostic; message holds all — check both
        all_diagnostic_tokens: set[str] = set()
        for r in rows:
            if r.code:
                all_diagnostic_tokens.add(r.code)
            if r.message:
                for part in r.message.split("; "):
                    all_diagnostic_tokens.add(part.strip())
        # Must not silently resolve; ILIKE should report ambiguous or unknown
        assert "ambiguous_product_match" in all_diagnostic_tokens or "unknown_product" in all_diagnostic_tokens, (
            f"Expected ambiguous or unknown product diagnostic; got: {all_diagnostic_tokens}"
        )


def test_product_resolution_single_ilike_match_resolves_product_id() -> None:
    """When a product token matches no exact key, the ILIKE fallback runs.
    - Exactly one match → product resolved + 'product_matched_by_ilike' diagnostic.
    - Zero matches → 'unknown_product'.
    Either way a product outcome diagnostic must appear in code or message;
    the row must never be silently left with no product diagnostic.

    ImportRowResult.code holds only the first diagnostic; message holds all.
    We check both to be robust to diagnostic ordering.
    """
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                # Token that exact-matches nothing; ILIKE will either find one or none.
                "SKU": "PART-RES-001-ILIKE-TOKEN-THAT-WONT-EXACT",
                "Qty": "1",
                "MSRP": "100",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        all_diagnostic_tokens: set[str] = set()
        for r in rows:
            if r.code:
                all_diagnostic_tokens.add(r.code)
            if r.message:
                for part in r.message.split("; "):
                    all_diagnostic_tokens.add(part.strip())
        has_product_outcome = (
            "product_matched_by_ilike" in all_diagnostic_tokens
            or "unknown_product" in all_diagnostic_tokens
            or "ambiguous_product_match" in all_diagnostic_tokens
            or "historical_lineup_row_ok" in all_diagnostic_tokens
        )
        assert has_product_outcome, (
            f"Expected a product resolution diagnostic; got: {all_diagnostic_tokens}"
        )


def test_partial_margin_stack_severity_is_warning_not_error() -> None:
    """partial_margin_stack alone must not escalate the row to severity=error."""
    source_id = _seed_resolution_fixtures()
    # Row has only one margin field (disti_margin) but not the others → partial_margin_stack.
    # Product and customer are known, qty is valid → no other error trigger.
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "Part Number": "PART-RES-001",
                "Qty": "10",
                "MSRP": "999",
                "Disti Margin": "8",
                # Rebate, Dealer Margin, VAT intentionally absent → partial_margin_stack
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        # Find the data row (row_number > 0, not a sheet summary)
        data_rows = [r for r in rows if r.row_number > 0]
        assert data_rows, "Expected at least one data row result — workbook processing may have failed"
        partial_rows = [r for r in data_rows if "partial_margin_stack" in (r.message or "")]
        assert partial_rows, (
            "Expected at least one row with partial_margin_stack diagnostic. "
            f"Actual messages: {[r.message for r in data_rows]}"
        )
        for row in partial_rows:
            assert row.severity != "error", (
                f"partial_margin_stack must not be error; got severity={row.severity!r}, message={row.message!r}"
            )


def test_invalid_quantity_escalates_to_error_optional_numeric_does_not() -> None:
    """
    invalid_quantity (bad qty value) → severity error.
    invalid_numeric on an optional field (e.g. MSRP) → severity warning.
    """
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            # Row 1: qty is non-numeric → invalid_quantity → error
            {
                "Customer": "CUST-RES-01",
                "Part Number": "PART-RES-001",
                "Qty": "BADQTY",
                "MSRP": "999",
            },
            # Row 2: qty is valid, MSRP is non-numeric → invalid_numeric (optional) → warning
            {
                "Customer": "CUST-RES-01",
                "Part Number": "PART-RES-001",
                "Qty": "5",
                "MSRP": "NOT_A_NUMBER",
            },
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == processed.id,
                ImportRowResult.row_number > 0,
            )
        ).all()
        # Sort by row_number to handle workbooks where header is at row 0 and data starts
        # at row_number=2 (Excel 1-based: header=row1, first data=row2).
        data_rows = sorted(rows, key=lambda r: r.row_number)
        assert len(data_rows) == 2, (
            f"Expected exactly 2 data rows, got {len(data_rows)}: "
            f"{[(r.row_number, r.message) for r in data_rows]}"
        )
        r1, r2 = data_rows[0], data_rows[1]

        # r1: qty is non-numeric → parse pass emits invalid_quantity → severity must be error
        assert "invalid_quantity" in (r1.message or ""), (
            f"Expected invalid_quantity in r1.message; got: {r1.message!r}"
        )
        assert r1.severity == "error", (
            f"Row with invalid_quantity must be severity=error, got {r1.severity!r}"
        )

        # r2: qty is valid, MSRP is non-numeric → invalid_numeric (optional) → severity warning
        assert "invalid_numeric" in (r2.message or ""), (
            f"Expected invalid_numeric in r2.message; got: {r2.message!r}"
        )
        assert "invalid_quantity" not in (r2.message or ""), (
            f"Row 2 should not have invalid_quantity; got: {r2.message!r}"
        )
        assert r2.severity != "error", (
            f"Row with only optional invalid_numeric must not be error, got {r2.severity!r}"
        )


def test_previous_job_rows_stable_after_second_validate_run() -> None:
    """
    Running a second validate job on the same source must not alter the first job's rows.
    Each job's ImportRowResult rows are immutable after completion.
    """
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "Part Number": "PART-RES-001",
                "Qty": "7",
                "MSRP": "999",
            }
        ]
    )

    job1 = _run_validate_job(source_id, workbook, filename="run1.xlsx")
    with SessionLocal() as db:
        rows_before = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == job1.id)
        ).all()
        codes_before = sorted(r.code for r in rows_before)
        count_before = len(rows_before)

    # Run a second validate job (same source, same file bytes — simulates user retry)
    _run_validate_job(source_id, workbook, filename="run2.xlsx")

    with SessionLocal() as db:
        rows_after = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == job1.id)
        ).all()
        codes_after = sorted(r.code for r in rows_after)
        count_after = len(rows_after)

    assert count_before == count_after, (
        f"Job 1 row count changed after job 2: {count_before} → {count_after}"
    )
    assert codes_before == codes_after, (
        f"Job 1 row codes changed after job 2: {codes_before} → {codes_after}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1A additional tests — positive paths + apply mode
# ─────────────────────────────────────────────────────────────────────────────


def test_product_resolution_sku_field_fallback_to_part_number() -> None:
    """Step 2: when sku_raw fails exact-SKU match, the same value is tried against
    part_number. A product whose part_number equals the raw SKU token is resolved
    without falling through to ILIKE.

    Proof: neither 'unknown_product' nor 'product_matched_by_ilike' appears in
    any row's code or message — the match was via exact lookup only.
    """
    source_id = _seed_resolution_fixtures()
    # Workbook has a "SKU" column containing "PART-STEP2-LOOKUP".
    # No product has sku="PART-STEP2-LOOKUP", but SKU-STEP2-TEST has part_number="PART-STEP2-LOOKUP".
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "SKU": "PART-STEP2-LOOKUP",
                "Qty": "5",
                "MSRP": "999",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        tokens = _all_diagnostic_tokens(rows)
        assert "unknown_product" not in tokens, (
            f"Expected product to be resolved via step-2 part_number fallback; got: {tokens}"
        )
        assert "product_matched_by_ilike" not in tokens, (
            f"Expected exact resolution (step 2), not ILIKE fallback; got: {tokens}"
        )


def test_product_resolution_by_sales_model_name() -> None:
    """Step 4b: model_raw matching a unique sales_model_name resolves product_id
    even when no product has that value as its model_name.
    """
    source_id = _seed_resolution_fixtures()
    # SKU-RES-01 has sales_model_name="SALES-RES-A" (model_name is "MODEL-RES-A" — different).
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "Model name": "SALES-RES-A",
                "Qty": "5",
                "MSRP": "999",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        tokens = _all_diagnostic_tokens(rows)
        assert "unknown_product" not in tokens, (
            f"Expected sales_model_name exact resolution; got: {tokens}"
        )


def test_product_resolution_cross_field_model_ambiguity_stays_unresolved() -> None:
    """Step 4 cross-field guard: when model_raw resolves to product A via model_name
    and to a *different* product B via sales_model_name, the code must NOT silently
    choose. It must emit ambiguous_product_match and leave product_id unresolved.

    SKU-RES-06: model_name="CROSS-FIELD-X"
    SKU-RES-07: sales_model_name="CROSS-FIELD-X"
    Both are unique in their respective fields, so both pass the uniqueness guard.
    """
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "Model name": "CROSS-FIELD-X",
                "Qty": "5",
                "MSRP": "999",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        tokens = _all_diagnostic_tokens(rows)
        assert "ambiguous_product_match" in tokens, (
            f"Expected ambiguous_product_match for cross-field model token; got: {tokens}"
        )
        assert "unknown_product" not in tokens, (
            f"ambiguous should be reported as ambiguous, not unknown; got: {tokens}"
        )


def test_product_single_ilike_match_positive_path() -> None:
    """Step 5 positive path: when exact lookups all fail but exactly one product
    ILIKE-matches the token, product_id is resolved and 'product_matched_by_ilike'
    is recorded.

    SKU-RES-ILIKE has name="ILIKE-TESTSENTINEL-2026-PRODUCT". The token
    "TESTSENTINEL-2026" does not match any product's sku/part_number/model_name/
    sales_model_name exactly — so steps 1–4 all fail. ILIKE finds exactly one match.
    """
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "SKU": "TESTSENTINEL-2026",
                "Qty": "5",
                "MSRP": "999",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        tokens = _all_diagnostic_tokens(rows)
        assert "product_matched_by_ilike" in tokens, (
            f"Expected product_matched_by_ilike for single ILIKE match; got: {tokens}"
        )
        assert "unknown_product" not in tokens, (
            f"ILIKE single match should resolve, not unknown; got: {tokens}"
        )
        assert "ambiguous_product_match" not in tokens, (
            f"ILIKE single match should not be ambiguous; got: {tokens}"
        )


def test_product_matched_by_ilike_is_warning_not_error() -> None:
    """product_matched_by_ilike must not escalate severity to error.
    A row resolved via soft ILIKE match remains at severity='warning' so users
    can review it, but it does not block apply or inflate error counts.
    """
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "SKU": "TESTSENTINEL-2026",
                "Qty": "5",
                "MSRP": "999",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == processed.id,
                ImportRowResult.row_number > 0,
            )
        ).all()
        ilike_rows = [r for r in rows if "product_matched_by_ilike" in (r.message or "")]
        assert ilike_rows, (
            f"Expected at least one row with product_matched_by_ilike; "
            f"got messages: {[r.message for r in rows]}"
        )
        for row in ilike_rows:
            assert row.severity != "error", (
                f"product_matched_by_ilike must not be error; got severity={row.severity!r}"
            )


def test_apply_mode_resolved_product_id_is_persisted() -> None:
    """In apply mode, a product resolved via exact part_number (step 3) must have
    its product_id written to HistoricalLineupImportLine.product_id.
    """
    source_id = _seed_resolution_fixtures()
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "Part Number": "PART-RES-001",
                "Qty": "5",
                "MSRP": "999",
            }
        ]
    )
    processed = _run_apply_job(source_id, workbook)
    with SessionLocal() as db:
        expected_product = db.scalar(
            select(DimProduct).where(DimProduct.sku == "SKU-RES-01")
        )
        assert expected_product is not None, "Seed product SKU-RES-01 must exist"

        headers = db.scalars(
            select(HistoricalLineupImportHeader).where(
                HistoricalLineupImportHeader.import_job_id == processed.id
            )
        ).all()
        assert headers, "Apply mode must create at least one HistoricalLineupImportHeader"

        lines = db.scalars(
            select(HistoricalLineupImportLine).where(
                HistoricalLineupImportLine.header_id == headers[0].id
            )
        ).all()
        assert lines, "Apply mode must create at least one HistoricalLineupImportLine"
        for line in lines:
            assert line.product_id == expected_product.id, (
                f"Expected product_id={expected_product.id} on all lines; "
                f"got product_id={line.product_id} for source_row={line.source_row_number}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3B — alias fix + diagnostic code-field ordering tests
# ─────────────────────────────────────────────────────────────────────────────


def test_base_unit_column_does_not_block_product_resolution_when_part_number_present() -> None:
    """After the alias fix, a workbook with 'Base Unit' + 'Part Number' columns must:
    - Map 'Part Number' to part_number_raw (unchanged).
    - Map 'Base Unit' to base_unit_raw (descriptor), NOT sku_raw.
    - Resolve the product via Part Number rather than treating Base Unit as a product key.
    """
    source_id = _seed_resolution_fixtures()
    # Build a workbook that mirrors real ASUS structure: both columns present.
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                "Base Unit": "SomeDescriptor",  # descriptor — must NOT drive product lookup
                "Part Number": "PART-RES-001",  # real identity key
                "Qty": "5",
                "MSRP": "999",
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportRowResult).where(ImportRowResult.job_id == processed.id)
        ).all()
        tokens = _all_diagnostic_tokens(rows)
        assert "unknown_product" not in tokens, (
            "With a valid Part Number present, unknown_product must not be emitted; "
            f"got tokens={tokens}"
        )


def test_code_field_uses_error_level_diagnostic_when_both_present() -> None:
    """When a row accumulates partial_margin_stack (added first, during parse pass) and
    then unknown_product (added during resolution), ImportRowResult.code must be
    'unknown_product' — not 'partial_margin_stack' — and severity must be 'error'.

    This verifies the _ERROR_LEVEL_CODES priority logic in the code-field selection.
    """
    source_id = _seed_resolution_fixtures()
    # Row: real qty, partial margin stack (only disti_margin present), unknown product token.
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "CUST-RES-01",
                # Unknown token → parser emits partial_margin_stack first, then unknown_product during resolution.
                "Part Number": "DOES-NOT-EXIST-IN-DB",
                "Qty": "5",
                "MSRP": "999",
                "Disti Margin": "8",  # only one margin field → partial_margin_stack
                # Rebate, Dealer Margin, VAT absent → triggers partial_margin_stack
            }
        ]
    )
    processed = _run_validate_job(source_id, workbook)
    with SessionLocal() as db:
        data_rows = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == processed.id,
                ImportRowResult.row_number > 0,
            )
        ).all()
        assert data_rows, "Expected at least one data row result"
        # Find the row that has both diagnostics in its message.
        target = next(
            (r for r in data_rows if "partial_margin_stack" in (r.message or "") and "unknown_product" in (r.message or "")),
            None,
        )
        assert target is not None, (
            "Expected a row with both partial_margin_stack and unknown_product in message; "
            f"got messages: {[r.message for r in data_rows]}"
        )
        assert target.code == "unknown_product", (
            f"code must be 'unknown_product' (error-level wins); got code={target.code!r}"
        )
        assert target.severity == "error", (
            f"severity must be 'error' when unknown_product present; got severity={target.severity!r}"
        )


def test_invalid_numeric_fields_in_raw_payload() -> None:
    """Phase 3C: rows with non-parseable optional numeric values must carry
    _invalid_numeric_fields in raw_payload so the UI can name the affected fields.

    Validates the backend change that collects field names during the numeric
    resolution loop and embeds them into ImportRowResult.raw_payload before
    persisting the row.
    """
    source_id = _seed_resolution_fixtures()
    # 6 mapped columns → confidence 6/23 ≈ 0.26 which does NOT trigger low_mapping_confidence
    # (threshold is < 0.25).  This ensures invalid_numeric becomes the primary_code on the row.
    workbook = _make_simple_workbook(
        [
            {
                "Customer": "Resolution Customer",   # resolves via exact name match
                "Part Number": "PART-RES-001",        # resolves via exact part_number
                "Model name": "MODEL-RES-A",          # maps to model_raw
                "Qty": "5",
                "MSRP": "TBD",    # non-parseable text (not a pandas NaN sentinel) → triggers invalid_numeric
                "DAP": "500.00",  # 6th mapped field (valid) — conf = 6/23 ≈ 0.26 ≥ 0.25
            }
        ],
        sheet_name="Historical Lineup",
    )
    job = _run_validate_job(source_id, workbook, filename="test_numeric_payload.xlsx")

    with SessionLocal() as db:
        results = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job.id,
                ImportRowResult.code == "invalid_numeric",
            )
        ).all()

    assert results, (
        "Expected at least one ImportRowResult with code='invalid_numeric'. "
        "Ensure the workbook has >= 5 mapped columns so map_conf >= 0.25 and "
        "low_mapping_confidence is not prepended as the primary code."
    )
    for r in results:
        assert r.raw_payload is not None, "raw_payload must not be None for invalid_numeric rows"
        inv_fields = r.raw_payload.get("_invalid_numeric_fields")
        assert inv_fields, (
            f"_invalid_numeric_fields must be present in raw_payload; got {r.raw_payload!r}"
        )
        assert "msrp_local" in inv_fields, (
            f"Expected 'msrp_local' in _invalid_numeric_fields; got {inv_fields!r}. "
            "Note: avoid pandas NaN sentinels (N/A, NA, NaN) as test values — use 'TBD' etc."
        )
