"""Shipped fact identity: stable upsert keys, collapse planning, fact upsert dedupe."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.imports.shipment_evidence_line_identity import (
    fact_upsert_key_for_evidence_values,
    is_legacy_shipped_source_key,
    stable_line_identity_key_from_fields,
    stable_shipped_fact_upsert_key_from_fields,
)
from app.services.imports.shipment_inbound_facts import (
    _dedupe_rows_for_fact_upsert,
    _row_values_from_evidence,
)
from app.services.imports.shipment_shipped_fact_identity_twin_merge import (
    ShippedFactCollapseGroup,
    ShippedFactCollapseSkip,
    _build_collapse_group,
    _classify_group,
    plan_shipped_fact_identity_twin_merges,
)


def _fact(
    *,
    id: int,
    job: int,
    qty: float,
    legacy: bool,
    po_id: int | None = 10,
    delivery: str = "D",
    item: str = "ITEM",
) -> SimpleNamespace:
    if legacy:
        sk = f"acza_workbook_shipped:Shipped|{delivery}|{item}"
        inv = None
    else:
        sk = f"acza_workbook_shipped:Shipped|{delivery}|{id}|{item}"
        inv = str(id)
    return SimpleNamespace(
      id=id,
      fact_upsert_key=f"ship:Shipped|{delivery}|{item}",
      line_state="shipped",
      source_key=sk,
      invoice_line=inv,
      quantity=qty,
      amount=None,
      import_job_id=job,
      purchase_order_id=po_id,
      resolved_customer_id=26,
      delivery_no=delivery,
      item_code=item,
      operating_unit="Shipped",
  )


def test_shipped_fact_upsert_key_ignores_invoice_line() -> None:
    with_inv = stable_shipped_fact_upsert_key_from_fields(
        operating_unit="Shipped",
        delivery_no="15260139536",
        item_code="90NB1542-M007D0",
    )
    without = stable_shipped_fact_upsert_key_from_fields(
        operating_unit="Shipped",
        delivery_no="15260139536",
        item_code="90NB1542-M007D0",
    )
    assert with_inv == without == "ship:Shipped|15260139536|90NB1542-M007D0"


def test_line_identity_key_still_includes_invoice_line() -> None:
    key = stable_line_identity_key_from_fields(
        operating_unit="Shipped",
        delivery_no="15260139536",
        invoice_line="1",
        item_code="90NB1542-M007D0",
    )
    assert key == "ship:Shipped|15260139536|1|90NB1542-M007D0"


def test_open_order_fact_upsert_key_uses_source_key() -> None:
    sk = "acza_workbook_unship:Unship|OU|ORD|1|ITEM"
    assert (
        fact_upsert_key_for_evidence_values(
            {"line_state": "open_order", "source_key": sk, "order_no": "ORD", "order_line": "1"}
        )
        == sk
    )


def test_legacy_vs_populated_source_key_detection() -> None:
    assert is_legacy_shipped_source_key("acza_workbook_shipped:Shipped|15260139536|90NB1542-M007D0")
    assert not is_legacy_shipped_source_key(
        "acza_workbook_shipped:Shipped|15260139536|1|90NB1542-M007D0"
    )


def test_dedupe_shipped_rows_sums_quantity_within_chunk() -> None:
    key = "ship:Shipped|15260158606|90NB13Y1-M01XE0"
    rows = [
        {"fact_upsert_key": key, "line_state": "shipped", "quantity": 36.0, "import_job_id": 1},
        {"fact_upsert_key": key, "line_state": "shipped", "quantity": 36.0, "import_job_id": 1},
    ]
    out = _dedupe_rows_for_fact_upsert(rows)
    assert len(out) == 1
    assert out[0]["quantity"] == 72.0


def test_dedupe_does_not_merge_open_order_rows() -> None:
    rows = [
        {"fact_upsert_key": "k1", "line_state": "open_order", "quantity": 5.0},
        {"fact_upsert_key": "k1", "line_state": "open_order", "quantity": 7.0},
    ]
    out = _dedupe_rows_for_fact_upsert(rows)
    assert len(out) == 1
    assert out[0]["quantity"] == 7.0


def test_classify_clean_1_1_legacy_populated() -> None:
    legacy = _fact(id=1, job=40, qty=108.0, legacy=True, delivery="D1")
    populated = _fact(id=2, job=153, qty=108.0, legacy=False, delivery="D1")
    outcome = _classify_group("ship:Shipped|D1|ITEM", [legacy, populated])
    assert isinstance(outcome, ShippedFactCollapseGroup)
    assert outcome.bucket == "clean"
    assert outcome.keeper_id == 2
    assert outcome.survivor_qty == 108.0
    assert outcome.loser_ids == (1,)


def test_classify_multi_invoice_legacy_vs_two_populated() -> None:
    legacy = _fact(id=1, job=40, qty=36.0, legacy=True, delivery="D2")
    pop_a = _fact(id=2, job=153, qty=36.0, legacy=False, delivery="D2")
    pop_b = _fact(id=3, job=153, qty=36.0, legacy=False, delivery="D2")
    outcome = _classify_group("ship:Shipped|D2|ITEM", [legacy, pop_a, pop_b])
    assert isinstance(outcome, ShippedFactCollapseGroup)
    assert outcome.bucket == "multi_invoice"
    assert outcome.survivor_qty == 72.0
    assert set(outcome.loser_ids) == {1, 2}


def test_classify_multi_import_multiple_legacy_jobs() -> None:
    pop = _fact(id=1, job=147, qty=216.0, legacy=False, delivery="D3", po_id=None)
    leg_a = _fact(id=2, job=153, qty=216.0, legacy=True, delivery="D3", po_id=None)
    leg_b = _fact(id=3, job=154, qty=216.0, legacy=True, delivery="D3", po_id=None)
    outcome = _classify_group("ship:Shipped|D3|ITEM", [pop, leg_a, leg_b])
    assert isinstance(outcome, ShippedFactCollapseGroup)
    assert outcome.bucket == "multi_import"
    assert outcome.max_import_job_id == 154
    assert outcome.survivor_qty == 216.0
    assert set(outcome.loser_ids) == {1, 2}


def test_skip_multi_po_on_one_key() -> None:
    a = _fact(id=1, job=40, qty=10.0, legacy=True, delivery="D4", po_id=100)
    b = _fact(id=2, job=153, qty=10.0, legacy=False, delivery="D4", po_id=200)
    outcome = _build_collapse_group("ship:Shipped|D4|ITEM", [a, b])
    assert isinstance(outcome, ShippedFactCollapseSkip)
    assert outcome.reason == "multiple_distinct_purchase_order_ids"


def test_row_values_from_evidence_sets_fact_upsert_key() -> None:
    line = SimpleNamespace(
        id=99,
        import_job_id=153,
        source_key="acza_workbook_shipped:Shipped|D|1|I",
        source_sheet="Shipped",
        source_row_number=2,
        report_type="acza_workbook_shipped",
        line_state="shipped",
        raw_source_row={},
        operating_unit="Shipped",
        bill_to_raw=None,
        ship_to_raw=None,
        order_no=None,
        customer_po="PO1",
        purchase_order_id=1,
        order_line=None,
        delivery_no="D",
        invoice_line="1",
        item_code="I",
        sales_model_name="M",
        customer_item=None,
        ean_code=None,
        upc_code=None,
        mpor_item_no=None,
        quantity=10.0,
        unit_price=None,
        amount=None,
        currency_code=None,
        ship_confirm_date=None,
        schedule_ship_date=None,
        promise_date=None,
        exwork_date=None,
        erd_date=None,
        est_pod_date=None,
        pod_date=None,
        crad_date=None,
        product_id=1,
        product_resolution_status="resolved",
        product_resolution_token=None,
        product_resolution_detail=None,
        distributor_id=1,
        distributor_resolution_status="resolved",
        distributor_resolution_token=None,
        customer_dealer_token=None,
        customer_id=26,
        customer_resolution_status="resolved",
        resolved_customer_id=26,
        resolved_distributor_id=1,
    )
    row = _row_values_from_evidence(line)  # type: ignore[arg-type]
    assert row["fact_upsert_key"] == "ship:Shipped|D|I"
    assert row["source_key"] == "acza_workbook_shipped:Shipped|D|1|I"


def test_upsert_splits_shipped_and_open_order_paths(monkeypatch) -> None:
    from app.services.imports import shipment_inbound_facts as facts_mod

    calls: list[str] = []

    def _ship(db, tbl, rows):
        calls.append(f"shipped:{len(rows)}")

    def _open(db, tbl, rows):
        calls.append(f"open:{len(rows)}")

    monkeypatch.setattr(facts_mod, "_upsert_shipped_chunk", _ship)
    monkeypatch.setattr(facts_mod, "_upsert_open_order_chunk", _open)
    monkeypatch.setattr(
        facts_mod,
        "_row_values_from_evidence",
        lambda line: {
            "source_key": "k",
            "fact_upsert_key": "ship:OU|D|I",
            "import_job_id": 1,
            "line_state": "shipped" if getattr(line, "shipped", True) else "open_order",
            "quantity": 5.0,
        },
    )

    line_ship = MagicMock(shipped=True)
    line_open = MagicMock(shipped=False)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [line_ship, line_open]
    facts_mod.upsert_inbound_shipment_facts_for_job(db, 1)
    assert calls == ["shipped:1", "open:1"]


def test_plan_merge_collapses_split_groups(monkeypatch) -> None:
    db = MagicMock()
    legacy = _fact(id=10, job=40, qty=36.0, legacy=True)
    pop1 = _fact(id=11, job=153, qty=36.0, legacy=False)
    pop2 = _fact(id=12, job=153, qty=36.0, legacy=False)
    db.scalars.return_value.all.return_value = [legacy, pop1, pop2]
    plans, skipped = plan_shipped_fact_identity_twin_merges(db)
    assert len(plans) == 1
    assert plans[0].bucket == "multi_invoice"
    assert plans[0].survivor_qty == 72.0
    assert skipped == []
