"""Shipment apply hardening — unresolved write-through + failure writeback."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.services.imports.shipment_apply_sync as apply_mod
import app.services.imports.shipment_inbound_facts as facts_mod
from app.ingestion.pipeline import STAGE_FAILED, STAGE_LOADED
from app.services.imports.shipment_apply_failure import (
    ShipmentApplyRowError,
    record_shipment_apply_failure,
)
from app.services.imports.shipment_inbound_facts import _row_values_from_evidence


def test_unresolved_product_row_values_carry_null_product_and_status() -> None:
    line = SimpleNamespace(
        import_job_id=310,
        id=104324,
        source_key="acza_workbook_unship:unship|PO|1.1|SKU",
        source_sheet="Unship",
        source_row_number=12,
        report_type="xxomrpt0027_order",
        line_state="open_order",
        raw_source_row={"Item": "SKU"},
        operating_unit="OU",
        bill_to_raw="Bill",
        ship_to_raw="Ship",
        order_no="PO",
        customer_po=None,
        purchase_order_id=None,
        order_line="1.1",
        delivery_no=None,
        invoice_line=None,
        item_code="90NX0801-M0B3B0",
        sales_model_name="B1503CVA-C516512BMU1X",
        customer_item=None,
        ean_code="4711636703352",
        upc_code="199291703353",
        mpor_item_no=None,
        quantity=5.0,
        unit_price=None,
        amount=None,
        currency_code="USD",
        ship_confirm_date=None,
        schedule_ship_date=None,
        promise_date=None,
        exwork_date=None,
        erd_date=None,
        est_pod_date=None,
        pod_date=None,
        crad_date=None,
        product_id=None,
        product_resolution_status="no_match",
        product_resolution_token="90NX0801-M0B3B0",
        product_resolution_detail="unresolved_product",
        distributor_id=1,
        distributor_resolution_status="resolved",
        distributor_resolution_token="Bill",
        customer_dealer_token=None,
        customer_id=26,
        customer_resolution_status="resolved",
        resolved_customer_id=26,
        resolved_distributor_id=1,
    )
    row = _row_values_from_evidence(line)  # type: ignore[arg-type]
    assert row["product_id"] is None
    assert row["product_resolution_status"] == "no_match"
    assert row["product_resolution_token"] == "90NX0801-M0B3B0"
    assert row["item_code"] == "90NX0801-M0B3B0"
    assert row["quantity"] == 5.0


def test_open_order_upsert_uses_fact_upsert_constraint() -> None:
    assert facts_mod._FACT_UPSERT_CONSTRAINT == "uq_fact_inbound_shipment_fact_upsert_key"
    import inspect

    source = inspect.getsource(facts_mod._upsert_open_order_chunk)
    assert "_FACT_UPSERT_CONSTRAINT" in source
    assert "uq_fact_inbound_shipment_source_key" not in source


def test_record_shipment_apply_failure_uses_fresh_session_and_import_row_result() -> None:
    job = MagicMock()
    job.stage = STAGE_LOADED
    fresh_db = MagicMock()
    fresh_db.get.return_value = job

    with patch("app.services.imports.shipment_apply_failure.SessionLocal") as session_local:
        session_local.return_value.__enter__.return_value = fresh_db
        out = record_shipment_apply_failure(
            310,
            ShipmentApplyRowError(
                "boom",
                evidence_line_id=104324,
                source_key="k",
                source_row_number=12,
            ),
        )

    assert out["outcome"] == "failed"
    assert out["recorded"] is True
    fresh_db.add.assert_called_once()
    row_result = fresh_db.add.call_args[0][0]
    assert row_result.code == "shipment_apply_fact_write_failed"
    assert row_result.row_number == 12
    assert job.status == "failed"
    assert job.stage == STAGE_FAILED
    fresh_db.commit.assert_called_once()


def test_run_shipment_apply_sync_records_failure_without_raising(monkeypatch) -> None:
    job = MagicMock()
    job.template_slug = "inbound_shipments"
    db = MagicMock()
    db.get.return_value = job

    monkeypatch.setattr(apply_mod, "persist_pipeline_worker_started_at", lambda s, j: None)
    monkeypatch.setattr(apply_mod, "apply_high_confidence_shipment_mapping_candidates", lambda job_id: 0)

    def _boom(*_a, **_k):
        raise RuntimeError("simulated apply failure")

    monkeypatch.setattr(apply_mod, "upsert_inbound_shipment_facts_for_job", _boom)
    recorded: list[int] = []

    def _record(job_id, exc, **kwargs):
        recorded.append(job_id)
        return {"id": job_id, "outcome": "failed", "recorded": True}

    monkeypatch.setattr(apply_mod, "record_shipment_apply_failure", _record)

    out = apply_mod.run_shipment_apply_sync(db, 310)
    assert out["outcome"] == "failed"
    assert recorded == [310]
    db.rollback.assert_called_once()


def test_run_shipment_apply_sync_completed_with_errors_when_unresolved_products(monkeypatch) -> None:
    job = MagicMock()
    job.template_slug = "inbound_shipments"
    db = MagicMock()
    db.get.return_value = job
    db.scalar.return_value = 148

    monkeypatch.setattr(apply_mod, "persist_pipeline_worker_started_at", lambda s, j: None)
    monkeypatch.setattr(apply_mod, "persist_clear_background_task_metadata", lambda s, j: None)
    monkeypatch.setattr(apply_mod, "apply_high_confidence_shipment_mapping_candidates", lambda job_id: 0)
    monkeypatch.setattr(apply_mod, "upsert_inbound_shipment_facts_for_job", lambda db, job_id, on_progress=None: 7080)

    out = apply_mod.run_shipment_apply_sync(db, 310)
    assert out["outcome"] == "applied"
    assert out["unresolved_product_rows"] == 148
    assert job.stage == STAGE_LOADED
    assert job.status == "completed_with_errors"
    assert "148" in (job.error_summary or "")


def test_chunk_failure_falls_back_to_row_and_raises_shipment_apply_row_error(monkeypatch) -> None:
    line = MagicMock()
    line.id = 99
    line.source_key = "k"
    line.source_row_number = 7
    db = MagicMock()
    tbl = MagicMock()

    def _chunk_fail(*_a, **_k):
        raise RuntimeError("chunk failed")

    monkeypatch.setattr(facts_mod, "_upsert_shipped_chunk", _chunk_fail)
    monkeypatch.setattr(
        facts_mod,
        "_row_values_from_evidence",
        lambda ln: {
            "source_key": "k",
            "fact_upsert_key": "k",
            "import_job_id": 1,
            "line_state": "open_order",
        },
    )

    def _row_fail(db, tbl, line):
        raise RuntimeError("row failed")

    monkeypatch.setattr(facts_mod, "_upsert_single_evidence_row", _row_fail)

    with pytest.raises(ShipmentApplyRowError) as excinfo:
        facts_mod._upsert_evidence_chunk(db, tbl, [line], [{"line_state": "open_order"}])

    assert excinfo.value.evidence_line_id == 99
    assert excinfo.value.source_key == "k"
