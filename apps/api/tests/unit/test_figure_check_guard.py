"""Wave 2 figure_check.py: SQL screening, figure parsing and comparison. No database.

Runs under CIP_UNIT_TESTS_FORBID_DB=1 (tests/unit/conftest.py vetoes every connection).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify" / "figure_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("wave2_figure_check", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


fc = _load()


# --- SQL acceptance -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "select count(*) from fact_table",
        "  SELECT sum(units) FROM t WHERE period = %(period)s ;  ",
        "WITH x AS (SELECT 1 AS v) SELECT v FROM x",
        "(SELECT 1)",
        "-- leading comment\nSELECT 1 -- trailing",
        "/* block */ SELECT /* inner /* nested */ */ 2",
        "SELECT 'a--b' AS s",
        'SELECT "updated_at" FROM t',  # quoted identifier: not the word UPDATE
        "SELECT created_at, deleted FROM t",  # words that only contain a keyword
        "SELECT 1;;",
    ],
)
def test_accepts_single_select(sql: str) -> None:
    cleaned = fc.validate_select(sql)
    assert cleaned.lstrip("( ").upper().startswith(("SELECT", "WITH"))
    assert not cleaned.endswith(";")


@pytest.mark.parametrize(
    "sql, reason",
    [
        ("", "empty"),
        ("   -- only a comment", "empty"),
        ("SELECT 1; SELECT 2", "batch"),
        ("SELECT 1; DROP TABLE t", "batch"),
        ("SELECT 1 /* ; */; UPDATE t SET a = 1", "batch"),
        ("UPDATE t SET a = 1", "SELECT"),
        ("INSERT INTO t VALUES (1)", "SELECT"),
        ("DELETE FROM t", "SELECT"),
        ("TRUNCATE t", "SELECT"),
        ("EXPLAIN ANALYZE SELECT 1", "SELECT"),
        ("SHOW search_path", "SELECT"),
        ("SET default_transaction_read_only = off", "SELECT"),
        ("WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d", "DELETE"),
        ("WITH u AS (UPDATE t SET a = 1 RETURNING a) SELECT a FROM u", "UPDATE"),
        ("WITH m AS (MERGE INTO t USING s ON true WHEN MATCHED THEN DO NOTHING) SELECT 1", "MERGE"),
        ("SELECT * INTO new_table FROM t", "INTO"),
        ("SELECT 1 WHERE EXISTS (SELECT 1) -- \n; alter table t add c int", "batch"),
        ("select 1 from t where x = 'drop'", "DROP"),  # conservative: keywords refused anywhere
        ("SELECT set_config('default_transaction_read_only', 'off', false)", "set_config"),
        ("SELECT pg_terminate_backend(1)", "pg_terminate_backend"),
        ("SELECT nextval('s')", "nextval"),
        ("SELECT * FROM dblink('x', 'y') AS t(a int)", "dblink"),
        ("SELECT pg_sleep(100)", "pg_sleep"),
        ("SELECT $$x$$", "dollar"),
        ("SELECT 1 /* unterminated", "unterminated"),
        ("SELECT 'unterminated", "unterminated"),
        ("WITH x AS (VALUES (1)) TABLE x", "SELECT"),
        ("COPY (SELECT 1) TO STDOUT", "SELECT"),
        ("CALL p()", "SELECT"),
        ("DO $$BEGIN END$$", "SELECT"),
        ("GRANT SELECT ON t TO PUBLIC", "SELECT"),
        ("CREATE TABLE t AS SELECT 1", "SELECT"),
        ("ALTER TABLE t ADD c int", "SELECT"),
    ],
)
def test_refuses(sql: str, reason: str) -> None:
    with pytest.raises(fc.RefusedError) as exc:
        fc.validate_select(sql)
    message = str(exc.value).lower()
    hints = {
        "empty": "empty",
        "batch": "batch",
        "SELECT": "",
        "dollar": "dollar",
        "unterminated": "unterminated",
    }
    expected = hints.get(reason, reason.lower())
    assert expected in message


@pytest.mark.parametrize("word", fc.FORBIDDEN_KEYWORDS)
def test_every_forbidden_keyword_is_refused_inside_a_select(word: str) -> None:
    with pytest.raises(fc.RefusedError):
        fc.validate_select(f"SELECT 1 FROM t WHERE note = 'x' AND {word.lower()} = 1")


def test_strip_comments_keeps_literals() -> None:
    assert fc.strip_sql_comments("SELECT '--x' -- c\n").strip() == "SELECT '--x'"
    assert fc.strip_sql_comments("SELECT 'it''s' /* c */").strip() == "SELECT 'it''s'"


# --- figures and comparison -----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("1,234.5", Decimal("1234.5")),
        ("R 1 234 567", Decimal("1234567")),
        ("US$ 574.59", Decimal("574.59")),
        ("-12", Decimal("-12")),
        ("(3.5)", Decimal("-3.5")),
        ("42%", Decimal("42")),
        (7, Decimal("7")),
        (2.5, Decimal("2.5")),
        (Decimal("0.10"), Decimal("0.10")),
        ("—", None),
        ("", None),
        (None, None),
        (True, None),
        (float("nan"), None),
    ],
)
def test_parse_figure(raw, expected) -> None:
    assert fc.parse_figure(raw) == expected


def test_tolerance_parsing() -> None:
    assert fc.parse_tolerance(None) == fc.Tolerance()
    assert fc.parse_tolerance(0.5).absolute == Decimal("0.5")
    assert fc.parse_tolerance("1%").relative == Decimal("0.01")
    assert fc.parse_tolerance("1%").describe() == "1%"
    for bad in (-1, "-2%", "abc", "x%"):
        with pytest.raises(fc.RefusedError):
            fc.parse_tolerance(bad)


def test_figures_match_maths() -> None:
    exact = fc.Tolerance()
    assert fc.figures_match(Decimal("10"), Decimal("10"), exact)
    assert not fc.figures_match(Decimal("10"), Decimal("10.01"), exact)
    absolute = fc.Tolerance(absolute=Decimal("0.5"))
    assert fc.figures_match(Decimal("10.5"), Decimal("10"), absolute)
    assert fc.figures_match(Decimal("9.5"), Decimal("10"), absolute)
    assert not fc.figures_match(Decimal("10.51"), Decimal("10"), absolute)
    relative = fc.parse_tolerance("1%")
    assert fc.figures_match(Decimal("1010"), Decimal("1000"), relative)
    assert not fc.figures_match(Decimal("1011"), Decimal("1000"), relative)
    assert fc.figures_match(Decimal("-990"), Decimal("-1000"), relative)
    assert fc.figures_match(Decimal("0"), Decimal("0"), relative)


def _check(**overrides):
    item = {
        "name": "units",
        "route": "/dashboards",
        "sql": "SELECT 1",
        "params": None,
        "expected": "1,000",
        "tolerance": 0,
    }
    item.update(overrides)
    return fc.load_checks([item])[0]


def test_evaluate_match_and_mismatch() -> None:
    hit = fc.evaluate(_check(), Decimal("1000"))
    assert hit.status == "match" and hit.difference == "0"
    miss = fc.evaluate(_check(), 999)
    assert miss.status == "mismatch" and miss.difference == "1"
    within = fc.evaluate(_check(tolerance="0.2%"), 999)
    assert within.status == "match"


def test_evaluate_missing_rows_and_non_numbers() -> None:
    assert fc.evaluate(_check(expected=None), 5).status == "missing_expected"
    assert fc.evaluate(_check(), None, row_count=0).status == "no_row"
    assert fc.evaluate(_check(), 1, row_count=2).status == "no_row"
    assert fc.evaluate(_check(), "n/a").status == "not_numeric"


def test_evaluate_uses_page_figures_when_expected_is_null() -> None:
    lines = [
        json.dumps({"name": "units", "viewport": "desktop", "value": 1000}),
        json.dumps({"name": "units", "viewport": "mobile", "value": 1000}),
        "",
    ]
    figures = fc.load_page_figures(lines)
    result = fc.evaluate(_check(expected=None), 1000, figures)
    assert result.status == "match" and result.expected_source == "page figures"
    split = fc.load_page_figures(
        [json.dumps({"name": "units", "value": 1}), json.dumps({"name": "units", "value": 2})]
    )
    assert fc.evaluate(_check(expected=None), 1, split).status == "page_inconsistent"


def test_load_checks_refuses_bad_input() -> None:
    with pytest.raises(fc.RefusedError):
        fc.load_checks([])
    with pytest.raises(fc.RefusedError):
        fc.load_checks([{"name": "a", "route": "/x", "sql": "DELETE FROM t"}])
    with pytest.raises(fc.RefusedError):
        fc.load_checks([{"name": "a", "route": "x", "sql": "SELECT 1"}])
    with pytest.raises(fc.RefusedError):
        fc.load_checks([{"name": "a", "route": "/x", "sql": "SELECT 1", "params": [1]}])
    dup = {"name": "a", "route": "/x", "sql": "SELECT 1"}
    with pytest.raises(fc.RefusedError):
        fc.load_checks([dup, dup])


def test_db_url_normalisation_and_redaction() -> None:
    assert fc.normalise_db_url("postgresql+psycopg://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert fc.normalise_db_url("postgresql://u@h/db") == "postgresql://u@h/db"
    assert fc.normalise_db_url("postgres://u@h/db") == "postgresql://u@h/db"
    for bad in ("", "postgresql+asyncpg://u@h/db", "sqlite:///x.db", "mysql://u@h/db"):
        with pytest.raises(fc.RefusedError):
            fc.normalise_db_url(bad)
    assert fc.redact_url("postgresql://user:secret@h/db") == "postgresql://user:***@h/db"


def test_outputs_markdown_and_json(tmp_path: Path) -> None:
    results = [fc.evaluate(_check(), 1000), fc.evaluate(_check(name="b|c"), 5)]
    md, js = fc.write_outputs(tmp_path, results, "some_db")
    text = md.read_text(encoding="utf-8")
    assert "| Check | Route | Status |" in text
    assert "b\\|c" in text and "1 of 2 figures match." in text
    payload = json.loads(js.read_text(encoding="utf-8"))
    assert payload["mismatches"] == 1 and payload["database"] == "some_db"


def test_main_refuses_bad_sql_before_connecting(tmp_path: Path) -> None:
    checks = tmp_path / "checks.json"
    checks.write_text(
        json.dumps([{"name": "a", "route": "/x", "sql": "SELECT 1; DROP TABLE t"}]),
        encoding="utf-8",
    )
    code = fc.main(
        [
            "--checks",
            str(checks),
            "--db-url",
            "postgresql://u@127.0.0.1:1/nothing",
            "--expect-db",
            "nothing",
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert not (tmp_path / "out").exists()


def test_main_requires_db_url_and_expect_db(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        fc.main(["--checks", "x.json", "--out", str(tmp_path)])
    with pytest.raises(SystemExit):
        fc.main(["--checks", "x.json", "--db-url", "postgresql://h/db", "--out", str(tmp_path)])
