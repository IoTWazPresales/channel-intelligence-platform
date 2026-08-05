"""Unit tests for PO competition classifier (BACKLOG-119). Pure — no DB."""

from __future__ import annotations

from datetime import date

from app.services.commercial_planner.lineup_po_competition import (
    REASON_COMPETES_CROSS_PERIOD,
    REASON_COMPETES_SAME_BU_SAME_PERIOD,
    REASON_INDETERMINATE_NO_SHIPMENT,
    REASON_MULTI_BU_SHARED,
    annotate_proposals_with_competition,
    case_period_key,
    classify_po_competition,
    classify_proposals_competition,
    is_contested,
)


def test_case_period_key_normalizes_26q1_and_2026_q1():
    assert case_period_key(inferred_period_start=date(2026, 1, 1), period_label=None) == "26Q1"
    assert case_period_key(inferred_period_start=None, period_label="2026 Q1") == "26Q1"
    assert case_period_key(inferred_period_start=None, period_label="26Q1") == "26Q1"


def test_c2_multi_bu_shared_not_contested():
    """C2: shipment two BUs; each case overlaps shipped products in its BU."""
    cls = classify_po_competition(
        po_number_norm="POMULTI",
        claiming_cases=[
            {"case_id": 1, "bu": "NB", "period_key": "25Q2"},
            {"case_id": 2, "bu": "NR", "period_key": "25Q2"},
        ],
        ship_product_bu={10: "NB", 20: "NR"},
        case_product_ids={1: {10, 11}, 2: {20, 21}},
    )
    assert cls.status == "not_contested"
    assert cls.reason == REASON_MULTI_BU_SHARED
    assert is_contested({"status": cls.status}) is False


def test_c3_same_bu_same_period_contested():
    cls = classify_po_competition(
        po_number_norm="POSAME",
        claiming_cases=[
            {"case_id": 121, "bu": "NB", "period_key": "26Q2"},
            {"case_id": 122, "bu": "NB", "period_key": "26Q2"},
            {"case_id": 128, "bu": "NB", "period_key": "26Q2"},
        ],
        ship_product_bu={10: "NB"},
        case_product_ids={121: {10}, 122: {10}, 128: {10}},
    )
    assert cls.status == "contested"
    assert cls.reason == REASON_COMPETES_SAME_BU_SAME_PERIOD


def test_c4_cross_period_contested():
    cls = classify_po_competition(
        po_number_norm="POCROSS",
        claiming_cases=[
            {"case_id": 125, "bu": "NR", "period_key": "25Q3"},
            {"case_id": 126, "bu": "NR", "period_key": "25Q4"},
        ],
        ship_product_bu={10: "NR"},
        case_product_ids={125: {10}, 126: {10}},
    )
    assert cls.status == "contested"
    assert cls.reason == REASON_COMPETES_CROSS_PERIOD


def test_c5_no_shipment_indeterminate_visible():
    cls = classify_po_competition(
        po_number_norm="PONONE",
        claiming_cases=[
            {"case_id": 1, "bu": "NB", "period_key": "25Q2"},
            {"case_id": 2, "bu": "NR", "period_key": "25Q2"},
        ],
        ship_product_bu={},
        case_product_ids={1: {10}, 2: {20}},
    )
    assert cls.status == "indeterminate"
    assert cls.reason == REASON_INDETERMINATE_NO_SHIPMENT


def test_c6_flag_not_block_annotation():
    props = [
        {"case_id": 1, "po_number_norm": "POSAME", "proposal_key": "1:0:POSAME"},
        {"case_id": 2, "po_number_norm": "POSAME", "proposal_key": "2:0:POSAME"},
    ]
    classifications = classify_proposals_competition(
        props,
        case_meta={
            1: {"bu": "NB", "inferred_period_start": date(2026, 4, 1), "period_label": "2026 Q2"},
            2: {"bu": "NB", "inferred_period_start": date(2026, 4, 1), "period_label": "2026 Q2"},
        },
        case_product_ids={1: {10}, 2: {10}},
        ship_products_by_po_norm={"POSAME": {10: "NB"}},
    )
    annotate_proposals_with_competition(props, classifications)
    for p in props:
        assert p["competition"]["status"] == "contested"
        assert p["competition"]["blocks_apply"] is False


def test_cross_period_beats_multi_bu_ship():
    """Different periods are contested even when shipment shows multiple BUs."""
    cls = classify_po_competition(
        po_number_norm="POBOTH",
        claiming_cases=[
            {"case_id": 1, "bu": "NB", "period_key": "25Q2"},
            {"case_id": 2, "bu": "NR", "period_key": "25Q3"},
        ],
        ship_product_bu={10: "NB", 20: "NR"},
        case_product_ids={1: {10}, 2: {20}},
    )
    assert cls.status == "contested"
    assert cls.reason == REASON_COMPETES_CROSS_PERIOD


def test_multi_bu_without_product_overlap_is_contested():
    """Cases claim different BUs but lineup products do not overlap shipped BU products."""
    cls = classify_po_competition(
        po_number_norm="PONOOV",
        claiming_cases=[
            {"case_id": 1, "bu": "NB", "period_key": "25Q2"},
            {"case_id": 2, "bu": "NR", "period_key": "25Q2"},
        ],
        ship_product_bu={10: "NB", 20: "NR"},
        case_product_ids={1: {99}, 2: {98}},  # no overlap with ship products
    )
    assert cls.status == "contested"
    assert cls.reason == REASON_COMPETES_SAME_BU_SAME_PERIOD
