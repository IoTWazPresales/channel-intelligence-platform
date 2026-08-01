"""Distributor sales & inventory import: staging, candidates, facts, upsert apply (sync pipeline)."""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from sqlalchemy import func, inspect, select

from app.db.session_sync import SessionLocal
from app.ingestion.pipeline import process_import_job_sync
from app.services.imports.dsi_mapping_workflow import (
    column_samples_from_inferred,
    dsi_mapping_gate_errors,
    sanitize_dsi_field_mapping,
)
from app.models.dimensions import DimChannel, DimCustomer, DimDistributor, DimProduct, DimRegion
from app.models.facts import FactInboundShipment, FactInventoryDistributor, FactReturns, FactSalesSellout
from app.services.imports.dsi_fact_source_keys import dsi_sellout_source_key
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob, ImportRowResult, ImportTemplate, RawFileMetadata, SourceDefinition
from app.models.mapping import EntityMappingQueue
from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync
from app.services.seed_demo import _seed_import_core
from app.storage.local import get_storage_backend


def _dsi_source_id(db) -> int:
    sid = db.scalar(select(SourceDefinition.id).where(SourceDefinition.code == "distributor_inventory"))
    assert sid is not None
    return int(sid)


def _seed_dsi_catalog() -> int:
    """Import templates/sources + minimal dims for DSI tests. Returns distributor_inventory source_id."""
    with SessionLocal() as db:
        names = set(inspect(db.connection()).get_table_names())
        if "import_distributor_si_staging_line" not in names:
            pytest.skip(
                "Database missing DSI tables; apply Alembic revision 20260430_0024 (alembic upgrade head)."
            )
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
                )
            )
        db.commit()
        from app.services.imports.product_resolution_index_cache import (
            invalidate_product_resolution_index_cache,
        )

        invalidate_product_resolution_index_cache()
        return _dsi_source_id(db)


def _csv_bytes(content: str) -> bytes:
    return content.encode("utf-8")


def _run_dsi_job(
    source_id: int,
    csv_bytes: bytes,
    *,
    import_mode: str,
    filename: str = "dsi.csv",
    dsi_workflow_mode_explicit: str | None = None,
) -> ImportJob:
    storage = get_storage_backend()
    with SessionLocal() as db:
        staged_meta = None
        if dsi_workflow_mode_explicit:
            staged_meta = {"dsi_workflow_mode_explicit": dsi_workflow_mode_explicit}
        job = ImportJob(
            source_id=source_id,
            template_slug="distributor_inventory",
            import_mode=import_mode,
            status="pending",
            stage="uploaded",
            file_name=filename,
            content_type="text/csv",
            staged_metadata=staged_meta,
        )
        db.add(job)
        db.flush()
        key = f"imports/test/{job.id}/{filename}"
        storage.save(key, csv_bytes, job.content_type)
        db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(csv_bytes), checksum=None))
        db.commit()
        return process_import_job_sync(db, job.id)


@pytest.fixture(scope="module")
def dsi_source_id() -> int:
    return _seed_dsi_catalog()


def test_distributor_si_template_pipeline_handler(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        row = db.scalar(select(ImportTemplate).where(ImportTemplate.slug == "distributor_inventory"))
        assert row is not None
        assert row.pipeline_handler == "distributor_sales_inventory"
        assert row.display_name == "Distributor sales & inventory"


def test_distributor_si_validate_staging_candidates_no_queue_spam(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-01-15,2,Mystery Dealer Zed,10\n"
        "DIST-01,SKU-ALPHA-01,2024-01-15,1,Mystery Dealer Zed,5\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate")
    job_id = job.id

    with SessionLocal() as db:
        cust_cands = db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job_id,
                ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            )
        ).all()
        assert len(cust_cands) == 1
        assert cust_cands[0].row_count == 2

        qn = db.scalar(select(func.count()).select_from(EntityMappingQueue).where(EntityMappingQueue.job_id == job_id))
        assert int(qn or 0) == 0

        lines = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job_id)
        ).all()
        assert len(lines) == 2
        assert all(l.severity == "warning" for l in lines)
        assert all(l.resolution_status == "ready_inventory" for l in lines)
        assert all("sellout_blocked_missing_customer" in (l.diagnostic_codes or []) for l in lines)

        summary = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job_id, ImportRowResult.code == "distributor_si_summary"
            )
        ).first()
        assert summary is not None
        assert "aggregated_candidates" in (summary.message or "")


