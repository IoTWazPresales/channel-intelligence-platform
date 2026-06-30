"""Shipped fact identity: PO-inclusive upsert keys, collapse planning, fact upsert dedupe."""

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
    _build_collapse_group,
    _classify_group,
    plan_shipped_fact_identity_twin_merges,
)

AMAZON_PO = 8843
OTHER_PO = 8933
DELIVERY = "15260158606"
ITEM = "90NB13Y1-M01XE0"


def _fact(
    *,
    id: int,
    job: int,
    qty: float,
    legacy: bool,
    po_id: int | None = AMAZON_PO,
    delivery: str = DELIVERY,
    item: str = ITEM,
    invoice_line: str | None = None,
) -> SimpleNamespace:
    if legacy:
        sk = f"acza_workbook_shipped:Shipped|{delivery}|{item}"
        inv = None
    else:
        il = invoice_line if invoice_line is not None else str(id)
        sk = f"acza_workbook_shipped:Shipped|{delivery}|{il}|{item}"
        inv = il
    po_seg = str(int(po_id)) if po_id is not None else ""
    key_body = "|".join(x for x in (delivery, item, po_seg) if x)
    return SimpleNamespace(
        id=id,
        fact_upsert_key=f"ship:{key_body}",
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
        operating_unit=None,
    )


def test_shipped_fact_upsert_key_includes_purchase_order_id() -> None:
    k_a = stable_shipped_fact_upsert_key_from_fields(
        delivery_no=DELIVERY,
        item_code=ITEM,
        purchase_order_id=AMAZON_PO,
    )
    k_b = stable_shipped_fact_upsert_key_from_fields(
        delivery_no=DELIVERY,
        item_code=ITEM,
        purchase_order_id=OTHER_PO,
    )
    assert k_a == f"ship:{DELIVERY}|{ITEM}|{AMAZON_PO}"
    assert k_b == f"ship:{DELIVERY}|{ITEM}|{OTHER_PO}"
    assert k_a != k_b


def test_shipped_fact_upsert_key_ignores_invoice_line() -> None:
    with_inv = stable_shipped_fact_upsert_key_from_fields(
        delivery_no="15260139536",
        item_code="90NB1542-M007D0",
        purchase_order_id=10,
    )
    without = stable_shipped_fact_upsert_key_from_fields(
        delivery_no="15260139536",
        item_code="90NB1542-M007D0",
        purchase_order_id=10,
    )
    assert with_inv == without == "ship:15260139536|90NB1542-M007D0|10"


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


def test_dedupe_shipped_rows_sums_quantity_same_po_within_chunk() -> None:
    key = f"ship:{DELIVERY}|{ITEM}|{AMAZON_PO}"
    rows = [
        {
            "fact_upsert_key": key,
            "line_state": "shipped",
            "quantity": 36.0,
            "import_job_id": 153,
            "purchase_order_id": AMAZON_PO,
        },
        {
            "fact_upsert_key": key,
            "line_state": "shipped",
            "quantity": 36.0,
            "import_job_id": 153,
            "purchase_order_id": AMAZON_PO,
        },
    ]
    out = _dedupe_rows_for_fact_upsert(rows)
    assert len(out) == 1
    assert out[0]["quantity"] == 72.0


def test_dedupe_keeps_different_po_rows_separate() -> None:
    key_a = f"ship:{DELIVERY}|{ITEM}|{AMAZON_PO}"
    key_b = f"ship:{DELIVERY}|{ITEM}|{OTHER_PO}"
    rows = [
        {"fact_upsert_key": key_a, "line_state": "shipped", "quantity": 36.0, "import_job_id": 153},
        {"fact_upsert_key": key_b, "line_state": "shipped", "quantity": 48.0, "import_job_id": 153},
    ]
    out = _dedupe_rows_for_fact_upsert(rows)
    assert len(out) == 2
    assert {r["quantity"] for r in out} == {36.0, 48.0}


def test_dedupe_does_not_merge_open_order_rows() -> None:
    rows = [
        {"fact_upsert_key": "k1", "line_state": "open_order", "quantity": 5.0},
        {"fact_upsert_key": "k1", "line_state": "open_order", "quantity": 7.0},
    ]
    out = _dedupe_rows_for_fact_upsert(rows)
    assert len(out) == 1
    assert out[0]["quantity"] == 7.0


