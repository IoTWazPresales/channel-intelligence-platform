"""Unit tests for shipment evidence line_identity_key (no database)."""

from __future__ import annotations

from app.services.imports.shipment_evidence_line_identity import (
    observation_payload_hash,
    stable_line_identity_key_from_fields,
    stable_shipped_fact_upsert_key_from_fields,
)


def test_line_identity_key_order_backed() -> None:
    key = stable_line_identity_key_from_fields(
        operating_unit="OU1",
        order_no="PO-99",
        order_line="2",
        item_code="SKU-X",
    )
    assert key == "order:OU1|PO-99|2|SKU-X"


def test_line_identity_key_shipped_corpus_grain() -> None:
    key = stable_line_identity_key_from_fields(
        line_state="shipped",
        operating_unit="OU1",
        order_no="ORD-IGNORED",
        order_line="9",
        delivery_no="D100",
        invoice_line="1",
        item_code="SKU-Y",
        purchase_order_id=42,
    )
    assert key == "ship:OU1|D100|SKU-Y|42|1"


def test_line_identity_key_shipped_requires_po() -> None:
    key = stable_line_identity_key_from_fields(
        line_state="shipped",
        delivery_no="D100",
        invoice_line="1",
        item_code="SKU-Y",
        purchase_order_id=None,
    )
    assert key.startswith("digest:")


def test_line_identity_key_digest_when_no_business_segments() -> None:
    key = stable_line_identity_key_from_fields(raw_source_row={"foo": "bar"})
    assert key.startswith("digest:")


def test_shipped_fact_upsert_key_from_fields() -> None:
    key = stable_shipped_fact_upsert_key_from_fields(
        operating_unit="OU",
        delivery_no="D1",
        item_code="SKU",
    )
    assert key == "ship:OU|D1|SKU"


def test_observation_payload_hash_stable() -> None:
    values = {
        "source_key": "rt:abc",
        "line_identity_key": "order:OU|1|1|I",
        "report_type": "xxomrpt0027_order",
        "line_state": "open_order",
        "source_sheet": "Sheet1",
        "source_row_number": 2,
        "operating_unit": "OU",
        "order_no": "1",
        "order_line": "1",
        "item_code": "I",
        "bill_to_raw": None,
        "ship_to_raw": None,
        "delivery_no": None,
        "invoice_line": None,
        "sales_model_name": None,
        "customer_item": None,
        "ean_code": None,
        "upc_code": None,
        "mpor_item_no": None,
        "quantity": 1.0,
        "unit_price": None,
        "amount": None,
        "currency_code": None,
        "ship_confirm_date": None,
        "schedule_ship_date": None,
        "promise_date": None,
        "exwork_date": None,
        "erd_date": None,
        "est_pod_date": None,
        "pod_date": None,
        "customer_dealer_token": None,
        "customer_id": None,
        "customer_resolution_status": None,
        "product_id": None,
        "product_resolution_status": "no_match",
        "product_resolution_token": None,
        "product_resolution_detail": None,
        "distributor_id": None,
        "distributor_resolution_status": "unresolved",
        "distributor_resolution_token": None,
    }
    h1 = observation_payload_hash(values)
    h2 = observation_payload_hash(dict(values))
    assert h1 == h2
    assert len(h1) == 40