def test_distributor_si_apply_sellout_and_inventory_and_double_apply(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh,channel,amount,revenue,currency\n"
        'DIST-01,SKU-ALPHA-01,2024-02-01,2,"",10,Open Channel retail,100,999,USD\n'
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_apply.csv")
    job_id = job.id

    with SessionLocal() as db:
        fs = db.scalars(select(FactSalesSellout).where(FactSalesSellout.source_import_job_id == job_id)).all()
        assert len(fs) == 1
        assert fs[0].units == 2
        assert fs[0].unit_sellout_price_ex_tax_amount == 100
        assert fs[0].currency_code == "USD"
        assert fs[0].reported_revenue_amount == 999
        assert fs[0].computed_revenue_amount == 200

        inv = db.scalars(
            select(FactInventoryDistributor).where(FactInventoryDistributor.source_import_job_id == job_id)
        ).all()
        assert len(inv) == 1
        assert inv[0].on_hand_units == 10

        ship_n = db.scalar(select(func.count()).select_from(FactInboundShipment))
        assert int(ship_n or 0) >= 0

        j = db.get(ImportJob, job_id)
        assert j and (j.staged_metadata or {}).get("distributor_si", {}).get("applied") is True

    # Re-applying the same job is idempotent (upsert); must not double-count or hard-fail.
    with SessionLocal() as db:
        process_import_job_sync(db, job_id)

    with SessionLocal() as db:
        fs2 = db.scalars(select(FactSalesSellout).where(FactSalesSellout.source_import_job_id == job_id)).all()
        inv2 = db.scalars(
            select(FactInventoryDistributor).where(FactInventoryDistributor.source_import_job_id == job_id)
        ).all()
        assert len(fs2) == 1
        assert len(inv2) == 1
        double = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job_id, ImportRowResult.code == "distributor_si_double_apply_blocked"
            )
        ).first()
        assert double is None


def test_distributor_si_approved_alias_resolves_customer(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        cust = db.scalars(select(DimCustomer).where(DimCustomer.code == "CUST-1001")).first()
        dist = db.scalars(select(DimDistributor).where(DimDistributor.code == "DIST-01")).first()
        assert cust and dist
        cust_id = cust.id
        db.add(
            CustomerSourceTokenAlias(
                customer_id=cust_id,
                source_definition_id=dsi_source_id,
                distributor_id=dist.id,
                raw_token="Alias Dealer Token",
                normalized_token="alias dealer token",
                status="approved",
            )
        )
        db.commit()

    csv = (
        "distributor_code,sku,date,qty,customer_name,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-03-01,1,Alias Dealer Token,3\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_alias.csv")
    job_id = job.id

    with SessionLocal() as db:
        line = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job_id)
        ).first()
        assert line is not None
        assert line.severity != "error"
        assert line.resolved_customer_id == cust_id
        fs = db.scalars(select(FactSalesSellout).where(FactSalesSellout.source_import_job_id == job_id)).all()
        assert len(fs) == 1


def test_disti_header_maps_to_distributor_token(dsi_source_id: int) -> None:
    csv = "DISTI,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-05-01,1,CUST-1001,1\n"
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_disti.csv")
    with SessionLocal() as db:
        j = db.get(ImportJob, job.id)
        assert j and j.field_mapping
        inv = {v: k for k, v in (j.field_mapping or {}).items()}
        assert inv.get("distributor_token") == "DISTI"


def test_dsi_mapped_canonical_json_safe_pandas_timestamp_and_numpy() -> None:
    import json

    import numpy as np
    import pandas as pd

    from app.services.imports import distributor_sales_inventory as dsi

    row = pd.Series(
        {
            "Date": pd.Timestamp("2024-06-01"),
            "Qty": np.int64(4),
            "Amt": np.float64(10.5),
        }
    )
    mapping = {
        "Date": "transaction_date",
        "Qty": "quantity_sold",
        "Amt": "unit_sellout_price_ex_tax_amount",
    }
    mapped = dsi._build_mapped_canonical(row, mapping, [])
    json.dumps(mapped, allow_nan=False)
    assert isinstance(mapped["transaction_date"], str)
    assert mapped["quantity_sold"] == 4
    assert mapped["unit_sellout_price_ex_tax_amount"] == 10.5


def test_dsi_verify_json_serializable_preflight() -> None:
    import pandas as pd

    from app.utils.json_safe import verify_json_serializable

    verify_json_serializable("probe", {"d": pd.Timestamp("2024-01-02")})


def test_dsi_sanitize_channel_code_to_channel_key_token() -> None:
    out, notes = sanitize_dsi_field_mapping(["Channel"], {"Channel": "channel_code"})
    assert out == {"Channel": "channel_key_token"}
    assert any(n["code"] == "dsi_target_normalized" for n in notes)


def test_dsi_sanitize_name_to_product_when_productish_header() -> None:
    out, _ = sanitize_dsi_field_mapping(["ModelName"], {"ModelName": "name"})
    assert out == {"ModelName": "product_identifier"}


def test_dsi_sanitize_name_dropped_for_customerish_header() -> None:
    out, notes = sanitize_dsi_field_mapping(["Customer name"], {"Customer name": "name"})
    assert "Customer name" not in out
    assert any(n["code"] == "dsi_target_dropped" for n in notes)


def test_dsi_sanitize_drops_unknown_targets() -> None:
    out, notes = sanitize_dsi_field_mapping(["X"], {"X": "form_factor"})
    assert "X" not in out
    assert any("form_factor" in n["message"] for n in notes)


