"""Wave 2 figure checks: compare figures shown on a page with read-only SQL on the same database.

Usage (from apps/api; see docs/audits/WAVE2_VERIFICATION_HARNESS.md):

    python scripts/verify/figure_check.py --checks checks.json --db-url <url> --expect-db <name>
        --out <dir> [--page-figures ../web/.tmp/wave2/figures.ndjson]

``checks.json`` is a JSON array of objects::

    {"name": str, "route": str, "sql": str, "params": {..} | null,
     "expected": number | str | null, "tolerance": number | "<n>%" | null, "selector": str?}

``expected`` is the figure read from the page. When it is null, the value captured by the
Playwright spec (``figures.ndjson``, written for checks that name a ``selector``) is used.
``params`` use psycopg named placeholders (``%(name)s``); with no params, ``%`` needs no escaping.
Each statement must return one row with one column: the database figure.

Safety:
- ``--db-url`` and ``--expect-db`` are required; there is no default database. The run stops
  before any check when ``current_database()`` differs from ``--expect-db``.
- The session is read-only three ways: libpq ``default_transaction_read_only=on`` at connect,
  ``SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY`` plus
  ``SET default_transaction_read_only``, and every check runs inside its own ``BEGIN READ ONLY``
  transaction that is always rolled back after ``transaction_read_only`` is confirmed ``on``.
- Every statement is screened before connecting: a single ``SELECT`` or ``WITH ... SELECT`` only,
  comments stripped, no ``;`` batches, and no write keyword or session-changing function anywhere
  as a word (string literals included, deliberately conservative).

Exit codes: 0 all figures match, 1 any mismatch or missing figure,
2 refused (input, SQL or database).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# Write statements (the Wave 2 list) plus SELECT ... INTO, which creates a table.
FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "TRUNCATE",
    "ALTER",
    "DROP",
    "CREATE",
    "GRANT",
    "COPY",
    "CALL",
    "DO",
    "INTO",
)
# Functions that change session state, reach outside the database, or hold locks. A read-only
# transaction already refuses most writes; set_config could switch the read-only default off.
FORBIDDEN_FUNCTIONS: tuple[str, ...] = (
    "set_config",
    "dblink",
    "dblink_exec",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "pg_rotate_logfile",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_sleep",
    "pg_advisory_lock",
    "pg_advisory_xact_lock",
    "lo_import",
    "lo_export",
    "nextval",
    "setval",
)
_FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE)
_FUNCTION_RE = re.compile(r"\b(" + "|".join(FORBIDDEN_FUNCTIONS) + r")\b", re.IGNORECASE)
_LEADING_RE = re.compile(r"^\(*\s*(SELECT|WITH)\b", re.IGNORECASE)
_DOLLAR_TAG_RE = re.compile(r"\$[A-Za-z_]*\$")

DEFAULT_STATEMENT_TIMEOUT_MS = 60_000


class RefusedError(Exception):
    """Input, SQL or database refused; nothing was run against the database."""


# --------------------------------------------------------------------------------------------
# SQL screening (no database)
# --------------------------------------------------------------------------------------------


def strip_sql_comments(sql: str) -> str:
    """Remove ``--`` and ``/* */`` comments, keeping quoted strings and identifiers intact.

    Dollar-quoted bodies are refused outright: they only appear in function bodies and DO blocks.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if ch == "-" and nxt == "-":
            end = sql.find("\n", i)
            i = n if end < 0 else end
            out.append(" ")
            continue
        if ch == "/" and nxt == "*":
            depth, i = 1, i + 2
            while i < n and depth:
                if sql.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif sql.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            if depth:
                raise RefusedError("unterminated /* comment")
            out.append(" ")
            continue
        if ch in ("'", '"'):
            j = i + 1
            while j < n:
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:  # doubled quote escape
                        j += 2
                        continue
                    break
                j += 1
            if j >= n:
                raise RefusedError("unterminated quoted string")
            out.append(sql[i : j + 1])
            i = j + 1
            continue
        if ch == "$" and _DOLLAR_TAG_RE.match(sql, i):
            raise RefusedError("dollar-quoted bodies are not allowed in a figure check")
        out.append(ch)
        i += 1
    return "".join(out)


def _without_literals(sql: str) -> str:
    """Blank out quoted strings and identifiers (input already comment-free)."""
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "''", sql)


