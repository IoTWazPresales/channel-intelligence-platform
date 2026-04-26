from __future__ import annotations

import io

import pandas as pd
from sqlalchemy import select

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata, SourceDefinition
from app.ingestion.pipeline import process_import_job_sync
from app.services.imports.historical_lineup import parse_historical_workbook
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
            db.add(DimProduct(sku="SKU-HL-01", name="Hist Product", category="Audio", channel_id=ch.id))
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
