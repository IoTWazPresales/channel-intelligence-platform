"""Budget ledger sums. No database."""

from app.services.budget_ledger import balances_from_amounts, position_with_pending


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
