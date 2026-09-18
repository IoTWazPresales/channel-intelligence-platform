from app.services.cpor.settlement_desk import (
    cip_amount_product_grain,
    classify_corroboration,
    customer_amount_line_grain,
)


def test_classify_pending_when_no_customer_report():
    assert classify_corroboration(cip_qty=10, customer_qty=None, has_customer_report=False) == "pending"


def test_classify_cip_only_when_customer_qty_zero():
    assert classify_corroboration(cip_qty=12, customer_qty=0, has_customer_report=True) == "cip_only"


def test_classify_match_exact_equality_not_ten_percent():
    assert classify_corroboration(cip_qty=118, customer_qty=118, has_customer_report=True) == "match"
    assert classify_corroboration(cip_qty=100, customer_qty=91, has_customer_report=True) == "mismatch"


def test_cip_amount_product_grain_does_not_double_count_duplicate_sku_lines():
    lines = [
        {"product_id": 1, "cip_qty": 10, "support_unit": 5, "customer_qty": None},
        {"product_id": 1, "cip_qty": 10, "support_unit": 5, "customer_qty": None},
        {"product_id": 2, "cip_qty": 4, "support_unit": 2, "customer_qty": None},
    ]
    assert cip_amount_product_grain(lines) == 58.0


def test_customer_amount_none_when_tape_empty():
    lines = [
        {"product_id": 1, "cip_qty": 10, "support_unit": 5, "customer_qty": None},
    ]
    assert customer_amount_line_grain(lines) is None