def test_dsi_dealer_name_group_resolves_when_customer_blank_apply(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,Dealer Name Group,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-11-01,1,,Metro Market Group,2\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_dg_blank_cust.csv")
    jid = job.id
    with SessionLocal() as db:
        line = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == jid)
        ).first()
        assert line is not None
        assert "customer_resolution_primary_dealer_name_group" in (line.diagnostic_codes or [])
        assert line.raw_customer_dealer_token is None
        assert line.raw_dealer_group_token == "Metro Market Group"
        cust = db.scalars(select(DimCustomer).where(DimCustomer.code == "CUST-1001")).first()
        assert cust is not None
        assert line.resolved_customer_id == cust.id
        n_sell = int(
            db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id == jid))
            or 0
        )
        n_inv = int(
            db.scalar(
                select(func.count()).select_from(FactInventoryDistributor).where(
                    FactInventoryDistributor.source_import_job_id == jid
                )
            )
            or 0
        )
        assert n_sell == 1
        assert n_inv == 1


def test_dsi_placeholder_customer_column_uses_dealer_name_group_apply(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,Dealer Name Group,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-11-02,1,to be mapped,Metro Market Group,2\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_tbm_dg.csv")
    jid = job.id
    with SessionLocal() as db:
        line = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == jid)
        ).first()
        assert line is not None
        assert "customer_resolution_primary_dealer_name_group" in (line.diagnostic_codes or [])
        assert line.raw_customer_dealer_token == "to be mapped"
        assert line.raw_dealer_group_token == "Metro Market Group"
        cust = db.scalars(select(DimCustomer).where(DimCustomer.code == "CUST-1001")).first()
        assert cust is not None
        assert line.resolved_customer_id == cust.id


def test_dsi_unresolved_customer_single_candidate_merged_dealer_group_patterns(dsi_source_id: int) -> None:
    """Same dealer group + unresolved sellout: customer vs placeholder customer must not double-insert candidates."""
    csv = (
        "distributor_code,sku,date,qty,customer_name,Dealer Name Group,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-05-10,1,Wootware Zed Unres,Wootware Zed Unres Group,1\n"
        "DIST-01,SKU-ALPHA-01,2024-05-11,1,to be mapped,Wootware Zed Unres Group,1\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_merge_cust_cand.csv")
    jid = job.id
    with SessionLocal() as db:
        cands = list(
            db.scalars(
                select(ImportEntityMappingCandidate).where(
                    ImportEntityMappingCandidate.import_job_id == jid,
                    ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
                )
            ).all()
        )
        assert len(cands) == 1
        assert cands[0].row_count == 2
        assert float(cands[0].total_units or 0) == 2.0
        assert cands[0].normalized_key == "wootware zed unres group"
        assert cands[0].dealer_group_token == "Wootware Zed Unres Group"
        ctx = cands[0].context or {}
        assert ctx.get("primary_source") == "dealer_name_group"
        assert ctx.get("dealer_group_account_raw") == "Wootware Zed Unres Group"
        src = ctx.get("source_customer_name_raw_samples") or []
        assert any("Wootware Zed Unres" in str(x) for x in src)
        assert "wootware zed unres" in (ctx.get("customer_name_evidence_norms") or [])


def test_dsi_mixed_unresolved_sellout_inventory_still_applies_on_apply(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-12-15,3,Mystery Dealer Zed Unresolvable,99\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_mixed_inv.csv")
    jid = job.id
    with SessionLocal() as db:
        n_sell = int(
            db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id == jid))
            or 0
        )
        n_inv = int(
            db.scalar(
                select(func.count()).select_from(FactInventoryDistributor).where(
                    FactInventoryDistributor.source_import_job_id == jid
                )
            )
            or 0
        )
        assert n_sell == 0
        assert n_inv == 1


def test_dsi_qty_zero_does_not_require_customer_inventory_applies(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh,channel\n"
        "DIST-01,SKU-ALPHA-01,2024-12-20,0,,5,Makro retail\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_qty0.csv")
    jid = job.id
    with SessionLocal() as db:
        line = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == jid)
        ).first()
        assert line is not None
        assert line.resolved_customer_id is None
        assert "sellout_blocked_missing_customer" not in (line.diagnostic_codes or [])
        n_sell = int(
            db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id == jid))
            or 0
        )
        n_inv = int(
            db.scalar(
                select(func.count()).select_from(FactInventoryDistributor).where(
                    FactInventoryDistributor.source_import_job_id == jid
                )
            )
            or 0
        )
        assert n_sell == 0
        assert n_inv == 1


def test_dsi_blank_customer_makro_channel_not_open_channel(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh,channel\n"
        "DIST-01,SKU-ALPHA-01,2024-12-22,1,,5,Makro retail\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_blank_makro.csv")
    jid = job.id
    with SessionLocal() as db:
        line = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == jid)
        ).first()
        assert line is not None
        oc = db.scalars(select(DimCustomer).where(DimCustomer.code == "OPEN_CHANNEL")).first()
        if oc is not None:
            assert line.resolved_customer_id != oc.id
        assert "customer_open_channel" not in (line.diagnostic_codes or [])
        assert "sellout_blocked_missing_customer" in (line.diagnostic_codes or [])


