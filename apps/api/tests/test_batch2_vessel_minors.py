"""GOV-008 minors on the vessel card: a pulled-in ETA is not "unchanged", and a vessel with no ETA is not drawn at 100%. Pure."""

from __future__ import annotations

from datetime import date

from app.services.shipping.on_the_water import build_vessels

from tests.test_on_the_water import AS_OF, CFG, _ln


def _vessel(**kw):
    return build_vessels([_ln(1, **kw)], as_of=AS_OF, report_date=date(2026, 10, 27), cfg=CFG)[0]


def test_a_pulled_in_eta_is_a_negative_shift_not_an_unchanged_eta():
    v = _vessel(first_eta=date(2026, 11, 9), port_eta=date(2026, 11, 5))
    assert v["eta_shift_days"] == -4  # before: the field did not exist, slip_days (clamped to 0) was all the card had
    assert v["slip_days"] == 0  # tiles and sorting keep the later-ETA figure
    assert v["history"]["first_eta"] == "2026-11-09" and v["history"]["current_eta"] == "2026-11-05"


def test_a_later_eta_and_an_unchanged_eta_keep_their_shift():
    assert _vessel(first_eta=date(2026, 10, 22), port_eta=date(2026, 11, 5))["eta_shift_days"] == 14
    assert _vessel(first_eta=date(2026, 10, 22), port_eta=date(2026, 11, 5))["slip_days"] == 14
    unchanged = _vessel(first_eta=date(2026, 11, 5), port_eta=date(2026, 11, 5))
    assert unchanged["eta_shift_days"] == 0 and unchanged["slip_days"] == 0


def test_the_largest_later_move_wins_over_a_pulled_in_line():
    lines = [_ln(1, first_eta=date(2026, 11, 9), port_eta=date(2026, 11, 5)), _ln(2, first_eta=date(2026, 11, 1), port_eta=date(2026, 11, 5))]
    v = build_vessels(lines, as_of=AS_OF, report_date=date(2026, 10, 27), cfg=CFG)[0]
    assert v["eta_shift_days"] == 4 and v["slip_days"] == 4


def test_a_vessel_with_no_eta_is_not_drawn_at_100_percent():
    no_eta = _vessel(port_eta=None)
    assert no_eta["eta"] is None and no_eta["position_known"] is False
    assert no_eta["pct"] == 0.0  # before: 100.0, as if it had arrived
    with_eta = _vessel()
    assert with_eta["position_known"] is True and 0.0 < with_eta["pct"] < 100.0


def test_a_vessel_with_no_eta_sits_at_the_start_of_its_lane_not_at_the_port():
    no_eta = _vessel(port_eta=None)
    with_eta = _vessel(port_eta=date(2026, 10, 29))  # one day from the port: at the far end
    assert (no_eta["x"], no_eta["y"]) != (with_eta["x"], with_eta["y"])
