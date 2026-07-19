"""Per-file DSI distributor identity: banner sniff, gate, stamp."""

from __future__ import annotations

import pandas as pd

from app.services.imports.dsi_file_distributor import (
    apply_file_distributor_stamps_to_dataframe,
    distributor_identity_satisfied,
    file_distributors_all_confirmed,
    sniff_banner_company_token_from_grid,
)
from app.services.imports.dsi_mapping_workflow import dsi_mapping_gate_errors
from app.services.imports.dsi_workbook import is_nested_dsi_field_mapping


def test_sniff_banner_company_name_adjacent_cells() -> None:
    grid = pd.DataFrame(
        [
            ["ASUS Weekly Sellout Form", None, None],
            ["Company Name", "MUSTEK-ZA-C", None],
            ["Report Period", "2026-W28", None],
        ]
    )
    assert sniff_banner_company_token_from_grid(grid) == "MUSTEK-ZA-C"


def test_sniff_banner_company_name_colon_cell() -> None:
    grid = pd.DataFrame([["Company Name: PINNACLE-ZA-C", None], ["Invoice Date", "2026-07-01"]])
    assert sniff_banner_company_token_from_grid(grid) == "PINNACLE-ZA-C"


def test_gate_accepts_confirmed_file_stamp() -> None:
    mapping = {
        "Model": "product_identifier",
        "Invoice Date": "transaction_date",
        "Qty": "quantity_sold",
    }
    errs = dsi_mapping_gate_errors(mapping, file_distributor_satisfied=False)
    assert any(e["code"] == "missing_column_mapping_distributor" for e in errs)
    errs_ok = dsi_mapping_gate_errors(mapping, file_distributor_satisfied=True)
    assert not any(e["code"] == "missing_column_mapping_distributor" for e in errs_ok)


def test_stamp_rows_by_source_file() -> None:
    class _Job:
        staged_metadata = {
            "dsi_file_distributors": {
                "mustek.xlsx": {
                    "token": "MUSTEK-ZA-C",
                    "confirmed": True,
                    "distributor_id": 11,
                    "distributor_name": "Mustek",
                },
                "pinnacle.xlsx": {
                    "token": "PINNACLE-ZA-C",
                    "confirmed": True,
                    "distributor_id": 22,
                    "distributor_name": "Pinnacle",
                },
            },
            "dsi_batch_filenames": ["mustek.xlsx", "pinnacle.xlsx"],
        }
        field_mapping = {}
        file_name = None

    df = pd.DataFrame(
        {
            "_dsi_source_file": ["mustek.xlsx", "pinnacle.xlsx", "mustek.xlsx"],
            "product_identifier": ["A", "B", "C"],
        }
    )
    out = apply_file_distributor_stamps_to_dataframe(_Job(), df)  # type: ignore[arg-type]
    assert out["distributor_token"].tolist() == ["MUSTEK-ZA-C", "PINNACLE-ZA-C", "MUSTEK-ZA-C"]


def test_identity_satisfied_per_file_column_or_stamp() -> None:
    class _Job:
        staged_metadata = {
            "dsi_file_distributors": {
                "banner.xlsx": {
                    "token": "MUSTEK-ZA-C",
                    "confirmed": True,
                    "distributor_id": 1,
                    "distributor_name": "Mustek",
                },
                "column.xlsx": {
                    "token": None,
                    "confirmed": False,
                    "distributor_id": None,
                    "distributor_name": None,
                },
            },
            "dsi_batch_filenames": ["banner.xlsx", "column.xlsx"],
        }
        field_mapping = {
            "banner.xlsx::Sheet1": {
                "Model": "product_identifier",
                "Qty": "quantity_sold",
                "Date": "transaction_date",
            },
            "column.xlsx::Sheet1": {
                "Dist": "distributor_token",
                "Model": "product_identifier",
                "Qty": "quantity_sold",
                "Date": "transaction_date",
            },
        }
        file_name = None

    job = _Job()
    assert is_nested_dsi_field_mapping(job.field_mapping)
    assert file_distributors_all_confirmed(job)  # type: ignore[arg-type]
    assert distributor_identity_satisfied(
        job,  # type: ignore[arg-type]
        job.field_mapping["banner.xlsx::Sheet1"],
        mapping_key="banner.xlsx::Sheet1",
    )
    assert distributor_identity_satisfied(
        job,  # type: ignore[arg-type]
        job.field_mapping["column.xlsx::Sheet1"],
        mapping_key="column.xlsx::Sheet1",
    )


def test_nested_mapping_keys_are_not_flat_headers() -> None:
    nested = {
        "mustek.xlsx::Sheet1": {"Model": "product_identifier"},
        "pinnacle.xlsx::Sheet1": {"Model": "product_identifier"},
    }
    assert is_nested_dsi_field_mapping(nested) is True
    assert is_nested_dsi_field_mapping({"Model": "product_identifier"}) is False


def test_confirmed_file_stamps_satisfy_distributor_gate_without_column() -> None:
    """Canonical writer: confirmed per-file stamps pass the distributor gate (no Dist column)."""
    from sqlalchemy import select

    from app.db.session_sync import SessionLocal
    from app.ingestion.pipeline import process_import_job_sync
    from app.models.dimensions import DimDistributor
    from app.models.ingestion import ImportJob, ImportRowResult, RawFileMetadata
    from app.services.imports.dsi_file_distributor import set_dsi_file_distributors
    from app.storage.local import get_storage_backend
    from app.utils.json_safe import to_jsonable
    from tests.test_dsi_batch import _seed_dsi_source_for_batch_e2e

    source_id = _seed_dsi_source_for_batch_e2e()
    csv = (
        "sku,date,qty,customer_name,soh\n"
        "SKU-ALPHA-01,2024-06-01,2,Mystery Dealer Zed,10\n"
    ).encode("utf-8")
    storage = get_storage_backend()

    with SessionLocal() as db:
        dist = db.scalar(select(DimDistributor).where(DimDistributor.code == "DIST-01"))
        assert dist is not None
        job = ImportJob(
            source_id=source_id,
            template_slug="distributor_inventory",
            file_name="stamp_gate.csv",
            status="pending",
            stage="mapped",
            import_mode="validate",
            content_type="text/csv",
            field_mapping={
                "sku": "product_identifier",
                "date": "transaction_date",
                "qty": "quantity_sold",
                "customer_name": "customer_dealer_token",
                "soh": "stock_on_hand",
            },
            file_headers=["sku", "date", "qty", "customer_name", "soh"],
            staged_metadata=to_jsonable(
                {
                    "dsi_workflow_mode": "weekly",
                    "dsi_batch_filenames": ["stamp_gate.csv"],
                }
            ),
        )
        db.add(job)
        db.flush()
        key = f"imports/test/{job.id}/stamp_gate.csv"
        storage.save(key, csv, "text/csv")
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(csv), checksum=None))
        set_dsi_file_distributors(
            job,
            {
                "stamp_gate.csv": {
                    "token": "DIST-01",
                    "reason": "banner_company_name",
                    "confirmed": True,
                    "distributor_id": int(dist.id),
                    "distributor_name": dist.name,
                }
            },
        )
        db.add(job)
        db.commit()
        job_id = job.id

        processed = process_import_job_sync(db, job_id)
        assert processed.id == job_id
        missing = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job_id,
                ImportRowResult.code == "missing_distributor_token_mapping",
            )
        ).first()
        assert missing is None, "confirmed file stamps must satisfy the canonical distributor gate"
        refreshed = db.get(ImportJob, job_id)
        assert refreshed is not None
        assert (refreshed.status or "") in ("completed", "completed_with_errors")