def validate_select(sql: str) -> str:
    """Return the statement to run, or raise RefusedError. One SELECT or WITH ... SELECT only."""
    if not isinstance(sql, str) or not sql.strip():
        raise RefusedError("empty statement")
    cleaned = strip_sql_comments(sql).strip()
    while cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if ";" in _without_literals(cleaned):
        raise RefusedError("more than one statement (';' batch)")
    if not cleaned:
        raise RefusedError("empty statement")
    if not _LEADING_RE.match(cleaned):
        raise RefusedError("only SELECT or WITH ... SELECT is allowed")
    word = _FORBIDDEN_RE.search(cleaned)
    if word:
        raise RefusedError(f"refused keyword {word.group(1).upper()!r}")
    func = _FUNCTION_RE.search(cleaned)
    if func:
        raise RefusedError(f"refused function {func.group(1).lower()!r}")
    if not re.search(r"\bSELECT\b", _without_literals(cleaned), re.IGNORECASE):
        raise RefusedError("WITH without a SELECT")
    return cleaned


# --------------------------------------------------------------------------------------------
# Figures and comparison (no database)
# --------------------------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"^(.*?)(\d+(?:\.\d+)?|\.\d+)(.*)$")


def parse_figure(value: Any) -> Decimal | None:
    """Number from a page figure; same rule as ``parseFigure`` in apps/web matrix.ts.

    Spaces, non-breaking spaces and commas are thousands separators, ``.`` is the decimal point,
    a leading ``-`` or wrapping ``( )`` is negative; currency, units and ``%`` are ignored.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            return None
        return d if d.is_finite() else None
    text = re.sub(r"[\s\u00a0\u202f,]", "", str(value))
    m = _NUMBER_RE.match(text)
    if not m:
        return None
    number = Decimal(m.group(2))
    negative = "-" in m.group(1) or ("(" in m.group(1) and m.group(3).startswith(")"))
    return -number if negative else number


@dataclass(frozen=True)
class Tolerance:
    absolute: Decimal = Decimal(0)
    relative: Decimal = Decimal(0)  # fraction of |actual|

    def describe(self) -> str:
        if self.relative:
            return f"{(self.relative * 100).normalize()}%"
        return str(self.absolute.normalize()) if self.absolute else "0"


def parse_tolerance(raw: Any) -> Tolerance:
    """``None``/0 exact, a number is absolute, ``"<n>%"`` is relative to the database figure."""
    if raw is None or raw == "":
        return Tolerance()
    if isinstance(raw, str) and raw.strip().endswith("%"):
        pct = parse_figure(raw.strip()[:-1])
        if pct is None or pct < 0:
            raise RefusedError(f"bad tolerance {raw!r}")
        return Tolerance(relative=pct / Decimal(100))
    value = parse_figure(raw)
    if value is None or value < 0:
        raise RefusedError(f"bad tolerance {raw!r}")
    return Tolerance(absolute=value)


def figures_match(expected: Decimal, actual: Decimal, tolerance: Tolerance) -> bool:
    allowed = tolerance.absolute + tolerance.relative * abs(actual)
    return abs(expected - actual) <= allowed


# --------------------------------------------------------------------------------------------
# Checks input
# --------------------------------------------------------------------------------------------


@dataclass
class Check:
    name: str
    route: str
    sql: str
    params: dict[str, Any] | None
    expected_raw: Any
    tolerance: Tolerance
    selector: str | None = None


@dataclass
class CheckResult:
    name: str
    route: str
    # match | mismatch | missing_expected | page_inconsistent | no_row | not_numeric | error
    status: str
    tolerance: str = "0"
    expected: str | None = None
    actual: str | None = None
    difference: str | None = None
    expected_source: str = ""
    detail: str = ""
    page_values: list[str] = field(default_factory=list)


def load_checks(raw: Any) -> list[Check]:
    if not isinstance(raw, list) or not raw:
        raise RefusedError("checks file must be a non-empty JSON array")
    checks: list[Check] = []
    names: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise RefusedError(f"check #{i} is not an object")
        name, route, sql = item.get("name"), item.get("route"), item.get("sql")
        if not isinstance(name, str) or not name.strip():
            raise RefusedError(f"check #{i}: name is required")
        if name in names:
            raise RefusedError(f"duplicate check name {name!r}")
        names.add(name)
        if not isinstance(route, str) or not route.startswith("/"):
            raise RefusedError(f"check {name!r}: route must be an in-app path")
        try:
            statement = validate_select(sql)  # type: ignore[arg-type]
        except RefusedError as exc:
            raise RefusedError(f"check {name!r}: {exc}") from None
        params = item.get("params")
        if params is not None and not isinstance(params, Mapping):
            raise RefusedError(f"check {name!r}: params must be an object of named parameters")
        selector = item.get("selector")
        checks.append(
            Check(
                name=name,
                route=route,
                sql=statement,
                params=dict(params) if params else None,
                expected_raw=item.get("expected"),
                tolerance=parse_tolerance(item.get("tolerance")),
                selector=selector if isinstance(selector, str) else None,
            )
        )
    return checks


def load_page_figures(lines: Iterable[str]) -> dict[str, list[Decimal | None]]:
    """``figures.ndjson`` from the Playwright spec: name -> values seen (one per viewport)."""
    out: dict[str, list[Decimal | None]] = {}
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        row = json.loads(raw)
        out.setdefault(str(row.get("name")), []).append(parse_figure(row.get("value")))
    return out


def evaluate(
    check: Check,
    actual_value: Any,
    page_figures: Mapping[str, list[Decimal | None]] | None = None,
    *,
    row_count: int = 1,
) -> CheckResult:
    """Compare one check's expected figure with the database value (pure; no database)."""
    source = "checks file"
    expected = parse_figure(check.expected_raw)
    page_values: list[str] = []
    if expected is None and check.expected_raw is None and page_figures is not None:
        seen = page_figures.get(check.name, [])
        page_values = ["null" if v is None else str(v) for v in seen]
        distinct = set(seen)
        source = "page figures"
        if len(distinct) > 1:
            detail = "the page showed different values across viewports"
            return _result(check, "page_inconsistent", source, page_values, detail=detail)
        expected = next(iter(distinct)) if distinct else None
    if expected is None:
        detail = "no expected figure (none in the checks file, none captured from the page)"
        return _result(check, "missing_expected", source, page_values, detail=detail)
    if row_count != 1:
        detail = "query returned no row" if row_count == 0 else "query returned more than one row"
        return _result(check, "no_row", source, page_values, expected=expected, detail=detail)
    actual = parse_figure(actual_value)
    if actual is None:
        detail = f"database value is not a number: {actual_value!r}"[:200]
        return _result(check, "not_numeric", source, page_values, expected=expected, detail=detail)
    status = "match" if figures_match(expected, actual, check.tolerance) else "mismatch"
    return _result(check, status, source, page_values, expected=expected, actual=actual)