def test_delivery_15260158606_amazon_lines_sum_other_po_separate() -> None:
    """Invoice lines 1+2 (Amazon PO) sum; line 3 (other PO) stays a separate collapse group."""
    line1 = _fact(id=1, job=153, qty=36.0, legacy=False, po_id=AMAZON_PO, invoice_line="1")
    line2 = _fact(id=2, job=153, qty=36.0, legacy=False, po_id=AMAZON_PO, invoice_line="2")
    line3 = _fact(id=3, job=153, qty=48.0, legacy=False, po_id=OTHER_PO, invoice_line="3")

    amazon_key = f"ship:{DELIVERY}|{ITEM}|{AMAZON_PO}"
    other_key = f"ship:{DELIVERY}|{ITEM}|{OTHER_PO}"

    amazon_group = _build_collapse_group(amazon_key, [line1, line2])
    assert amazon_group.survivor_qty == 72.0
    assert amazon_group.loser_ids == (1,)

    plans, skipped = plan_shipped_fact_identity_twin_merges(_mock_db([line1, line2, line3]))
    assert len(skipped) == 0
    assert len(plans) == 1
    assert plans[0].fact_upsert_key == amazon_key
    assert plans[0].survivor_qty == 72.0


def test_multi_po_on_delivery_produces_separate_plans_not_skip() -> None:
    a = _fact(id=10, job=40, qty=21.0, legacy=True, po_id=AMAZON_PO, delivery="15260158594", item="90NR0QE7-M00020")
    b = _fact(id=11, job=153, qty=21.0, legacy=False, po_id=AMAZON_PO, delivery="15260158594", item="90NR0QE7-M00020", invoice_line="1")
    c = _fact(id=12, job=153, qty=48.0, legacy=False, po_id=OTHER_PO, delivery="15260158594", item="90NR0QE7-M00020", invoice_line="2")

    plans, skipped = plan_shipped_fact_identity_twin_merges(_mock_db([a, b, c]))
    assert skipped == []
    assert len(plans) == 1
    assert plans[0].purchase_order_id == AMAZON_PO
    assert plans[0].survivor_qty == 21.0


def _mock_db(facts: list[SimpleNamespace]) -> MagicMock:
    db = MagicMock()
    db.scalars.return_value.all.return_value = facts
    return db


def test_classify_clean_1_1_legacy_populated() -> None:
    legacy = _fact(id=1, job=40, qty=108.0, legacy=True, delivery="D1")
    populated = _fact(id=2, job=153, qty=108.0, legacy=False, delivery="D1")
    outcome = _classify_group(f"ship:D1|ITEM|{AMAZON_PO}", [legacy, populated])
    assert outcome.bucket == "clean"
    assert outcome.keeper_id == 2
    assert outcome.survivor_qty == 108.0
    assert outcome.loser_ids == (1,)


def test_classify_multi_invoice_legacy_vs_two_populated() -> None:
    legacy = _fact(id=1, job=40, qty=36.0, legacy=True, delivery="D2")
    pop_a = _fact(id=2, job=153, qty=36.0, legacy=False, delivery="D2", invoice_line="1")
    pop_b = _fact(id=3, job=153, qty=36.0, legacy=False, delivery="D2", invoice_line="2")
    outcome = _classify_group(f"ship:D2|ITEM|{AMAZON_PO}", [legacy, pop_a, pop_b])
    assert outcome.bucket == "multi_invoice"
    assert outcome.survivor_qty == 72.0
    assert set(outcome.loser_ids) == {1, 2}


def test_row_values_from_evidence_sets_po_inclusive_fact_upsert_key() -> None:
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
        purchase_order_id=AMAZON_PO,
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
    assert row["fact_upsert_key"] == f"ship:Shipped|D|I|{AMAZON_PO}"
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
            "fact_upsert_key": f"ship:OU|D|I|{AMAZON_PO}",
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
    legacy = _fact(id=10, job=40, qty=36.0, legacy=True)
    pop1 = _fact(id=11, job=153, qty=36.0, legacy=False, invoice_line="1")
    pop2 = _fact(id=12, job=153, qty=36.0, legacy=False, invoice_line="2")
    plans, skipped = plan_shipped_fact_identity_twin_merges(_mock_db([legacy, pop1, pop2]))
    assert len(plans) == 1
    assert plans[0].bucket == "multi_invoice"
    assert plans[0].survivor_qty == 72.0
    assert skipped == []
