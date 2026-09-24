"""N-0050 / BACKLOG-137 — cpor_case_line week-aligned windows (D-058).

Unit tests (no DB) for the Mon–Sun week helpers and the line-window claim rollup,
plus a cip_test-only schema test (skipped on any other database; always rolled back).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models.cpor import CporCaseLine
from app.services.cpor import settlement as st
from app.services.cpor.line_window import (
    FLAG_WINDOW_WEEK_STRADDLE,
    default_line_window,
    effective_line_window,
    is_week_aligned,
    line_window_info,
    straddle_weeks,
)

MON = date(2026, 1, 5)  # Monday
SUN = date(2026, 1, 18)  # Sunday, two weeks later


def test_week_alignment_is_monday_to_sunday() -> None:
    assert MON.weekday() == 0 and SUN.weekday() == 6
    assert is_week_aligned(MON, SUN)
    assert not is_week_aligned(date(2026, 1, 1), SUN)  # Thursday start
    assert straddle_weeks(MON, SUN) == []
    # Thu 1 Jan .. Wed 14 Jan: both boundary weeks are cut mid-week
    assert straddle_weeks(date(2026, 1, 1), date(2026, 1, 14)) == [date(2025, 12, 29), date(2026, 1, 12)]
    # start and end inside the same week: one straddled week, listed once
    assert straddle_weeks(date(2026, 1, 6), date(2026, 1, 8)) == [MON]


def test_default_and_effective_window_fall_back_to_case() -> None:
    case = SimpleNamespace(window_start=date(2026, 1, 1), window_end=date(2026, 1, 31))
    assert default_line_window(case) == (date(2026, 1, 1), date(2026, 1, 31))
    no_window = SimpleNamespace(product_id=1)
    assert effective_line_window(no_window, case) == (date(2026, 1, 1), date(2026, 1, 31))
    own = SimpleNamespace(window_start=MON, window_end=SUN)
    assert effective_line_window(own, case) == (MON, SUN)
    info = line_window_info(no_window, case)
    assert info["week_aligned"] is False
    assert info["straddle_weeks"] == ["2025-12-29", "2026-01-26"]


def test_model_grain_includes_window_start() -> None:
    uq = next(c for c in CporCaseLine.__table__.constraints if c.name == "uq_cpor_case_line_grain")
    assert [c.name for c in uq.columns] == ["case_id", "product_id", "distributor_id", "pod_quarter", "window_start"]
    assert CporCaseLine.__table__.c.window_start.nullable is False
    assert CporCaseLine.__table__.c.window_end.nullable is False


def test_migration_follows_0022_single_head() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert script.get_heads() == ["20260924_0023"]
    assert script.get_revision("20260924_0023").down_revision == "20260906_0022"


def _claim(pid: int, d: date, units: float, raw: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        case_id=1, product_id=pid, sale_date=d, units=units, source_model_token="A", raw_source_row=raw or {}
    )


def _run_rollup(monkeypatch, case, lines, claims):
    session = MagicMock()
    session.get.return_value = case
    session.scalars.side_effect = [
        MagicMock(all=MagicMock(return_value=claims)),
        MagicMock(all=MagicMock(return_value=lines)),
    ]
    monkeypatch.setattr(st, "recompute_case_line", lambda *a, **k: None)
    return st.rollup_result_qty_from_claims(session, 1)


def test_rollup_splits_claims_by_line_window_without_prorating(monkeypatch) -> None:
    # Superseded line: Mon 5 Jan .. Sun 11 Jan; successor Mon 12 Jan .. Sun 18 Jan (D-058 shape).
    case = SimpleNamespace(id=1, window_start=MON, window_end=SUN, customer_id=5, status="ended")
    old = SimpleNamespace(id=1, case_id=1, product_id=100, result_qty=None,
                          window_start=MON, window_end=date(2026, 1, 11))
    new = SimpleNamespace(id=2, case_id=1, product_id=100, result_qty=None,
                          window_start=date(2026, 1, 12), window_end=SUN)
    claims = [
        _claim(100, date(2026, 1, 7), 3),
        _claim(100, date(2026, 1, 11), 2),  # last day of old window
        _claim(100, date(2026, 1, 12), 5),  # first day of new window
        _claim(100, date(2026, 1, 20), 7),  # after case end: neither
    ]
    out = _run_rollup(monkeypatch, case, [old, new], claims)
    assert old.result_qty == 5.0
    assert new.result_qty == 5.0
    assert out["lines_updated"] == 2
    assert out["window_week_straddle_lines"] == 0
    assert out["override_claim_units_unplaced"] == 0.0


def test_rollup_flags_mid_week_boundary_and_counts_whole_days(monkeypatch) -> None:
    # Case window Thu 1 Jan .. Sat 31 Jan (non-aligned, as on most cip cases): flag, keep exact dates.
    case = SimpleNamespace(id=1, window_start=date(2026, 1, 1), window_end=date(2026, 1, 31),
                           customer_id=5, status="ended")
    line = SimpleNamespace(id=9, case_id=1, product_id=100, result_qty=None,
                           window_start=date(2026, 1, 1), window_end=date(2026, 1, 31))
    claims = [_claim(100, date(2025, 12, 31), 4), _claim(100, date(2026, 1, 1), 6), _claim(100, date(2026, 2, 1), 1)]
    out = _run_rollup(monkeypatch, case, [line], claims)
    assert line.result_qty == 6.0  # 31 Dec and 1 Feb are outside; nothing pro-rated
    assert out["window_week_straddle_lines"] == 1
    flag = out["window_flags"][0]
    assert flag["flag"] == FLAG_WINDOW_WEEK_STRADDLE
    assert flag["straddle_weeks"] == ["2025-12-29", "2026-01-26"]


def test_override_claim_single_window_counts_multi_window_unplaced(monkeypatch) -> None:
    override = {"_cpor_flags": {"include_out_of_window_override": True}}
    case = SimpleNamespace(id=1, window_start=MON, window_end=SUN, customer_id=5, status="ended")

    single = SimpleNamespace(id=1, case_id=1, product_id=100, result_qty=None, window_start=MON, window_end=SUN)
    out = _run_rollup(monkeypatch, case, [single], [_claim(100, date(2026, 1, 25), 4, override)])
    assert single.result_qty == 4.0
    assert out["override_claim_units_unplaced"] == 0.0

    old = SimpleNamespace(id=1, case_id=1, product_id=100, result_qty=None,
                          window_start=MON, window_end=date(2026, 1, 11))
    new = SimpleNamespace(id=2, case_id=1, product_id=100, result_qty=None,
                          window_start=date(2026, 1, 12), window_end=SUN)
    out = _run_rollup(monkeypatch, case, [old, new], [_claim(100, date(2026, 1, 25), 4, override)])
    assert old.result_qty == 0.0 and new.result_qty == 0.0
    assert out["override_claim_units_unplaced"] == 4.0


# --- cip_test only: schema + follow-case-window -------------------------------------------


@pytest.fixture()
def cip_test_conn():
    from app.core.config import get_settings

    get_settings.cache_clear()
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        pytest.skip(f"schema test runs on cip_test only (current_database()={db})")
    has = conn.execute(
        text(
            "select count(*) from information_schema.columns where table_schema = 'public' "
            "and table_name = 'cpor_case_line' and column_name in ('window_start', 'window_end')"
        )
    ).scalar_one()
    if has != 2:
        conn.close()
        pytest.skip("cip_test not at 20260924_0023")
    conn.rollback()  # end the autobegun read; the test body runs in one rolled-back transaction
    tx = conn.begin()
    try:
        yield conn
    finally:
        tx.rollback()
        conn.close()
        eng.dispose()


_INSERT = text(
    "insert into cpor_case_line (case_id, product_id, distributor_id, pod_quarter, srp, vat_rate, "
    "dealer_margin_pct, margin_source, estimate_qty, window_start, window_end) "
    "values (:case_id, :product_id, :distributor_id, 'N0050-Q', 100, 0.15, 0.1, 'test', 0, :ws, :we)"
)


def test_db_grain_holds_two_windows_rejects_duplicate_and_inverted(cip_test_conn) -> None:
    conn = cip_test_conn
    row = conn.execute(
        text("select l.case_id, l.product_id, l.distributor_id from cpor_case_line l order by l.id limit 1")
    ).first()
    if row is None:
        pytest.skip("cip_test has no cpor_case_line fixture row")
    key = {"case_id": row[0], "product_id": row[1], "distributor_id": row[2]}
    conn.execute(_INSERT, {**key, "ws": MON, "we": date(2026, 1, 11)})
    conn.execute(_INSERT, {**key, "ws": date(2026, 1, 12), "we": SUN})  # successor window stores
    sp = conn.begin_nested()
    with pytest.raises(IntegrityError):
        conn.execute(_INSERT, {**key, "ws": MON, "we": SUN})  # same window_start: grain conflict
    sp.rollback()
    sp = conn.begin_nested()
    with pytest.raises(IntegrityError):
        conn.execute(_INSERT, {**key, "ws": date(2026, 2, 2), "we": date(2026, 2, 1)})  # end < start
    sp.rollback()
    n = conn.execute(
        text("select count(*) from cpor_case_line where pod_quarter = 'N0050-Q' and case_id = :c"), {"c": key["case_id"]}
    ).scalar_one()
    assert n == 2


def test_db_follow_case_window_moves_only_lines_on_case_window(cip_test_conn) -> None:
    from sqlalchemy.orm import Session

    from app.services.cpor.line_window import follow_case_window

    conn = cip_test_conn
    row = conn.execute(
        text(
            "select l.case_id, l.product_id, l.distributor_id, c.window_start, c.window_end "
            "from cpor_case_line l join cpor_case c on c.id = l.case_id order by l.id limit 1"
        )
    ).first()
    if row is None:
        pytest.skip("cip_test has no cpor_case_line fixture row")
    case_id, pid, did, cws, cwe = row
    key = {"case_id": case_id, "product_id": pid, "distributor_id": did}
    conn.execute(_INSERT, {**key, "ws": MON, "we": SUN})  # own (non-case) window: must not move
    on_case = conn.execute(
        text("select count(*) from cpor_case_line where case_id = :c and window_start = :ws and window_end = :we"),
        {"c": case_id, "ws": cws, "we": cwe},
    ).scalar_one()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    moved = follow_case_window(
        session, case_id, old_start=cws, old_end=cwe, new_start=date(2030, 1, 7), new_end=date(2030, 2, 3)
    )
    session.flush()
    assert moved == on_case
    own = conn.execute(
        text("select window_start from cpor_case_line where case_id = :c and pod_quarter = 'N0050-Q'"), {"c": case_id}
    ).scalar_one()
    assert own == MON
    session.close()
