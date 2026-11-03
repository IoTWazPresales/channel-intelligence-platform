"""Pure rules. No database and no tenant names."""

from app.services.store_dc.rules import (
    NO_HISTORY,
    inbound_leg,
    need_units,
    onward_leg,
    pattern_matches,
)


def test_cover_only_need_uses_the_fallback_target():
    result = need_units(rate=10, soh=20, target_weeks=6, lead_weeks=0)
    assert result["units"] == 40
    assert result["reason"] == "cover"


def test_median_is_used_only_at_the_sample_floor():
    ready = inbound_leg([14, 14, 14, 14, 14], 5)
    assert ready["median_days"] == 14
    assert ready["used_in_need"] is True
    assert ready["lead_time_weeks"] == 2
    with_lead = need_units(rate=10, soh=20, target_weeks=6, lead_weeks=ready["lead_time_weeks"])
    assert with_lead["units"] == 60

    short = inbound_leg([14, 14, 14, 14], 5)
    assert short["lead_time_label"] == NO_HISTORY
    assert short["used_in_need"] is False
    assert short["lead_time_weeks"] is None
    assert need_units(rate=10, soh=20, target_weeks=6, lead_weeks=0)["units"] == 40


def test_onward_leg_never_receives_inbound_days():
    inbound = inbound_leg([14, 14, 14, 14, 14], 5)
    onward = onward_leg()
    assert inbound["median_days"] == 14
    assert onward["median_days"] is None
    assert onward["lead_time_label"] == NO_HISTORY
    assert onward["history"] == "no history"
    assert onward["sample_count"] == 0
    assert onward["used_in_need"] is False


def test_pattern_is_a_full_string_match():
    assert pattern_matches("SDC-HUB-1", [r"^SDC-HUB-.+$"]) is True
    assert pattern_matches("note SDC-HUB-1", [r"^SDC-HUB-.+$"]) is False
    assert pattern_matches("SDC-HUB-1 extra", [r"SDC-HUB"]) is False


def test_negative_duration_is_dropped():
    leg = inbound_leg([-3, 14, 14, 14, 14, 14], 5)
    assert leg["sample_count"] == 5
    assert leg["min_days"] == 14
