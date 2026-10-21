"""Sell-through rows on Attention (Warren 2026-10-19)."""

from app.services.brief_signals import sell_through_signals

ST = {
    "restock": 13, "out_of_stock": 10, "needs_replen": 3,
    "slowing": 45, "dropped": 1, "aged": 24, "stopped": 20,
    "customers_missing": ["Computer Mania", "Evetech", "Game", "Hifi", "Makro"],
    "has_data": True,
}


def test_rows_for_restock_missing_and_slowing():
    rows = sell_through_signals(ST, slot_signal_shown=False)
    assert [r["id"] for r in rows] == ["cst_restock", "cst_reports_missing_window", "cst_slowing"]
    assert rows[0]["title"] == "13 SKUs at customers need restocking"
    assert rows[0]["detail"] == "10 out of stock while selling, 3 below their customer's cover"
    assert rows[1]["detail"] == "Computer Mania, Evetech, Game and 2 more"
    assert all(r["action_href"] == "/channel-intelligence" for r in rows)


def test_missing_reports_not_repeated_when_slot_signal_shows():
    ids = [r["id"] for r in sell_through_signals(ST, slot_signal_shown=True)]
    assert "cst_reports_missing_window" not in ids


def test_nothing_when_no_counts():
    assert sell_through_signals(None, slot_signal_shown=False) == []
    assert sell_through_signals({**ST, "restock": 0, "slowing": 0, "customers_missing": []}, slot_signal_shown=False) == []


def test_singular_wording():
    rows = sell_through_signals(
        {**ST, "restock": 1, "slowing": 1, "customers_missing": ["Pinnacle"]}, slot_signal_shown=False
    )
    assert [r["title"] for r in rows] == [
        "1 SKU at a customer needs restocking",
        "1 customer has sell-through missing in the last 13 weeks",
        "1 SKU at a customer is slowing or stuck",
    ]
    assert rows[1]["meta"] == "1 customer"