def _result(
    check: Check,
    status: str,
    source: str,
    page_values: list[str],
    *,
    expected: Decimal | None = None,
    actual: Decimal | None = None,
    detail: str = "",
) -> CheckResult:
    both = expected is not None and actual is not None
    return CheckResult(
        name=check.name,
        route=check.route,
        status=status,
        tolerance=check.tolerance.describe(),
        expected=None if expected is None else str(expected),
        actual=None if actual is None else str(actual),
        difference=str(expected - actual) if both else None,  # type: ignore[operator]
        expected_source=source,
        detail=detail,
        page_values=page_values,
    )


# --------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------


def _cell(value: Any) -> str:
    return "" if value is None else str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(results: list[CheckResult], database: str) -> str:
    headers = [
        "Check",
        "Route",
        "Status",
        "Page",
        "Database",
        "Difference",
        "Tolerance",
        "Expected from",
        "Detail",
    ]
    lines = [
        f"# Figure checks ({database})",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "---|" * len(headers),
    ]
    for r in results:
        cells = [
            r.name,
            r.route,
            r.status,
            r.expected,
            r.actual,
            r.difference,
            r.tolerance,
            r.expected_source,
            r.detail,
        ]
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    failed = sum(1 for r in results if r.status != "match")
    lines += ["", f"{len(results) - failed} of {len(results)} figures match."]
    return "\n".join(lines) + "\n"


