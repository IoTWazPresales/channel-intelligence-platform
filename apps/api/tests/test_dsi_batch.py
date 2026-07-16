"""DSI unified multi-file batch grouping and job creation."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from app.services.imports.dsi_batch import (
    batch_groups_preview_to_dict,
    normalized_header_signature,
    propose_dsi_batch_groups,
)
from app.services.imports.dsi_workbook import (
    DSI_FILE_SHEET_SEP,
    build_combined_dsi_dataframe,
    build_dsi_workbook_structure,
    make_dsi_file_sheet_key,
    parse_dsi_mapping_key,
)


def test_same_layout_files_share_signature() -> None:
    a = pd.DataFrame({"Dist": ["D1"], "SKU": ["P1"], "Qty": [1], "Date": ["2024-01-01"]})
    b = pd.DataFrame({"Dist": ["D1"], "SKU": ["P2"], "Qty": [2], "Date": ["2024-01-08"]})
    bio_a = io.BytesIO()
    bio_b = io.BytesIO()
    a.to_csv(bio_a, index=False)
    b.to_csv(bio_b, index=False)
    sig_a, _, _, unm_a, _reason_a = normalized_header_signature("a.csv", bio_a.getvalue())
    sig_b, _, _, unm_b, _reason_b = normalized_header_signature("b.csv", bio_b.getvalue())
    assert not unm_a and not unm_b
    assert sig_a == sig_b


def test_divergent_layouts_split_groups() -> None:
    sell = pd.DataFrame({"Dist": ["D1"], "SKU": ["P1"], "Qty": [1], "Date": ["2024-01-01"]})
    soh = pd.DataFrame({"Dist": ["D1"], "SKU": ["P1"], "SOH": [10], "Snap": ["2024-01-31"]})
    bio_s = io.BytesIO()
    bio_h = io.BytesIO()
    sell.to_csv(bio_s, index=False)
    soh.to_csv(bio_h, index=False)
    groups = propose_dsi_batch_groups(
        [
            ("sell.csv", bio_s.getvalue()),
            ("soh.csv", bio_h.getvalue()),
        ]
    )
    assert len(groups) == 2
    preview = batch_groups_preview_to_dict(groups)
    assert len(preview) == 2


def test_file_sheet_mapping_key_roundtrip() -> None:
    key = make_dsi_file_sheet_key("week1.xlsx", "Sellout")
    file_part, sheet_part = parse_dsi_mapping_key(key)
    assert file_part == "week1.xlsx"
    assert sheet_part == "Sellout"
    assert DSI_FILE_SHEET_SEP in key


def test_cross_file_overlap_flags_shared_grain() -> None:
    import pandas as pd
    from unittest.mock import MagicMock

    from app.services.imports.dsi_workbook import flag_dsi_cross_file_raw_overlaps

    df = pd.DataFrame(
        {
            "distributor_token": ["Makro", "Makro"],
            "product_identifier": ["SKU1", "SKU1"],
            "customer_dealer_token": ["C1", "C1"],
            "transaction_date": ["2026-07-01", "2026-07-01"],
            "invoice_no": ["", ""],
            "_dsi_source_file": ["week1.csv", "week2.csv"],
        }
    )
    job = MagicMock()
    job.id = 99
    job.staged_metadata = {}
    db = MagicMock()
    n = flag_dsi_cross_file_raw_overlaps(db, job, df)
    assert n >= 1
    assert job.staged_metadata["dsi_cross_file_overlap"]["overlap_grain_count"] == 1


def test_column_samples_in_workbook_structure() -> None:
    sell = pd.DataFrame({"Dist": ["D1"], "SKU": ["P1"], "Qty": [1], "Date": ["2024-01-01"], "Cust": ["C1"]})
    bio = io.BytesIO()
    sell.to_csv(bio, index=False)
    structure = build_dsi_workbook_structure("a.csv", bio.getvalue())
    assert structure["sheets"]
    assert "column_samples" in structure["sheets"][0]
    assert structure["sheets"][0]["column_samples"]


def _seed_dsi_source_for_batch_e2e() -> int:
    """Minimal DSI catalog seed; skip if DSI tables missing."""
    from sqlalchemy import inspect, select

    from app.db.session_sync import SessionLocal
    from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct, DimRegion
    from app.models.ingestion import SourceDefinition
    from app.services.commercial_planner.reference_bootstrap import (
        ensure_commercial_planner_system_reference_data_sync,
    )
    from app.services.seed_demo import _seed_import_core

    with SessionLocal() as db:
        names = set(inspect(db.connection()).get_table_names())
        if "import_distributor_si_staging_line" not in names:
            pytest.skip("Database missing DSI tables")
        _seed_import_core(db)
        ensure_commercial_planner_system_reference_data_sync(db.connection())
        r1 = db.scalar(select(DimRegion).where(DimRegion.code == "NA-W"))
        if not r1:
            r1 = DimRegion(code="NA-W", name="North America West")
            db.add(r1)
            db.flush()
        ch = db.scalar(select(DimChannel).where(DimChannel.code == "RET"))
        if not ch:
            ch = DimChannel(code="RET", name="Retail")
            db.add(ch)
            db.flush()
        if not db.scalar(select(DimDistributor).where(DimDistributor.code == "DIST-01")):
            db.add(DimDistributor(code="DIST-01", name="Summit Supply Co."))
        if not db.scalar(select(DimCustomer).where(DimCustomer.code == "CUST-1001")):
            db.add(
                DimCustomer(
                    code="CUST-1001",
                    name="Metro Market Group",
                    region_id=r1.id,
                    channel_id=ch.id,
                )
            )
        if not db.scalar(select(DimProduct).where(DimProduct.sku == "SKU-ALPHA-01")):
            db.add(
                DimProduct(
                    sku="SKU-ALPHA-01",
                    name="Alpha Pro 200",
                    category="Audio",
                    channel_id=ch.id,
                )
            )
        db.commit()
        sid = db.scalar(select(SourceDefinition.id).where(SourceDefinition.code == "distributor_inventory"))
        assert sid is not None
        return int(sid)


def test_process_import_job_sync_two_file_batch_validate_stages_both() -> None:
    """U0e: nested multi-file must reach combine path (not missing_distributor_token_mapping)."""
    from copy import deepcopy

    from sqlalchemy import func, select

    from app.db.session_sync import SessionLocal
    from app.ingestion.pipeline import process_import_job_sync
    from app.models.import_distributor_si import ImportDistributorSiStagingLine
    from app.models.ingestion import ImportRowResult
    from app.services.imports.dsi_batch import create_dsi_batch_job_sync
    from app.services.imports.dsi_workbook import is_nested_dsi_field_mapping

    source_id = _seed_dsi_source_for_batch_e2e()
    csv_a = (
        "distributor_code,sku,date,qty,customer_name,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-06-01,2,Mystery Dealer Zed,10\n"
    ).encode("utf-8")
    csv_b = (
        "distributor_code,sku,date,qty,customer_name,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-06-08,1,Mystery Dealer Zed,8\n"
    ).encode("utf-8")

    with SessionLocal() as db:
        job = create_dsi_batch_job_sync(
            db,
            source_id=source_id,
            filenames_and_bytes=[("week1.csv", csv_a), ("week2.csv", csv_b)],
            import_mode="validate",
            # weekly avoids post-validate Celery enqueue (Redis) — U0e only needs pipeline entry
            dsi_workflow_mode="weekly",
        )
        job_id = job.id
        mapping_before = deepcopy(job.field_mapping)
        assert is_nested_dsi_field_mapping(mapping_before)
        assert (job.staged_metadata or {}).get("dsi_multi_file") is True

        processed = process_import_job_sync(db, job_id)
        assert processed.id == job_id

        missing = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job_id,
                ImportRowResult.code == "missing_distributor_token_mapping",
            )
        ).first()
        assert missing is None, "nested mapping must flatten before required-target gates"

        staged_n = db.scalar(
            select(func.count())
            .select_from(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == job_id)
        )
        assert int(staged_n or 0) == 2

        refreshed = db.get(type(processed), job_id)
        assert refreshed is not None
        assert refreshed.field_mapping == mapping_before
        subtotals = (refreshed.staged_metadata or {}).get("dsi_file_row_subtotals") or {}
        assert sum(int(v) for v in subtotals.values()) == 2


def test_process_import_job_sync_nested_multisheet_mapping_survives() -> None:
    """U0e: single-file multi-sheet nested mapping must survive validate byte-for-byte."""
    from copy import deepcopy

    from sqlalchemy import select

    from app.db.session_sync import SessionLocal
    from app.ingestion.pipeline import process_import_job_sync
    from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata
    from app.services.imports.dsi_mapping_workflow import infer_dsi_job_sync
    from app.services.imports.dsi_workbook import is_nested_dsi_field_mapping
    from app.storage.local import get_storage_backend
    from app.utils.json_safe import to_jsonable

    source_id = _seed_dsi_source_for_batch_e2e()
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "distributor_code": ["DIST-01"],
                "sku": ["SKU-ALPHA-01"],
                "date": ["2024-06-01"],
                "qty": [2],
                "customer_name": ["Mystery Dealer Zed"],
                "soh": [10],
            }
        ).to_excel(writer, sheet_name="Sellout", index=False)
        pd.DataFrame(
            {
                "distributor_code": ["DIST-01"],
                "sku": ["SKU-ALPHA-01"],
                "soh": [10],
                "snap": ["2024-06-30"],
            }
        ).to_excel(writer, sheet_name="SOH", index=False)
    xlsx_bytes = bio.getvalue()

    storage = get_storage_backend()
    with SessionLocal() as db:
        job = ImportJob(
            source_id=source_id,
            template_slug="distributor_inventory",
            import_mode="validate",
            status="pending",
            stage="uploaded",
            file_name="multi.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            staged_metadata=to_jsonable({"dsi_workflow_mode_explicit": "weekly"}),
        )
        db.add(job)
        db.flush()
        key = f"imports/test/{job.id}/multi.xlsx"
        storage.save(key, xlsx_bytes, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(xlsx_bytes), checksum=None))
        db.commit()
        job_id = job.id

        infer_dsi_job_sync(db, job_id)
        job = db.get(ImportJob, job_id)
        assert job is not None
        mapping_before = deepcopy(job.field_mapping)
        assert is_nested_dsi_field_mapping(mapping_before)

        process_import_job_sync(db, job_id)
        missing = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job_id,
                ImportRowResult.code == "missing_distributor_token_mapping",
            )
        ).first()
        assert missing is None
        refreshed = db.get(ImportJob, job_id)
        assert refreshed is not None
        assert refreshed.field_mapping == mapping_before
