"""Unit tests for BACKLOG-093 promo load bucket classification (no DB)."""

from __future__ import annotations

from app.services.cpor.promo_load_recon import _classify_line


def test_missing_load():
    assert (
        _classify_line(
            cst_in_window_units=0,
            cst_in_window_price_wtd=None,
            cst_near_miss_units=0,
            expected_price=100.0,
            price_tol=0.02,
        )
        == "missing_load"
    )


def test_wrong_window():
    assert (
        _classify_line(
            cst_in_window_units=0,
            cst_in_window_price_wtd=None,
            cst_near_miss_units=5,
            expected_price=100.0,
            price_tol=0.02,
        )
        == "wrong_window"
    )


def test_wrong_price():
    assert (
        _classify_line(
            cst_in_window_units=10,
            cst_in_window_price_wtd=120.0,
            cst_near_miss_units=0,
            expected_price=100.0,
            price_tol=0.02,
        )
        == "wrong_price"
    )


def test_price_unknown():
    assert (
        _classify_line(
            cst_in_window_units=10,
            cst_in_window_price_wtd=None,
            cst_near_miss_units=0,
            expected_price=100.0,
            price_tol=0.02,
        )
        == "price_unknown"
    )


def test_ok_within_tol():
    assert (
        _classify_line(
            cst_in_window_units=10,
            cst_in_window_price_wtd=101.0,
            cst_near_miss_units=0,
            expected_price=100.0,
            price_tol=0.02,
        )
        == "ok"
    )