def write_outputs(out_dir: Path, results: list[CheckResult], database: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / "figure_checks.md"
    js = out_dir / "figure_checks.json"
    md.write_text(render_markdown(results, database), encoding="utf-8")
    payload = {
        "database": database,
        "results": [asdict(r) for r in results],
        "mismatches": sum(1 for r in results if r.status != "match"),
    }
    js.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return md, js


# --------------------------------------------------------------------------------------------
# Database (read-only)
# --------------------------------------------------------------------------------------------


def normalise_db_url(url: str) -> str:
    """Accept ``postgresql+psycopg://`` or ``postgresql://`` (and ``postgres://``) for psycopg."""
    if not isinstance(url, str) or not url.strip():
        raise RefusedError("--db-url is required")
    url = url.strip()
    for prefix in ("postgresql+psycopg://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    if url.startswith("postgresql://"):
        return url
    raise RefusedError("--db-url must start with postgresql+psycopg:// or postgresql://")


def redact_url(url: str) -> str:
    return re.sub(r"://([^:/@]+):[^@]*@", r"://\1:***@", url)


def open_readonly(url: str, *, statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS):
    """Open an autocommit psycopg connection whose every transaction is read-only."""
    import psycopg  # local: unit tests patch psycopg.connect

    timeout = int(statement_timeout_ms)
    conn = psycopg.connect(
        normalise_db_url(url),
        autocommit=True,
        options=f"-c default_transaction_read_only=on -c statement_timeout={timeout}",
        application_name="cip_wave2_figure_check",
    )
    try:
        conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        conn.execute("SET default_transaction_read_only = on")
        state = conn.execute("SHOW default_transaction_read_only").fetchone()
        if not state or str(state[0]).lower() != "on":
            raise RefusedError("could not make the session read-only")
        conn.read_only = True
    except BaseException:
        conn.close()
        raise
    return conn


def assert_expected_db(conn, expect_db: str) -> str:
    row = conn.execute("SELECT current_database()").fetchone()
    actual = str(row[0]) if row else ""
    if not expect_db or actual != expect_db:
        raise RefusedError(
            f"current_database() is {actual!r}, --expect-db is {expect_db!r}; refusing"
        )
    return actual


class _Rollback(Exception):
    pass


def run_query(conn, check: Check) -> tuple[Any, int]:
    """Run one screened SELECT in its own READ ONLY transaction, always rolled back."""
    statement = validate_select(check.sql)  # re-screen right before execution
    value: Any = None
    rows = 0
    try:
        with conn.transaction():
            ro = conn.execute("SHOW transaction_read_only").fetchone()
            if not ro or str(ro[0]).lower() != "on":
                raise RefusedError("transaction is not read-only; refusing to run the check")
            cur = conn.execute(statement, check.params) if check.params else conn.execute(statement)
            if cur.description is None or len(cur.description) != 1:
                raise RefusedError("a figure check must return exactly one column")
            fetched = cur.fetchmany(2)
            rows = len(fetched)
            value = fetched[0][0] if fetched else None
            raise _Rollback
    except _Rollback:
        pass
    return value, rows


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compare page figures with read-only SQL (Wave 2).")
    p.add_argument("--checks", required=True, type=Path, help="JSON array of checks")
    p.add_argument("--db-url", required=True, help="postgresql+psycopg:// or postgresql:// URL")
    p.add_argument(
        "--expect-db", required=True, help="refuse unless current_database() equals this"
    )
    p.add_argument("--out", required=True, type=Path, help="directory for figure_checks.md/.json")
    p.add_argument("--page-figures", type=Path, help="figures.ndjson from the Playwright spec")
    p.add_argument("--statement-timeout-ms", type=int, default=DEFAULT_STATEMENT_TIMEOUT_MS)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = load_checks(json.loads(args.checks.read_text(encoding="utf-8")))
        page_figures = None
        if args.page_figures:
            page_figures = load_page_figures(
                args.page_figures.read_text(encoding="utf-8").splitlines()
            )
        url = normalise_db_url(args.db_url)
    except (RefusedError, OSError, json.JSONDecodeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2

    try:
        conn = open_readonly(url, statement_timeout_ms=args.statement_timeout_ms)
    except RefusedError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - report the driver error without the URL secret
        print(
            f"refused: cannot connect to {redact_url(url)}: {type(exc).__name__}", file=sys.stderr
        )
        return 2

    results: list[CheckResult] = []
    with conn:
        try:
            database = assert_expected_db(conn, args.expect_db)
        except RefusedError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        print(f"current_database={database!r} (read-only session)")
        for check in checks:
            try:
                value, rows = run_query(conn, check)
            except RefusedError as exc:
                print(f"refused: check {check.name!r}: {exc}", file=sys.stderr)
                return 2
            except Exception as exc:  # noqa: BLE001 - one bad query is a failed check, not a crash
                detail = f"{type(exc).__name__}: {exc}"[:300]
                results.append(_result(check, "error", "", [], detail=detail))
                continue
            results.append(evaluate(check, value, page_figures, row_count=rows))

    md, js = write_outputs(args.out, results, database)
    failed = [r for r in results if r.status != "match"]
    print(f"{len(results) - len(failed)} of {len(results)} figures match; wrote {md} and {js}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