def test_dsi_ignored_shipping_evidence_in_mapped_canonical_only(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh,OTW Shipped\n"
        "DIST-01,SKU-ALPHA-01,2024-12-23,1,CUST-1001,3,777\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_ship_raw.csv")
    jid = job.id
    with SessionLocal() as db:
        line = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == jid)
        ).first()
        assert line is not None
        mc = line.mapped_canonical or {}
        ship = mc.get("ignored_shipping_evidence") or {}
        assert "OTW Shipped" in ship
        assert ship.get("OTW Shipped") == 777


def test_dsi_column_samples_from_inferred() -> None:
    job = ImportJob()
    job.inferred_schema = {
        "columns": [
            {"name": "sku", "dtype": "object", "sample": ["A", "B"]},
        ]
    }
    s = column_samples_from_inferred(job)
    assert s["sku"] == ["A", "B"]


def test_dsi_mapping_gate_messages_include_required_wording() -> None:
    errs = dsi_mapping_gate_errors({"x": "distributor_token"})
    codes = {e["code"] for e in errs}
    assert "missing_column_mapping_product" in codes
    assert "missing_column_mapping_date" in codes
    assert "missing_column_mapping_quantity" in codes
    assert any("Required column mapping missing" in e["message"] for e in errs)
    errs2 = dsi_mapping_gate_errors(
        {
            "d": "distributor_token",
            "p": "product_identifier",
            "t": "transaction_date",
        }
    )
    assert any(e["code"] == "missing_column_mapping_quantity" for e in errs2)


def test_dsi_missing_mapping_message_vs_unresolved_distributor(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        job = _run_dsi_job(
            dsi_source_id,
            _csv_bytes("sku,date,qty,customer_name,soh\nSKU-ALPHA-01,2024-06-01,1,CUST-1001,1\n"),
            import_mode="validate",
            filename="dsi_nom.csv",
        )
        miss = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job.id, ImportRowResult.code == "missing_distributor_token_mapping"
            )
        ).first()
        assert miss is not None
        assert "Distributor" in (miss.message or "")
        assert "confirm a per-file" in (miss.message or "") or "column mapping" in (miss.message or "").lower()

    job2 = _run_dsi_job(
        dsi_source_id,
        _csv_bytes(
            "distributor_code,sku,date,qty,customer_name,soh\n"
            "NO-SUCH-DISTI,SKU-ALPHA-01,2024-06-02,1,CUST-1001,1\n"
        ),
        import_mode="validate",
        filename="dsi_bad_dist.csv",
    )
    with SessionLocal() as db:
        line = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job2.id)
        ).first()
        assert line is not None
        assert "unresolved_distributor_token" in (line.diagnostic_codes or [])
        unr = db.scalars(
            select(ImportRowResult).where(
                ImportRowResult.job_id == job2.id, ImportRowResult.code == "unresolved_distributor_token"
            )
        ).first()
        if unr is not None:
            assert "could not be matched" in (unr.message or "").lower()


def test_dsi_amount_column_maps_to_unit_price_not_revenue_alias(dsi_source_id: int) -> None:
    csv = "distributor_code,sku,date,qty,customer_name,soh,Amount,Revenue\nDIST-01,SKU-ALPHA-01,2024-07-01,1,CUST-1001,1,55.5,999\n"
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_amt.csv")
    with SessionLocal() as db:
        j = db.get(ImportJob, job.id)
        inv = {v: k for k, v in (j.field_mapping or {}).items()}
        assert inv.get("unit_sellout_price_ex_tax_amount") == "Amount"
        assert inv.get("reported_revenue_amount") == "Revenue"


def test_dsi_second_apply_same_job_idempotent(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh,channel\n"
        "DIST-01,SKU-ALPHA-01,2024-08-01,2,CUST-1001,5,Open Channel\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_idem.csv")
    jid = job.id
    with SessionLocal() as db:
        n1 = int(db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id == jid)) or 0)
        assert n1 == 1
        process_import_job_sync(db, jid)
        n2 = int(db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id == jid)) or 0)
        assert n2 == 1


def test_dsi_two_jobs_upsert_same_natural_key(dsi_source_id: int) -> None:
    csv = (
        "distributor_code,sku,date,qty,customer_name,soh,channel\n"
        "DIST-01,SKU-ALPHA-01,2024-09-01,3,CUST-1001,7,Open Channel retail\n"
    )
    _ = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_a.csv")
    job_b = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_b.csv")
    with SessionLocal() as db:
        prod_id = db.scalar(select(DimProduct.id).where(DimProduct.sku == "SKU-ALPHA-01"))
        n = db.scalar(
            select(func.count()).select_from(FactSalesSellout).where(
                FactSalesSellout.product_id == prod_id,
                FactSalesSellout.period_start == date(2024, 9, 1),
            )
        )
        assert int(n or 0) == 1
        row = db.scalars(
            select(FactSalesSellout).where(
                FactSalesSellout.product_id == prod_id,
                FactSalesSellout.period_start == date(2024, 9, 1),
            )
        ).first()
        assert row is not None
        assert row.source_import_job_id == job_b.id
    csv = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-04-01,1,Unknown X,1\n"
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_cand.csv")
    job_id = job.id

    with SessionLocal() as db:
        rows = db.scalars(
            select(ImportEntityMappingCandidate)
            .where(ImportEntityMappingCandidate.import_job_id == job_id)
            .order_by(ImportEntityMappingCandidate.entity_type)
        ).all()
        assert any(r.entity_type == "customer_dealer_token" for r in rows)


