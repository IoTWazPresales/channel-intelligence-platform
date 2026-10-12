"""Budget ledger sums. No database."""

from app.services.budget_ledger import balances_from_amounts


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
