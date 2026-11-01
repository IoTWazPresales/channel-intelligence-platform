"""Read-only: list where a database's schema differs from the SQLAlchemy models.

Uses Alembic's own comparator, so the answer is what ``alembic revision --autogenerate`` would see.
The session is read-only (``default_transaction_read_only``), so it is safe against ``cip``.

    python scripts/ops/schema_drift_report.py --db cip [--tables fact_inbound_shipment,...] [--out file]

Connects as the app role from settings with the database name replaced; ``--url`` overrides it.
Nothing is changed, and the report never prints a password.
"""
from __future__ import annotations

import argparse
import importlib
import pkgutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


def _load_all_models() -> None:
    import app.models as models

    for mod in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"app.models.{mod.name}")


def _describe(diff) -> tuple[str, str]:
    """Return (table, one-line description) for one comparator entry."""
    kind = diff[0]
    if kind in {"add_table", "remove_table"}:
        t = diff[1]
        side = "in models, not in database" if kind == "add_table" else "in database, not in models"
        return t.name, f"TABLE {t.name}: {side}"
    if kind in {"add_column", "remove_column"}:
        table, col = diff[2], diff[3]
        side = "in models, not in database" if kind == "add_column" else "in database, not in models"
        return table, f"COLUMN {table}.{col.name}: {side}"
    if kind in {"add_index", "remove_index"}:
        ix = diff[1]
        side = "in models, not in database" if kind == "add_index" else "in database, not in models"
        cols = ", ".join(c.name for c in ix.columns)
        return ix.table.name, f"INDEX {ix.name} ({cols}){' UNIQUE' if ix.unique else ''}: {side}"
    if kind in {"add_constraint", "remove_constraint"}:
        c = diff[1]
        side = "in models, not in database" if kind == "add_constraint" else "in database, not in models"
        cols = ", ".join(col.name for col in getattr(c, "columns", []))
        return c.table.name, f"{type(c).__name__.upper()} {c.name} ({cols}): {side}"
    if kind in {"add_fk", "remove_fk"}:
        c = diff[1]
        side = "in models, not in database" if kind == "add_fk" else "in database, not in models"
        cols = ", ".join(col.name for col in getattr(c, "columns", []))
        return c.table.name, f"FOREIGN KEY {c.name} ({cols}): {side}"
    if kind in {"modify_type", "modify_nullable", "modify_default"}:
        table, col = diff[2], diff[3]
        if kind == "modify_type":
            return table, f"COLUMN {table}.{col}: type database={diff[5]} models={diff[6]}"
        if kind == "modify_nullable":
            return table, f"COLUMN {table}.{col}: nullable database={diff[5]} models={diff[6]}"
        return table, f"COLUMN {table}.{col}: default differs"
    return "?", repr(diff)


def _flatten(diffs):
    for d in diffs:
        if isinstance(d, list):
            yield from _flatten(d)
        else:
            yield d


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="cip", help="database name on the settings host (default: cip)")
    ap.add_argument("--url", help="full sync SQLAlchemy URL; overrides --db")
    ap.add_argument("--tables", help="comma-separated table names to report on (default: all)")
    ap.add_argument("--out", help="write the report here as well as printing it")
    args = ap.parse_args()

    from app.core.config import get_settings
    from app.db.base import Base

    _load_all_models()
    from app.db.sync_url import sqlalchemy_sync_engine_url

    raw = args.url or str(make_url(get_settings().database_url_sync).set(database=args.db).render_as_string(hide_password=False))
    url = make_url(sqlalchemy_sync_engine_url(raw))
    engine = create_engine(url)
    only = {t.strip() for t in args.tables.split(",")} if args.tables else None

    def include_object(obj, name, type_, reflected, compare_to):
        if type_ == "table" and name == "alembic_version":
            return False
        return True

    with engine.connect() as conn:
        conn.execute(text("SET default_transaction_read_only = on"))
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        ctx = MigrationContext.configure(
            conn, opts={"compare_type": True, "compare_server_default": False, "include_object": include_object}
        )
        diffs = list(_flatten(compare_metadata(ctx, Base.metadata)))
        conn.rollback()

    rows = sorted({_describe(d) for d in diffs})
    if only is not None:
        rows = [r for r in rows if r[0] in only]
    lines = [
        f"schema drift: database={url.database} alembic_version={head} (read-only; models vs live catalogue)",
        f"{len(rows)} difference(s)" + (f" on {', '.join(sorted(only))}" if only else ""),
        "",
    ]
    lines += [f"{t}\t{desc}" for t, desc in rows]
    report = "\n".join(lines) + "\n"
    print(report)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