def test_dsi_mapping_candidates_http_matches_db_and_job_scope(dsi_source_id: int) -> None:
    """GET /mappings/import-jobs/{id}/distributor-si-candidates matches DB rows and filters by job id."""
    from fastapi.testclient import TestClient

    from app.main import app

    csv = (
        "distributor_code,sku,date,qty,customer_name,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-01-15,2,Mystery Dealer Zed,10\n"
        "DIST-01,SKU-ALPHA-01,2024-01-15,1,Mystery Dealer Zed,5\n"
    )
    job_a = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_http_scope_a.csv")
    csv_b = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-02-20,1,Other Dealer X,1\n"
    job_b = _run_dsi_job(dsi_source_id, _csv_bytes(csv_b), import_mode="validate", filename="dsi_http_scope_b.csv")

    with SessionLocal() as db:
        db_a = list(
            db.scalars(
                select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_a.id)
            ).all()
        )
        db_b = list(
            db.scalars(
                select(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job_b.id)
            ).all()
        )

    # Single TestClient session avoids asyncpg / event-loop teardown races on Windows (see historical_lineup tests).
    with TestClient(app) as client:
        api_a = client.get(f"/api/v1/mappings/import-jobs/{job_a.id}/distributor-si-candidates").json()
        api_b = client.get(f"/api/v1/mappings/import-jobs/{job_b.id}/distributor-si-candidates").json()

    assert api_a["total"] == len(db_a)
    assert api_b["total"] == len(db_b)
    items_a = api_a["items"]
    items_b = api_b["items"]
    assert {row["import_job_id"] for row in items_a} == {job_a.id}
    assert {row["import_job_id"] for row in items_b} == {job_b.id}
    cust_a = next(x for x in items_a if x.get("entity_type") == "customer_dealer_token")
    cust_b = next(x for x in items_b if x.get("entity_type") == "customer_dealer_token")
    assert cust_a["normalized_key"] != cust_b["normalized_key"]
    assert cust_a["row_count"] == 2
    assert "created_at" in cust_a
    assert "source_definition_id" in cust_a

    # Windows + Starlette TestClient can leave asyncpg's transport attached to a closed loop; dispose the
    # async engine so the next test module's TestClient gets a clean pool (mirrors teardown concerns in
    # tests/test_historical_lineup_import.py).
    import asyncio

    from app.db import session as db_session

    async def _dispose() -> None:
        await db_session.engine.dispose()

    asyncio.run(_dispose())


def test_dsi_candidate_steward_map_customer_and_alias_persisted(dsi_source_id: int) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with SessionLocal() as db:
        if "distributor_source_token_alias" not in set(inspect(db.connection()).get_table_names()):
            pytest.skip("Apply migration 20260430_0027 (distributor_source_token_alias).")
    token = f"Steward Map Dealer {secrets.token_hex(4)}"
    csv = f"distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-03-10,1,{token},1\n"
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_steward_cust.csv")
    with SessionLocal() as db:
        cust = db.scalars(select(DimCustomer).where(DimCustomer.code == "CUST-1001")).first()
        assert cust is not None
        cand = db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job.id,
                ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            )
        ).first()
        assert cand is not None
        cand_id = cand.id
        cust_id = cust.id
    with TestClient(app) as client:
        r = client.post(f"/api/v1/mappings/import-candidates/{cand_id}/map-customer", json={"customer_id": cust_id})
        assert r.status_code == 200, r.text
    with SessionLocal() as db:
        cand2 = db.get(ImportEntityMappingCandidate, cand_id)
        assert cand2 is not None
        assert cand2.status == "resolved"
        assert cand2.suggested_entity_id == cust_id
        alias_n = db.scalar(
            select(func.count()).select_from(CustomerSourceTokenAlias).where(
                CustomerSourceTokenAlias.customer_id == cust_id,
                CustomerSourceTokenAlias.import_entity_mapping_candidate_id == cand_id,
            )
        )
        assert int(alias_n or 0) >= 1

    import asyncio

    from app.db import session as db_session

    async def _dispose() -> None:
        await db_session.engine.dispose()

    asyncio.run(_dispose())


