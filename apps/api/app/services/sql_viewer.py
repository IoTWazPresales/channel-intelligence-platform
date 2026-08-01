"""P3-6 SQL viewer — allow only read-only SELECT/WITH/EXPLAIN/SHOW statements."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_ROW_CAP = 200
MAX_ROW_CAP = 1000
DEFAULT_TIMEOUT_MS = 5_000
MAX_TIMEOUT_MS = 30_000

_COMMENT_LINE = re.compile(r"--[^\n]*")
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_FORBIDDEN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|MERGE|UPSERT|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"COPY|CALL|EXECUTE|VACUUM|REINDEX|CLUSTER|LOCK|NOTIFY|LISTEN|UNLISTEN|LOAD|"
    r"PREPARE|DEALLOCATE|DISCARD|REASSIGN|IMPORT|EXPORT|SECURITY|OWNER\s+TO|"
    r"SET\s+ROLE|SET\s+SESSION|RESET|REFRESH\s+MATERIALIZED|"
    r"EXPLAIN\s+ANALYZE|DO\b"
    r")\b",
    re.IGNORECASE,
)


class SqlViewerRefused(ValueError):
    """SQL rejected by the read-only gate."""


@dataclass
class SqlViewerResult:
    status: str  # ok | refused | error | timeout
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    message: str | None = None
    sql_text: str = ""


def strip_sql_comments(sql: str) -> str:
    no_block = _COMMENT_BLOCK.sub(" ", sql or "")
    no_line = _COMMENT_LINE.sub(" ", no_block)
    return re.sub(r"\s+", " ", no_line).strip()


def assert_readonly_sql(sql: str) -> str:
    cleaned = strip_sql_comments(sql)
    if not cleaned:
        raise SqlViewerRefused("Empty SQL")
    if ";" in cleaned.rstrip(";"):
        raise SqlViewerRefused("Single statement only (no multiple statements)")
    cleaned = cleaned.rstrip(";").strip()
    if _FORBIDDEN.search(cleaned):
        raise SqlViewerRefused(
            "Only SELECT / WITH / EXPLAIN (no ANALYZE) / SHOW are allowed — writes and DDL are blocked"
        )
    first = cleaned.split(None, 1)[0].upper()
    if first not in ("SELECT", "WITH", "EXPLAIN", "SHOW", "TABLE"):
        raise SqlViewerRefused(
            f"Statement must start with SELECT, WITH, EXPLAIN, SHOW, or TABLE — got {first}"
        )
    return cleaned


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date, dt_time, UUID)):
        return str(v)
    if isinstance(v, (bytes, memoryview)):
        return bytes(v).hex()
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return str(v)


def clamp_row_cap(raw: int | None) -> int:
    if raw is None:
        return DEFAULT_ROW_CAP
    return max(1, min(int(raw), MAX_ROW_CAP))


def clamp_timeout_ms(raw: int | None) -> int:
    if raw is None:
        return DEFAULT_TIMEOUT_MS
    return max(500, min(int(raw), MAX_TIMEOUT_MS))


def execute_readonly_sql(
    session: Session,
    *,
    sql: str,
    row_cap: int | None = None,
    timeout_ms: int | None = None,
) -> SqlViewerResult:
    """Run a gated read-only statement inside READ ONLY + statement_timeout."""
    started = time.perf_counter()
    cap = clamp_row_cap(row_cap)
    timeout = clamp_timeout_ms(timeout_ms)
    try:
        cleaned = assert_readonly_sql(sql)
    except SqlViewerRefused as e:
        return SqlViewerResult(
            status="refused",
            columns=[],
            rows=[],
            row_count=0,
            truncated=False,
            duration_ms=int((time.perf_counter() - started) * 1000),
            message=str(e),
            sql_text=(sql or "")[:4000],
        )

    bind = session.get_bind()
    truncated = False
    columns: list[str] = []
    rows_out: list[list[Any]] = []
    try:
        with bind.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text("SET TRANSACTION READ ONLY"))
                conn.execute(text(f"SET LOCAL statement_timeout = {int(timeout)}"))
                result = conn.execute(text(cleaned))
                if result.returns_rows:
                    columns = list(result.keys())
                    fetched = result.fetchmany(cap + 1)
                    if len(fetched) > cap:
                        truncated = True
                        fetched = fetched[:cap]
                    rows_out = [[_jsonable(c) for c in row] for row in fetched]
                trans.commit()
            except Exception:
                trans.rollback()
                raise
        duration_ms = int((time.perf_counter() - started) * 1000)
        return SqlViewerResult(
            status="ok",
            columns=columns,
            rows=rows_out,
            row_count=len(rows_out),
            truncated=truncated,
            duration_ms=duration_ms,
            message="truncated at row_cap" if truncated else None,
            sql_text=cleaned[:4000],
        )
    except Exception as e:  # noqa: BLE001 — surface as viewer error/timeout
        duration_ms = int((time.perf_counter() - started) * 1000)
        msg = str(e)
        status = "timeout" if "statement timeout" in msg.lower() or "canceling statement" in msg.lower() else "error"
        return SqlViewerResult(
            status=status,
            columns=[],
            rows=[],
            row_count=0,
            truncated=False,
            duration_ms=duration_ms,
            message=msg[:1000],
            sql_text=cleaned[:4000],
        )


def list_public_tables(session: Session, *, limit: int = 200) -> list[dict[str, Any]]:
    sql = """
    SELECT table_schema, table_name, table_type
    FROM information_schema.tables
    WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY table_schema, table_name
    LIMIT :lim
    """
    rows = session.execute(text(sql), {"lim": int(limit)}).mappings().all()
    return [dict(r) for r in rows]
