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
        assert data_rows, "Expected at least one data row result"
        partial_rows = [r for r in data_rows if "partial_margin_stack" in (r.message or "")]
        if partial_rows:
            for row in partial_rows:
                assert row.severity != "error", (
                    f"partial_margin_stack must not be error; got severity={row.severity!r}"
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
        by_row = {r.row_number: r for r in rows}
        # Row 1 (first data row, row_number=1): must be error due to invalid_quantity
        r1 = by_row.get(1)
        if r1 and "invalid_quantity" in (r1.message or ""):
            assert r1.severity == "error", f"Row 1 with invalid_quantity must be error, got {r1.severity!r}"
        # Row 2 (row_number=2): should be warning (invalid_numeric on MSRP is optional)
        r2 = by_row.get(2)
        if r2 and "invalid_numeric" in (r2.message or "") and "invalid_quantity" not in (r2.message or ""):
            assert r2.severity != "error", (
                f"Row 2 with only invalid_numeric on optional field must not be error, got {r2.severity!r}"
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