def test_dsi_candidate_steward_distributor_alias_then_revalidate_resolves(dsi_source_id: int) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with SessionLocal() as db:
        if "distributor_source_token_alias" not in set(inspect(db.connection()).get_table_names()):
            pytest.skip("Apply migration 20260430_0027 (distributor_source_token_alias).")
    dist_code = f"NOVEL-DIST-{secrets.token_hex(4)}"
    csv = f"distributor_code,sku,date,qty,customer_name,soh\n{dist_code},SKU-ALPHA-01,2024-03-12,1,CUST-1001,1\n"
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_steward_dist.csv")
    with SessionLocal() as db:
        cand = db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job.id,
                ImportEntityMappingCandidate.entity_type == "distributor_token",
            )
        ).first()
        assert cand is not None
        cand_id = cand.id
    with TestClient(app) as client:
        r = client.post(
            f"/api/v1/mappings/import-candidates/{cand_id}/create-provisional-distributor",
            json={"display_name": f"Novel Disti {dist_code}", "confirm_for_suspicious_token": False},
        )
        assert r.status_code == 200, r.text
        dist_id = r.json()["distributor_id"]
    with SessionLocal() as db:
        n_alias = db.scalar(select(func.count()).select_from(DistributorSourceTokenAlias))
        assert int(n_alias or 0) >= 1
    csv2 = f"distributor_code,sku,date,qty,customer_name,soh\n{dist_code},SKU-ALPHA-01,2024-03-13,1,CUST-1001,1\n"
    job2 = _run_dsi_job(dsi_source_id, _csv_bytes(csv2), import_mode="validate", filename="dsi_steward_dist2.csv")
    with SessionLocal() as db:
        line = db.scalars(
            select(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job2.id)
        ).first()
        assert line is not None
        assert line.resolved_distributor_id == dist_id

    import asyncio

    from app.db import session as db_session

    async def _dispose() -> None:
        await db_session.engine.dispose()

    asyncio.run(_dispose())


def test_dsi_candidate_steward_dealer_primary_alias_raw_is_source_customer_not_dealer_group(dsi_source_id: int) -> None:
    """Map-customer alias raw_token must follow source customer evidence, not Dealer Name Group / composite sample."""
    from fastapi.testclient import TestClient

    from app.main import app

    with SessionLocal() as db:
        if "distributor_source_token_alias" not in set(inspect(db.connection()).get_table_names()):
            pytest.skip("Apply migration 20260430_0027 (distributor_source_token_alias).")
    tok = secrets.token_hex(4)
    source_shop = f"SourceShop {tok}"
    dealer_group = f"Metro Reporting Group {tok}"
    csv = (
        "distributor_code,sku,date,qty,customer_name,Dealer Name Group,soh\n"
        f"DIST-01,SKU-ALPHA-01,2024-08-01,1,{source_shop},{dealer_group},1\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_steward_dg_primary.csv")
    with SessionLocal() as db:
        cust = db.scalars(select(DimCustomer).where(DimCustomer.code == "CUST-1001")).first()
        assert cust is not None
        cand = db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job.id,
                ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            )
        ).first()
        assert cand is not None
        assert cand.dealer_group_token == dealer_group
        ctx = cand.context or {}
        assert ctx.get("dealer_group_account_raw") == dealer_group
        assert source_shop in (ctx.get("source_customer_name_raw_samples") or [])
        cand_id = cand.id
        cust_id = cust.id
    with TestClient(app) as client:
        r = client.post(f"/api/v1/mappings/import-candidates/{cand_id}/map-customer", json={"customer_id": cust_id})
        assert r.status_code == 200, r.text
    with SessionLocal() as db:
        alias = db.scalars(
            select(CustomerSourceTokenAlias).where(
                CustomerSourceTokenAlias.import_entity_mapping_candidate_id == cand_id,
                CustomerSourceTokenAlias.customer_id == cust_id,
            )
        ).first()
        assert alias is not None
        assert alias.raw_token == source_shop
        assert (alias.dealer_group_token or "") == dealer_group

    import asyncio

    from app.db import session as db_session

    async def _dispose() -> None:
        await db_session.engine.dispose()

    asyncio.run(_dispose())


def test_dsi_candidate_open_channel_named_requires_confirm(dsi_source_id: int) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    with SessionLocal() as db:
        if "distributor_source_token_alias" not in set(inspect(db.connection()).get_table_names()):
            pytest.skip("Apply migration 20260430_0027 (distributor_source_token_alias).")
    token = f"Named Dealer OC {secrets.token_hex(4)}"
    csv = f"distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-03-14,1,{token},1\n"
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="validate", filename="dsi_steward_oc.csv")
    with SessionLocal() as db:
        cand = db.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == job.id,
                ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            )
        ).first()
        assert cand is not None
        cand_id = cand.id
    with TestClient(app) as client:
        r = client.post(
            f"/api/v1/mappings/import-candidates/{cand_id}/mark-open-channel",
            json={"confirm_for_named_dealer": False, "confirm_for_strategic_channel_hint": False},
        )
        assert r.status_code == 400
        r2 = client.post(
            f"/api/v1/mappings/import-candidates/{cand_id}/mark-open-channel",
            json={"confirm_for_named_dealer": True, "confirm_for_strategic_channel_hint": False},
        )
        assert r2.status_code == 200, r2.text

    import asyncio

    from app.db import session as db_session

    async def _dispose() -> None:
        await db_session.engine.dispose()

    asyncio.run(_dispose())


