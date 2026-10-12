"""Budget ledger sums. No database."""

from app.services.budget_ledger import (
    annotate_buckets,
    attach_caps,
    balances_from_amounts,
    current_cap,
    include_in_view,
    plan_transfer,
    position_with_pending,
)


def test_balances_net_commit_consume_and_cancel():
    settled = balances_from_amounts(
        [
            ("reserve", 200),
            ("commit", 100),
            ("consume", 80),
            ("release", 20),
            ("paid", 50),
        ]
    )
    assert settled["consumed"] == 80
    assert settled["remaining"] == 120
    assert settled["paid"] == 50

    cancelled = balances_from_amounts([("commit", 100), ("release", 100)])
    assert cancelled["pending_headroom_used"] == 0

    historical = balances_from_amounts([("consume", 1320000)])
    assert historical["consumed"] == 1320000
    assert historical["pending_headroom_used"] == 1320000


def test_pending_does_not_reduce_remaining_and_cap_stays_empty():
    ledger = [
        {
            "product_line": "NB",
            "landed_quarter": "2026Q2",
            **balances_from_amounts([("consume", 80)]),
        }
    ]
    rows = position_with_pending(ledger, [("NB", "2026Q2", 25), ("NR", "2026Q1", 10)])
    by_key = {(row["product_line"], row["landed_quarter"]): row for row in rows}
    assert by_key[("NB", "2026Q2")]["pending"] == 25
    assert by_key[("NB", "2026Q2")]["remaining"] == -80
    assert by_key[("NB", "2026Q2")]["cap"] is None
    assert by_key[("NR", "2026Q1")]["pending"] == 10
    assert by_key[("NR", "2026Q1")]["remaining"] == 0
    assert by_key[("NR", "2026Q1")]["cap"] is None


def test_unplanned_and_unknown_quarter_are_labels_not_new_amounts():
    rows = annotate_buckets(
        [
            {
                "product_line": "NB",
                "landed_quarter": "",
                "reserved": 0,
                "consumed": 10,
                "remaining": -10,
                "pending": 0,
                "cap": None,
            },
            {
                "product_line": "",
                "landed_quarter": "2026Q2",
                "reserved": 20,
                "consumed": 5,
                "remaining": 15,
                "pending": 0,
                "cap": None,
            },
        ]
    )
    assert rows[0]["quarter_label"] == "Unknown quarter"
    assert rows[0]["bucket"] == "unplanned"
    assert rows[0]["remaining"] == -10
    assert rows[1]["line_label"] == "No product line"
    assert rows[1]["bucket"] == "planned"
    assert include_in_view(None, "campaign") is True
    assert include_in_view("historical_import", "campaign") is True
    assert include_in_view("non_campaign", "campaign") is False
    assert include_in_view("non_campaign", "non_campaign") is True
    assert include_in_view("campaign", "non_campaign") is False


def test_cap_does_not_change_remaining_and_latest_clears():
    settled = balances_from_amounts([("consume", 80), ("cap", 50)])
    assert settled["remaining"] == -80
    assert settled["consumed"] == 80
    assert "cap" not in settled
    assert current_cap([100, None]) is None
    assert current_cap([100, 40]) == 40.0
    rows = attach_caps(
        [
            {
                "product_line": "NB",
                "landed_quarter": "2026Q2",
                **balances_from_amounts([("consume", 80)]),
                "pending": 25,
                "cap": None,
            }
        ],
        [("NB", "2026Q2", 50), ("NR", "2026Q1", 10)],
    )
    by_key = {(row["product_line"], row["landed_quarter"]): row for row in rows}
    assert by_key[("NB", "2026Q2")]["remaining"] == -80
    assert by_key[("NB", "2026Q2")]["pending"] == 25
    assert by_key[("NB", "2026Q2")]["cap"] == 50
    assert by_key[("NB", "2026Q2")]["over_cap"] is True
    assert by_key[("NR", "2026Q1")]["cap"] == 10
    assert by_key[("NR", "2026Q1")]["over_cap"] is False
    assert by_key[("NR", "2026Q1")]["remaining"] == 0


def test_transfer_pair_sums_to_zero_and_warns_when_over_remaining():
    refused = plan_transfer(
        amount=50,
        source=("NB", "2026Q2"),
        dest=("NR", "2026Q2"),
        source_remaining=10,
        confirm_over=False,
    )
    assert refused["needs_confirm"] is True
    assert refused["entries"] == []

    moved = plan_transfer(
        amount=50,
        source=("NB", "2026Q2"),
        dest=("NR", "2026Q2"),
        source_remaining=10,
        confirm_over=True,
    )
    assert moved["needs_confirm"] is False
    assert moved["over_remaining"] is True
    assert sum(entry["amount_usd"] for entry in moved["entries"]) == 0
    combined = balances_from_amounts(
        [("reserve", 10)] + [(entry["entry_type"], entry["amount_usd"]) for entry in moved["entries"]]
    )
    assert combined["remaining"] == 10
    source_only = balances_from_amounts([("reserve", 10), ("transfer", moved["entries"][0]["amount_usd"])])
    assert source_only["remaining"] == -40

    try:
        plan_transfer(
            amount=10,
            source=("NB", "2026Q2"),
            dest=("NB", "2026Q2"),
            source_remaining=10,
            confirm_over=True,
        )
    except ValueError as exc:
        assert "different" in str(exc)
    else:
        raise AssertionError("same cell must be refused")
