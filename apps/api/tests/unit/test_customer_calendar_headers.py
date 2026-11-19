"""Header matching for saved calendar mappings (review item B1). No database, no file system.

One normaliser (``normalize_header``) decides whether a saved alias and a file header are the same
column, so a saved mapping can never read a different column from the one the user selected. The
web editor keeps an identical normaliser (``calendarMapping.ts``); ``NORMALISE_CASES`` is repeated
in its test so the two cannot drift apart unnoticed.
"""

from __future__ import annotations

from datetime import date

from app.services.cpor.customer_calendar.parser import parse_calendar_grid
from app.services.cpor.customer_calendar.profiles import (
    default_calendar_profile,
    normalize_header,
    validate_profile,
)

NORMALISE_CASES = [
    ("Start", "start"),
    ("  Event   NAME ", "event name"),
    ("START DATE", "start date"),
    ("End\tDate", "end date"),
    ("", ""),
    (None, ""),
]


def _profile(column_map):
    p = default_calendar_profile()
    p["column_map_json"] = column_map
    return p


def test_normalize_header_cases():
    for raw, want in NORMALISE_CASES:
        assert normalize_header(raw) == want


def test_saved_alias_matches_a_differently_cased_and_spaced_header():
    grid = [
        ["Name", "  new   START "],
        ["Promo", "2026-03-01"],
    ]
    out = parse_calendar_grid(grid, _profile({"name": ["name"], "start_date": ["New Start"]}))
    assert out["ok"] is True
    assert out["mapped_columns"]["start_date"] == "  new   START "
    assert out["events"][0]["start_date"] == date(2026, 3, 1)


def test_editor_result_reads_the_selected_column_not_a_case_variant():
    """Headers ``Name,start,New Start``; the user selects ``New Start`` as the start date.

    The editor drops the alias that matches ``start`` (case-insensitively) and saves ``New Start``,
    so the parser reads the selected column.
    """
    grid = [["Name", "start", "New Start"], ["Promo", "2026-01-01", "2026-03-01"]]
    saved = _profile({"name": ["Name"], "start_date": ["New Start"]})
    out = parse_calendar_grid(grid, saved)
    assert out["mapped_columns"]["start_date"] == "New Start"
    assert out["events"][0]["start_date"] == date(2026, 3, 1)


def test_two_columns_with_the_same_normalised_header_are_ambiguous_not_guessed():
    grid = [["Name", "Start", "start"], ["Promo", "2026-01-01", "2026-03-01"]]
    out = parse_calendar_grid(grid, default_calendar_profile())
    assert out["ok"] is False
    assert out["events"] == []
    assert [e["code"] for e in out["blocking_errors"]] == ["ambiguous_start_date_column"]
    assert "Start" in out["blocking_errors"][0]["message"]


def test_ambiguity_in_an_optional_column_is_also_blocking():
    grid = [
        ["Name", "Start", "Kind", "KIND"],
        ["Promo", "2026-01-01", "campaign", "pillar"],
    ]
    out = parse_calendar_grid(grid, default_calendar_profile())
    assert [e["code"] for e in out["blocking_errors"]] == ["ambiguous_kind_column"]


def test_unrelated_duplicate_headers_do_not_block():
    grid = [["Name", "Start", "Notes", "notes"], ["Promo", "2026-01-01", "a", "b"]]
    out = parse_calendar_grid(grid, default_calendar_profile())
    assert out["ok"] is True


def test_validate_profile_rejects_one_header_mapped_to_two_fields():
    bad = _profile({"name": ["Name"], "start_date": ["Start"], "end_date": ["  START "]})
    problems = validate_profile(bad)
    assert any("start" in p.lower() and "more than one field" in p for p in problems)


def test_validate_profile_allows_repeated_aliases_inside_one_field():
    ok = _profile({"name": ["Name", "name"], "start_date": ["Start"]})
    assert validate_profile(ok) == []