def _require_dsi_phase0_schema(db) -> None:
    names = set(inspect(db.connection()).get_table_names())
    if "fact_returns" not in names:
        pytest.skip("Apply Alembic revisions 20260518_0038–0040 (fact_returns).")
    cols = {c["name"] for c in inspect(db.connection()).get_columns("import_distributor_si_staging_line")}
    if "invoice_no" not in cols:
        pytest.skip("Apply Alembic revision 20260518_0038 (staging invoice_no).")
    sell_cols = {c["name"] for c in inspect(db.connection()).get_columns("fact_sales_sellout")}
    if "transaction_date" not in sell_cols:
        pytest.skip("Apply Alembic revision 20260518_0038 (sellout transaction_date).")


def test_dsi_sellout_two_invoices_same_day_distinct_source_keys(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        _require_dsi_phase0_schema(db)
    csv = (
        "distributor_code,sku,date,qty,customer_name,invoice_no,soh\n"
        "DIST-01,SKU-ALPHA-01,2024-07-01,2,CUST-1001,INV-A,1\n"
        "DIST-01,SKU-ALPHA-01,2024-07-01,3,CUST-1001,INV-B,1\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_two_inv.csv")
    jid = job.id
    with SessionLocal() as db:
        n = int(
            db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id == jid))
            or 0
        )
        assert n == 2
        rows = list(db.scalars(select(FactSalesSellout).where(FactSalesSellout.source_import_job_id == jid)).all())
        assert len({r.source_key for r in rows}) == 2
        assert rows[0].transaction_date == date(2024, 7, 1)
        assert rows[0].period_start == date(2024, 7, 1)


def test_dsi_sellout_reupload_updates_units_not_identity(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        _require_dsi_phase0_schema(db)
        cust = db.scalars(select(DimCustomer).where(DimCustomer.code == "CUST-1001")).first()
        dist = db.scalars(select(DimDistributor).where(DimDistributor.code == "DIST-01")).first()
        prod = db.scalars(select(DimProduct).where(DimProduct.sku == "SKU-ALPHA-01")).first()
        assert cust and dist and prod
        cust_id, dist_id, prod_id = int(cust.id), int(dist.id), int(prod.id)
    csv1 = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-07-02,5,CUST-1001,1\n"
    _run_dsi_job(dsi_source_id, _csv_bytes(csv1), import_mode="apply", filename="dsi_reup1.csv")
    csv2 = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-07-02,9,CUST-1001,1\n"
    _run_dsi_job(dsi_source_id, _csv_bytes(csv2), import_mode="apply", filename="dsi_reup2.csv")
    sk = dsi_sellout_source_key(
        distributor_id=dist_id,
        product_id=prod_id,
        customer_id=cust_id,
        transaction_date=date(2024, 7, 2),
        invoice_no="",
    )
    with SessionLocal() as db:
        row = db.scalar(select(FactSalesSellout).where(FactSalesSellout.source_key == sk))
        assert row is not None
        assert float(row.units) == 9.0
        assert int(db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_key == sk)) or 0) == 1


def test_dsi_negative_qty_routes_to_returns_not_sellout(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        _require_dsi_phase0_schema(db)
    csv = (
        "distributor_code,sku,date,qty,customer_name,Dealer Name Group,soh,invoice_no\n"
        "DIST-01,SKU-ALPHA-01,2024-07-13,-4,,Metro Market Group,1,INV-NEG-TEST-01\n"
    )
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_neg.csv")
    jid = job.id
    with SessionLocal() as db:
        assert int(db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id == jid)) or 0) == 0
        assert int(db.scalar(select(func.count()).select_from(FactSalesSellout)) or 0) >= 0
        ret = db.scalar(
            select(FactReturns).where(FactReturns.invoice_no == "INV-NEG-TEST-01")
        )
        assert ret is not None
        assert float(ret.return_quantity) == 4.0
        assert ret.source_key.startswith("dsi-return:")
        assert (
            int(
                db.scalar(
                    select(func.count()).select_from(FactSalesSellout).where(
                        FactSalesSellout.invoice_no == "INV-NEG-TEST-01"
                    )
                )
                or 0
            )
            == 0
        )


