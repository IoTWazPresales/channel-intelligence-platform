"""P3-6 SQL viewer gate — no DB required for refuse rules."""

from __future__ import annotations

import pytest

from app.services.sql_viewer import SqlViewerRefused, assert_readonly_sql, strip_sql_comments


def test_allows_select_with_and_show():
    assert assert_readonly_sql("SELECT 1").startswith("SELECT")
    assert assert_readonly_sql("WITH x AS (SELECT 1 AS n) SELECT * FROM x").upper().startswith("WITH")
    assert assert_readonly_sql("SHOW search_path").upper().startswith("SHOW")
    assert assert_readonly_sql("EXPLAIN SELECT 1").upper().startswith("EXPLAIN")


def test_strips_comments():
    cleaned = assert_readonly_sql("/* evil INSERT */ SELECT 1 -- update foo")
    assert cleaned.upper().startswith("SELECT")


def test_refuses_writes_and_ddl():
    for sql in [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET a=1",
        "DELETE FROM t",
        "DROP TABLE t",
        "ALTER TABLE t ADD COLUMN x int",
        "CREATE TABLE t(x int)",
        "TRUNCATE t",
        "SELECT 1; DELETE FROM t",
        "EXPLAIN ANALYZE SELECT 1",
        "DO $$ BEGIN END $$",
    ]:
        with pytest.raises(SqlViewerRefused):
            assert_readonly_sql(sql)


def test_strip_comments_helper():
    assert "INSERT" not in strip_sql_comments("SELECT /* INSERT */ 1").upper().replace("SELECT", "")
