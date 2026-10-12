"""Budget ledger sums. No database."""

from app.services.budget_ledger import (
    annotate_buckets,
    assemble_customer_position,
    attach_caps,
    balances_from_amounts,
    current_cap,
    case_ledger_from_rows,
    describe_payment_link_coverage,
    fold_customer_amounts,
    headroom_used_from_tagged,
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


def test_customer_quarter_sums_product_lines_and_skips_caps():
    grouped = fold_customer_amounts(
        [
            (7, "2026Q2", "consume", 30),
            (7, "2026Q2", "consume", 50),
            (7, "2026Q2", "cap", 10),
            (None, "2026Q2", "consume", 5),
        ]
    )
    rows = assemble_customer_position(
        grouped,
        [(7, "2026Q2", 12), (9, "2026Q1", 4)],
        {7: "Takealot"},
    )
    by_key = {(row["customer_id"], row["landed_quarter"]): row for row in rows}
    takealot = by_key[(7, "2026Q2")]
    assert takealot["consumed"] == 80
    assert takealot["remaining"] == -80
    assert takealot["pending"] == 12
    assert takealot["cap"] is None
    assert takealot["over_cap"] is False
    assert takealot["customer_label"] == "Takealot"
    assert takealot["bucket"] == "unplanned"
    assert by_key[(None, "2026Q2")]["customer_label"] == "No customer"
    assert by_key[(None, "2026Q2")]["consumed"] == 5
    unnamed = by_key[(9, "2026Q1")]
    assert unnamed["customer_label"] == "Unnamed customer"
    assert unnamed["pending"] == 4
    assert unnamed["remaining"] == 0
    assert unnamed["cap"] is None


def test_payment_link_coverage_is_a_count_not_a_paid_write():
    sentence = describe_payment_link_coverage(
        {
            "paid_rows": 2718,
            "paid_linked": 243,
            "evidence_rows": 3375,
            "linked_rows": 283,
            "ledger_paid_rows": 0,
        }
    )
    assert sentence == (
        "Payment link coverage: 243 of 2718 paid evidence rows are linked to a case. "
        "283 of 3375 evidence rows are linked. "
        "The Paid column has 0 ledger rows. Historical payments were not loaded."
    )
    empty = describe_payment_link_coverage(
        {
            "paid_rows": 0,
            "paid_linked": 0,
            "evidence_rows": 0,
            "linked_rows": 0,
            "ledger_paid_rows": 0,
        }
    )
    assert "0 of 0" in empty
    assert "were not loaded" in empty


def test_case_ledger_sums_commit_consume_and_usd_paid_only():
    totals = case_ledger_from_rows(
        [
            ("commit", 100),
            ("commit_adjust", 5),
            ("consume", 80),
            ("release", 25),
            ("paid", 40),
            ("paid", None),
            ("cap", 10),
        ]
    )
    assert totals["committed_usd"] == 105
    assert totals["consumed_usd"] == 80
    assert totals["paid_usd"] == 40
    assert totals["paid_row_count"] == 2


def test_campaign_draw_ignores_caps_non_campaign_and_a_cancelled_commitment():
    cancelled = headroom_used_from_tagged(
        [
            ("commit", 40, None),
            ("release", 40, None),
            ("consume", 90, "non_campaign"),
            ("reserve", 25, "non_campaign"),
            ("cap", 1000, "line_cap"),
        ]
    )
    assert cancelled == 0
    assert headroom_used_from_tagged([("commit", 12, "campaign")]) == 12
    assert headroom_used_from_tagged([("consume", 80, "historical_import"), ("cap", 5, "line_cap")]) == 80