def test_dsi_zero_qty_skips_sellout_and_returns(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        _require_dsi_phase0_schema(db)
    csv = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-07-04,0,CUST-1001,2\n"
    job = _run_dsi_job(dsi_source_id, _csv_bytes(csv), import_mode="apply", filename="dsi_zero.csv")
    jid = job.id
    with SessionLocal() as db:
        assert int(db.scalar(select(func.count()).select_from(FactSalesSellout).where(FactSalesSellout.source_import_job_id == jid)) or 0) == 0
        assert int(db.scalar(select(func.count()).select_from(FactReturns).where(FactReturns.import_job_id == jid)) or 0) == 0
        assert int(
            db.scalar(
                select(func.count()).select_from(FactInventoryDistributor).where(
                    FactInventoryDistributor.source_import_job_id == jid
                )
            )
            or 0
        ) == 1


def test_dsi_inventory_upserts_by_source_key(dsi_source_id: int) -> None:
    with SessionLocal() as db:
        _require_dsi_phase0_schema(db)
        inv_cols = {c["name"] for c in inspect(db.connection()).get_columns("fact_inventory_distributor")}
        if "source_key" not in inv_cols:
            pytest.skip("Apply Alembic revision 20260518_0040 (inventory source_key).")
    csv1 = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-07-05,0,,10\n"
    csv2 = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-07-05,0,,22\n"
    _run_dsi_job(dsi_source_id, _csv_bytes(csv1), import_mode="apply", filename="dsi_inv1.csv")
    _run_dsi_job(dsi_source_id, _csv_bytes(csv2), import_mode="apply", filename="dsi_inv2.csv")
    with SessionLocal() as db:
        dist = db.scalars(select(DimDistributor).where(DimDistributor.code == "DIST-01")).first()
        prod = db.scalars(select(DimProduct).where(DimProduct.sku == "SKU-ALPHA-01")).first()
        assert dist and prod
        n = int(
            db.scalar(
                select(func.count())
                .select_from(FactInventoryDistributor)
                .where(
                    FactInventoryDistributor.distributor_id == dist.id,
                    FactInventoryDistributor.product_id == prod.id,
                    FactInventoryDistributor.as_of_date == date(2024, 7, 5),
                )
            )
            or 0
        )
        assert n == 1
        row = db.scalars(
            select(FactInventoryDistributor).where(
                FactInventoryDistributor.distributor_id == dist.id,
                FactInventoryDistributor.product_id == prod.id,
                FactInventoryDistributor.as_of_date == date(2024, 7, 5),
            )
        ).first()
        assert row is not None
        assert float(row.on_hand_units) == 22.0
        assert row.source_key == f"dsi-soh:{dist.id}:{prod.id}:2024-07-05"
        assert row.calculated_soh is None
        assert row.reconciliation_status is None


def test_dsi_weekly_validate_skips_post_validate_auto_apply(dsi_source_id: int, monkeypatch) -> None:
    calls: list = []

    def _fake_schedule(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(1)

    monkeypatch.setattr(
        "app.ingestion.dsi_validate_post_sync.schedule_or_enqueue_dsi_post_validate_auto_apply",
        _fake_schedule,
    )
    csv = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-07-06,1,CUST-1001,1\n"
    _run_dsi_job(
        dsi_source_id,
        _csv_bytes(csv),
        import_mode="validate",
        filename="dsi_weekly_pv.csv",
        dsi_workflow_mode_explicit="weekly",
    )
    assert calls == []


def test_dsi_historical_validate_enqueues_ready_candidates_only(dsi_source_id: int, monkeypatch) -> None:
    captured: list[tuple] = []

    def _fake_schedule(sync_db, job, *, candidate_ids, detach_from_caller):  # type: ignore[no-untyped-def]
        captured.append((job.id, candidate_ids, detach_from_caller))
        job.staged_metadata = {
            **(job.staged_metadata or {}),
            "dsi_post_validate_auto_apply": {"candidate_count": len(candidate_ids)},
        }

    def _fake_plan(session, job_id, **kwargs):  # type: ignore[no-untyped-def]
        return {
            "rows": [
                {"candidate_id": 99, "plan_status": "ready", "hold_for_manual_review": False},
                {"candidate_id": 100, "plan_status": "needs_review", "hold_for_manual_review": False},
                {"candidate_id": 101, "plan_status": "ready", "hold_for_manual_review": True},
            ]
        }

    monkeypatch.setenv("CIP_DEFER_DSI_POST_VALIDATE_AUTO_APPLY", "0")
    monkeypatch.setattr(
        "app.ingestion.dsi_validate_post_sync.schedule_or_enqueue_dsi_post_validate_auto_apply",
        _fake_schedule,
    )
    monkeypatch.setattr(
        "app.ingestion.dsi_validate_post_sync.build_dsi_resolution_plan_sync",
        _fake_plan,
    )
    csv = "distributor_code,sku,date,qty,customer_name,soh\nDIST-01,SKU-ALPHA-01,2024-07-07,1,CUST-1001,1\n"
    job = _run_dsi_job(
        dsi_source_id,
        _csv_bytes(csv),
        import_mode="validate",
        filename="dsi_hist_pv.csv",
        dsi_workflow_mode_explicit="historical",
    )
    assert len(captured) == 1
    assert captured[0][1] == [99]
    assert captured[0][2] is True
    with SessionLocal() as db:
        j = db.get(ImportJob, job.id)
        assert j is not None
        meta = j.staged_metadata or {}
        assert meta.get("dsi_post_validate_auto_apply", {}).get("candidate_count") == 1
