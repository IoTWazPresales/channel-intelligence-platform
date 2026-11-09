"""N-0118 review NB1/NB3 helpers in the customer sell-through apply (no database)."""

from __future__ import annotations

import sys

import pytest
from sqlalchemy import column
from sqlalchemy.dialects import postgresql

from app.services.imports import customer_sell_through_apply as apply_mod


def test_shared_whitespace_set_is_exactly_what_python_strip_removes() -> None:
    expected = {chr(c) for c in range(sys.maxunicode + 1) if chr(c).isspace()}
    assert set(apply_mod._PY_WHITESPACE) == expected
    assert len(apply_mod._PY_WHITESPACE) == len(expected)  # no character listed twice
    assert "\x00" not in apply_mod._PY_WHITESPACE


@pytest.mark.parametrize("label", [None, "", " ", "\t", "\u00a0", "\u3000 ", "S1", " S1 ", "\u200b"])
def test_python_site_test_uses_strip(label) -> None:
    line = type("L", (), {"site_label": label, "raw_location_token": None, "resolved_location_id": None})()
    assert apply_mod._line_names_site(line) == bool(str(label or "").strip())


def test_chunks_are_distinct_sorted_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apply_mod, "_LOOKUP_CHUNK_SIZE", 2)
    assert list(apply_mod._chunks([5, 3, 1, 3, 4])) == [[1, 3], [4, 5]]
    assert list(apply_mod._chunks(["b", "a", "c"])) == [["a", "b"], ["c"]]
    assert list(apply_mod._chunks([])) == []
    monkeypatch.setattr(apply_mod, "_LOOKUP_CHUNK_SIZE", 0)
    assert list(apply_mod._chunks([2, 1])) == [[1], [2]]


def test_default_lookup_chunk_stays_far_below_the_bind_limit() -> None:
    assert 0 < apply_mod._LOOKUP_CHUNK_SIZE <= 65535 // 4


def test_site_text_present_binds_the_whitespace_set() -> None:
    compiled = apply_mod._site_text_present(column("site_label")).compile(dialect=postgresql.dialect())
    assert "btrim(coalesce(site_label" in str(compiled)
    assert apply_mod._PY_WHITESPACE in compiled.params.values()
