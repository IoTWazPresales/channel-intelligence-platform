"""Final wave (c): one aged-stock line per customer, product and site, whatever the label's case."""

from __future__ import annotations

from app.services.store_dc.stock_actions import _blocks, _suggestion_rows


def _line(product_id: int, soh: float) -> dict:
    return {
        "product_id": product_id,
        "stock_on_hand": soh,
        "suggestions": ["promote"],
        "slow": True,
    }


def test_a_store_listed_under_sites_and_a_dc_with_other_case_is_one_block():
    view = {
        "customer_name": "Customer A",
        "sites": [{"site_label": "North Mall", "customer_id": 1, "lines": [_line(9, 4)]}],
        "dc_sections": [
            {
                "customer_id": 1,
                "site_label": "Hub",
                "stores": [{"site_label": "north  mall", "customer_id": 1, "lines": [_line(9, 4)]}],
                "need_from_distributor": [],
            }
        ],
    }
    blocks = _blocks(view, customer_id=1)
    assert [b["site_label"] for b in blocks] == ["North Mall"]
    rows = _suggestion_rows(view, customer_id=1)
    assert [(r["product_id"], r["site_label"]) for r in rows] == [(9, "North Mall")]


def test_distinct_sites_stay_distinct_and_other_owners_are_dropped():
    view = {
        "customer_name": "Customer A",
        "sites": [
            {"site_label": "North", "customer_id": 1, "lines": [_line(9, 4)]},
            {"site_label": "South", "customer_id": 1, "lines": [_line(9, 2)]},
        ],
        "dc_sections": [
            {
                "customer_id": 2,
                "site_label": "Other hub",
                "stores": [{"site_label": "East", "customer_id": 2, "lines": [_line(9, 1)]}],
                "need_from_distributor": [_line(9, 1)],
            }
        ],
    }
    rows = _suggestion_rows(view, customer_id=1)
    assert [(r["product_id"], r["site_label"]) for r in rows] == [(9, "North"), (9, "South")]


def test_dc_need_block_with_a_label_matching_a_store_is_not_added_twice():
    view = {
        "customer_name": "Customer A",
        "sites": [{"site_label": "Hub", "customer_id": 1, "lines": [_line(9, 4)]}],
        "dc_sections": [
            {
                "customer_id": 1,
                "site_label": " HUB ",
                "stores": [],
                "need_from_distributor": [_line(9, 3)],
            }
        ],
    }
    rows = _suggestion_rows(view, customer_id=1)
    assert len(rows) == 1 and rows[0]["stock_on_hand"] == 4
