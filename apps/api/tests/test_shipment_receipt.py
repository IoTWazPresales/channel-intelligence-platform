"""Shipment receipt grouping and the cancelled-candidate rule."""

from datetime import datetime, timezone

from app.services.shipping.shipment_receipt import (
    receipt_group,
    receipt_line_identity,
    reports_oldest_first,
    vanished_line_keys,
)


def test_delivery_groups_the_shipment():
    assert receipt_group({"delivery_no": "D1", "order_no": "O1"}) == "delivery"


def test_order_groups_when_there_is_no_delivery():
    assert receipt_group({"delivery_no": "  ", "order_no": "O1"}) == "order"


def test_identity_matches_the_order_grain():
    key = receipt_line_identity(
        {
            "line_state": "shipped",
            "operating_unit": "ZA",
            "order_no": "100",
            "order_line": "1",
            "item_code": "SKU",
        }
    )
    assert key == "order:ZA|100|1|SKU"


def test_one_report_does_not_flag_a_cancelled_candidate():
    assert vanished_line_keys([{"line-a"}]) == set()


def test_line_missing_from_the_latest_report_is_a_cancelled_candidate():
    reports = reports_oldest_first(
        [
            (1, datetime(2026, 1, 1, tzinfo=timezone.utc), "line-a"),
            (1, datetime(2026, 1, 1, tzinfo=timezone.utc), "line-b"),
            (2, datetime(2026, 2, 1, tzinfo=timezone.utc), "line-b"),
        ]
    )
    assert vanished_line_keys(reports) == {"line-a"}


def test_line_that_returns_on_the_latest_report_is_not_a_candidate():
    reports = [{"line-a"}, {"line-b"}, {"line-a", "line-b"}]
    assert vanished_line_keys(reports) == set()
