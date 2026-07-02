"""Unit tests for shipment evidence stable source_key (no database)."""

from __future__ import annotations

import pytest

from app.services.imports.shipment_evidence_report_detect import (
    REPORT_ACZA_SHIPPED,
    REPORT_ACZA_UNSHIP,
    REPORT_XXOMRPT0025,
    REPORT_XXOMRPT0027,
)
from app.services.imports.shipment_evidence_source_keys import (
    ShipmentEvidenceSourceKeyError,
    business_source_key_fragment,
    stable_source_key_for_row,
)


def _ex(**kwargs: str | None) -> dict:
    base = {
        "operating_unit": None,
        "order_no": None,
        "order_line": None,
        "delivery_no": None,
        "invoice_line": None,
        "item_code": None,
    }
    base.update(kwargs)
    return base


def test_xxomrpt0025_shipment_key_uses_delivery_invoice_item() -> None:
    ex = _ex(operating_unit="ORG1", delivery_no="D1", invoice_line="1.1", item_code="SKU-A")
    assert business_source_key_fragment(REPORT_XXOMRPT0025, ex) == "ORG1|D1|1.1|SKU-A"


def test_xxomrpt0027_order_key_uses_order_line_item() -> None:
    ex = _ex(operating_unit="OU9", order_no="PO-1", order_line="3", item_code="SKU-B")
    assert business_source_key_fragment(REPORT_XXOMRPT0027, ex) == "OU9|PO-1|3|SKU-B"


def test_acza_shipped_same_as_shipment_style() -> None:
    ex = _ex(operating_unit="X", delivery_no="900", invoice_line="2", item_code="I")
    assert business_source_key_fragment(REPORT_ACZA_SHIPPED, ex) == "X|900|2|I"


def test_acza_unship_same_as_order_style() -> None:
    ex = _ex(operating_unit="Y", order_no="O1", order_line="1", item_code="Z")
    assert business_source_key_fragment(REPORT_ACZA_UNSHIP, ex) == "Y|O1|1|Z"


def test_stable_key_prefixes_report_type_and_sheet() -> None:
    ex = _ex(delivery_no="D", invoice_line="1", item_code="I")
    k = stable_source_key_for_row(report_type=REPORT_XXOMRPT0025, sheet_name="Sheet1", ex=ex)
    assert k.startswith(f"{REPORT_XXOMRPT0025}:")
    assert "sheet1|" in k


def test_sheet_name_casing_normalized() -> None:
    ex = _ex(delivery_no="D", invoice_line="1", item_code="I")
    k1 = stable_source_key_for_row(report_type=REPORT_ACZA_SHIPPED, sheet_name="Shipped", ex=ex)
    k2 = stable_source_key_for_row(report_type=REPORT_ACZA_SHIPPED, sheet_name="shipped", ex=ex)
    assert k1 == k2


def test_unknown_report_type_raises() -> None:
    with pytest.raises(ShipmentEvidenceSourceKeyError):
        business_source_key_fragment("future_report_v1", _ex(order_no="1"))
