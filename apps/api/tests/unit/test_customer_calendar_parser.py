"""Mapped calendar parsing for the customer promotion calendar. No database, no file system."""

from __future__ import annotations

from datetime import date, datetime

from app.services.cpor.customer_calendar.parser import parse_calendar_csv, parse_calendar_grid
from app.services.cpor.customer_calendar.profiles import (
    default_calendar_profile,
    validate_profile,
)


def _profile(**over):
    p = default_calendar_profile()
    p.update(over)
    return p


def test_default_profile_maps_generic_headers_and_validates():
    p = default_calendar_profile()
    assert validate_profile(p) == []
    assert {"customer_token", "name", "kind", "start_date", "end_date"} <= set(p["column_map_json"])


def test_parses_rows_through_header_aliases_and_kind_map():
    grid = [
        ["Retailer", "Campaign Name", "Type", "Start", "End"],
        ["Acme", "Autumn push", "Campaign", date(2026, 3, 1), date(2026, 3, 14)],
        ["Acme", "Brand month", "PILLAR", datetime(2026, 4, 1, 0, 0), datetime(2026, 4, 30, 0, 0)],
        ["Acme", "Odd one", "mystery", "2026-05-01", "2026-05-02"],
    ]
    out = parse_calendar_grid(grid, default_calendar_profile())
    assert out["ok"] is True
    assert out["blocking_errors"] == []
    kinds = [e["kind"] for e in out["events"]]
    assert kinds == ["campaign", "pillar", "other"]
    first = out["events"][0]
    assert first["customer_token"] == "Acme"
    assert first["name"] == "Autumn push"
    assert first["start_date"] == date(2026, 3, 1)
    assert first["end_date"] == date(2026, 3, 14)
    assert first["row_number"] == 2
    assert out["events"][1]["start_date"] == date(2026, 4, 1)


def test_header_matching_ignores_case_and_spacing():
    grid = [
        ["  event   NAME ", "START DATE", "end date"],
        ["Promo", "2026-03-01", "2026-03-02"],
    ]
    out = parse_calendar_grid(grid, default_calendar_profile())
    assert out["ok"] is True
    assert out["events"][0]["name"] == "Promo"
    assert out["events"][0]["customer_token"] is None
    assert out["events"][0]["kind"] == "other"


def test_missing_end_date_defaults_to_start_day():
    grid = [["Name", "Start"], ["One day", "2026-03-01"]]
    out = parse_calendar_grid(grid, default_calendar_profile())
    assert out["events"][0]["end_date"] == date(2026, 3, 1)


def test_missing_required_column_is_a_blocking_error():
    grid = [["Name", "Colour"], ["x", "red"]]
    out = parse_calendar_grid(grid, default_calendar_profile())
    assert out["ok"] is False
    assert [e["code"] for e in out["blocking_errors"]] == ["missing_start_date_column"]
    assert out["events"] == []


def test_row_errors_are_reported_and_good_rows_still_parse():
    grid = [
        ["Name", "Start", "End"],
        ["Good", "2026-03-01", "2026-03-05"],
        ["", "2026-03-01", "2026-03-05"],
        ["No start", "", "2026-03-05"],
        ["Bad start", "not a date", "2026-03-05"],
        ["Backwards", "2026-03-10", "2026-03-05"],
        [None, None, None],
    ]
    out = parse_calendar_grid(grid, default_calendar_profile())
    assert [e["name"] for e in out["events"]] == ["Good"]
    codes = {(e["row"], e["code"]) for e in out["row_errors"]}
    assert codes == {
        (3, "missing_name"),
        (4, "missing_start_date"),
        (5, "bad_start_date"),
        (6, "end_before_start"),
    }
    assert out["ok"] is True  # row errors do not block; they are shown in the preview


def test_header_row_index_skips_title_rows():
    grid = [
        ["Calendar 2026"],
        [],
        ["Name", "Start", "End"],
        ["Promo", "2026-03-01", "2026-03-02"],
    ]
    out = parse_calendar_grid(grid, _profile(header_row_index=3))
    assert out["ok"] is True
    assert out["events"][0]["row_number"] == 4


def test_day_first_slash_dates():
    grid = [["Name", "Start", "End"], ["Promo", "01/03/2026", "15/03/2026"]]
    out = parse_calendar_grid(grid, default_calendar_profile())
    assert out["events"][0]["start_date"] == date(2026, 3, 1)
    assert out["events"][0]["end_date"] == date(2026, 3, 15)


def test_profile_value_map_and_aliases_are_data_not_code():
    prof = _profile(
        column_map_json={
            "name": ["Initiative"],
            "start_date": ["From"],
            "end_date": ["To"],
            "kind": ["Bucket"],
        },
        value_maps_json={"kind": {"always on": "pillar", "burst": "campaign"}},
    )
    grid = [["Initiative", "From", "To", "Bucket"], ["A", "2026-01-01", "2026-01-31", "Always On"]]
    out = parse_calendar_grid(grid, prof)
    assert out["events"][0]["kind"] == "pillar"


def test_raw_row_keeps_headers_and_json_safe_values():
    grid = [["Name", "Start", "End"], ["Promo", date(2026, 3, 1), date(2026, 3, 2)]]
    out = parse_calendar_grid(grid, default_calendar_profile())
    raw = out["events"][0]["raw_row"]
    assert raw["Name"] == "Promo"
    assert raw["Start"] == "2026-03-01"


def test_csv_bytes_parse_with_utf8_bom():
    data = ("﻿Name,Start,End,Kind\nSale,2026-03-01,2026-03-03,campaign\n").encode()
    out = parse_calendar_csv(data, default_calendar_profile())
    assert out["ok"] is True
    assert out["events"][0]["kind"] == "campaign"


def test_empty_file_is_blocking():
    out = parse_calendar_grid([], default_calendar_profile())
    assert out["ok"] is False
    assert out["blocking_errors"][0]["code"] == "empty_file"


def test_validate_profile_rejects_missing_fields_and_bad_kinds():
    bad = _profile(column_map_json={"name": ["Name"]}, header_row_index=0)
    problems = validate_profile(bad)
    assert any("start_date" in p for p in problems)
    assert any("header_row_index" in p for p in problems)
    bad_kind = _profile(value_maps_json={"kind": {"x": "banana"}})
    assert any("banana" in p for p in validate_profile(bad_kind))
