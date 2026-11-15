#!/usr/bin/env python3
"""Fill empty listing-site reader columns from a reviewed JSON file (W1-D, 2026-11-13).

Migration 20261103_0053 created one ``listing_site`` row per site with no page reader: the reader
settings that used to be code constants were not carried across, so the poll has skipped every
listing on those sites since. This script puts such settings back as DATA. Nothing here names a
site: the site keys and values come only from the input file.

Input (UTF-8 JSON)::

    {
      "tenant_id": "default",
      "sites": {
        "<site_key>": {"adapter_key": "...", "details_url_pattern": "...", ...}
      }
    }

Only these columns can be given: adapter_key, product_url_pattern, page_id_pattern,
search_url_pattern, details_url_pattern, first_party_seller, rate_limit_seconds. Every value is
checked with the same rules as the Sites & sellers editor. Other top-level keys (notes,
provenance) are ignored.

Rules:
- A column is filled only when it is empty (NULL or blank) on the row today. A value already
  there (a steward's) is kept and listed as "kept"; it is never replaced.
- A site key with no row in the tenant stops the run (the script never creates sites).
- The plan shows each site before and after, whether it will have a working reader, how many
  due listings it covers, and, when it will have a details link, the details URL built from one
  stored listing link (so a page-id pattern that captures the wrong part shows up before apply).

  dry run (read-only):
  python scripts/ops/restore_listing_site_readers.py --input <file>
  apply:
  python scripts/ops/restore_listing_site_readers.py --input <file> --apply --expect-db cip_test

``--apply`` needs ``--expect-db`` equal to ``current_database()``. It runs in ONE transaction:
each fill is a guarded UPDATE (``... WHERE <column> is still empty``) that must touch exactly one
row, and one ``platform_audit_event`` (area ``admin``, action ``listing_site_reader_restore``) keeps
the before and after rows and the undo SQL. Any difference rolls everything back. A second run
finds nothing to fill and writes nothing. The database is the one in DATABASE_URL_SYNC.
Never run it on ``cip`` before Warren says "run against cip".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text  # noqa: E402

FIELDS: tuple[str, ...] = (
    "adapter_key",
    "product_url_pattern",
    "page_id_pattern",
    "search_url_pattern",
    "details_url_pattern",
    "first_party_seller",
    "rate_limit_seconds",
)
ROW_COLUMNS: tuple[str, ...] = (
    "id",
    "tenant_id",
    "site_key",
    "display_name",
    "is_active",
    *FIELDS,
    "updated_by",
    "updated_at",
)
ACTOR = "scripts/ops/restore_listing_site_readers.py"
AUDIT_ACTION = "listing_site_reader_restore"


class InputError(ValueError):
    """The input file is not usable. Nothing is read from or written to the database."""


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _same(current: Any, wanted: Any) -> bool:
    if isinstance(current, (int, float, Decimal)) or isinstance(wanted, (int, float, Decimal)):
        try:
            return Decimal(str(current)) == Decimal(str(wanted))
        except Exception:  # noqa: BLE001
            return False
    return str(current).strip() == str(wanted).strip()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def load_input(path: Path) -> tuple[str, dict[str, dict[str, Any]], str]:
    """(tenant_id, {site_key: {column: normalized value}}, sha256 of the file)."""
    from app.services.listing_capture.sites import SITE_KEY_RE, _normalized_fields

    raw_bytes = path.read_bytes()
    try:
        doc = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"input is not UTF-8 JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("sites"), dict) or not doc["sites"]:
        raise InputError('input needs a non-empty "sites" object')
    tenant = str(doc.get("tenant_id") or "default").strip() or "default"
    out: dict[str, dict[str, Any]] = {}
    for key, values in doc["sites"].items():
        site_key = str(key).strip().lower()
        if not SITE_KEY_RE.match(site_key):
            raise InputError(f"{key!r}: not a valid site key")
        if site_key in out:
            raise InputError(f"{key!r}: site key given twice")
        if not isinstance(values, dict) or not values:
            raise InputError(f"{site_key}: needs an object of column values")
        unknown = sorted(set(values) - set(FIELDS))
        if unknown:
            raise InputError(f"{site_key}: columns not allowed here: {', '.join(unknown)}")
        try:
            normalized = _normalized_fields(values)
        except ValueError as exc:
            raise InputError(f"{site_key}: {exc}") from exc
        kept = {name: value for name, value in normalized.items() if not _blank(value)}
        if not kept:
            raise InputError(f"{site_key}: every value is empty")
        out[site_key] = kept
    return tenant, out, hashlib.sha256(raw_bytes).hexdigest()


def read_site(conn, tenant: str, site_key: str) -> dict[str, Any] | None:
    sql = (
        f"SELECT {', '.join(ROW_COLUMNS)} FROM listing_site "
        "WHERE tenant_id = :t AND site_key = :k"
    )
    row = conn.execute(text(sql), {"t": tenant, "k": site_key}).mappings().first()
    return {name: row[name] for name in ROW_COLUMNS} if row is not None else None


def _site_config(row: dict[str, Any]):
    from app.services.listing_capture.adapters import SiteConfig

    def txt(name: str) -> str | None:
        value = row.get(name)
        return None if _blank(value) else str(value).strip()

    rate = row.get("rate_limit_seconds")
    return SiteConfig(
        site_key=str(row["site_key"]),
        display_name=str(row.get("display_name") or row["site_key"]),
        adapter_key=txt("adapter_key"),
        product_url_pattern=txt("product_url_pattern"),
        page_id_pattern=txt("page_id_pattern"),
        search_url_pattern=txt("search_url_pattern"),
        details_url_pattern=txt("details_url_pattern"),
        first_party_seller=txt("first_party_seller"),
        rate_limit_seconds=float(rate) if rate is not None else None,
        is_active=bool(row.get("is_active")),
        id=int(row["id"]),
        tenant_id=str(row["tenant_id"]),
    )


def _due_listings(conn, tenant: str, site_key: str) -> int:
    from app.services.listing_capture.registry import POLLED_LISTING_STATUSES

    return int(
        conn.execute(
            text(
                "SELECT count(*) FROM customer_listing l "
                "JOIN dim_customer c ON c.id = l.customer_id "
                "WHERE c.tenant_id = :t AND lower(trim(l.marketplace)) = :k "
                "AND l.status = ANY(:s)"
            ),
            {"t": tenant, "k": site_key, "s": list(POLLED_LISTING_STATUSES)},
        ).scalar()
        or 0
    )


def _details_sample(conn, tenant: str, row_after: dict[str, Any]) -> dict[str, Any] | None:
    """The details URL the reader would call for one stored listing link, or why there is none."""
    pattern, details = row_after.get("page_id_pattern"), row_after.get("details_url_pattern")
    if _blank(details):
        return None
    url = conn.execute(
        text(
            "SELECT l.url FROM customer_listing l "
            "JOIN dim_customer c ON c.id = l.customer_id "
            "WHERE c.tenant_id = :t AND lower(trim(l.marketplace)) = :k "
            "AND coalesce(l.url, '') <> '' ORDER BY l.id LIMIT 1"
        ),
        {"t": tenant, "k": row_after["site_key"]},
    ).scalar()
    if not url:
        return {"listing_url": None, "note": "no stored listing link on this site"}
    if _blank(pattern):
        return {"listing_url": url, "note": "no page_id_pattern"}
    try:
        match = re.search(str(pattern), str(url))
    except re.error as exc:
        return {"listing_url": url, "note": f"page_id_pattern does not compile: {exc}"}
    if not match:
        return {"listing_url": url, "note": "page_id_pattern does not match this link"}
    page_id = match.group(1) if match.groups() else match.group(0)
    from urllib.parse import quote

    return {
        "listing_url": url,
        "page_id": page_id,
        "details_url": str(details).replace("{page_id}", quote(page_id, safe="")),
    }


def plan_sites(conn, tenant: str, wanted: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    from app.services.listing_capture.adapters import missing_fields

    plans: list[dict[str, Any]] = []
    for site_key in sorted(wanted):
        before = read_site(conn, tenant, site_key)
        if before is None:
            plans.append(
                {
                    "site_key": site_key,
                    "error": f"no listing_site row for {site_key!r} in tenant {tenant!r}",
                }
            )
            continue
        fill: dict[str, Any] = {}
        kept: dict[str, dict[str, Any]] = {}
        already: list[str] = []
        for name, value in wanted[site_key].items():
            current = before.get(name)
            if _blank(current):
                fill[name] = value
            elif _same(current, value):
                already.append(name)
            else:
                kept[name] = {"current": _jsonable(current), "file": _jsonable(value)}
        after = {**before, **fill}
        before_cfg, after_cfg = _site_config(before), _site_config(after)
        plans.append(
            {
                "site_key": site_key,
                "site_id": int(before["id"]),
                "fill": fill,
                "kept": kept,
                "already_set": sorted(already),
                "before": before,
                "after": after,
                "missing_before": missing_fields(before_cfg),
                "missing_after": missing_fields(after_cfg),
                "is_active": bool(before["is_active"]),
                "due_listings": _due_listings(conn, tenant, site_key),
                "details_sample": _details_sample(conn, tenant, after),
            }
        )
    return plans


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def undo_sql(plan: dict[str, Any]) -> str | None:
    """Puts back the empty values, only while the filled values are still the ones written here."""
    fill = plan.get("fill") or {}
    if not fill:
        return None
    before = plan["before"]
    sets = [f"{name} = {_sql_literal(before.get(name))}" for name in fill]
    sets.append(f"updated_by = {_sql_literal(before.get('updated_by'))}")
    sets.append("updated_at = now()")
    guards = [f"{name} = {_sql_literal(value)}" for name, value in fill.items()]
    where = " AND ".join([f"id = {int(plan['site_id'])}", *guards])
    return f"UPDATE listing_site SET {', '.join(sets)} WHERE {where};"


def _row_for_audit(row: dict[str, Any]) -> dict[str, Any]:
    return {name: _jsonable(row.get(name)) for name in ROW_COLUMNS}


def apply_plans(conn, plans: list[dict[str, Any]]) -> int:
    """Guarded UPDATE per column; each must change exactly one row. Returns the columns filled."""
    filled = 0
    for plan in plans:
        for name, value in plan["fill"].items():
            assert name in FIELDS  # column names come from the fixed list only
            empty = (
                f"{name} IS NULL"
                if name == "rate_limit_seconds"
                else f"({name} IS NULL OR btrim({name}) = '')"
            )
            result = conn.execute(
                text(
                    f"UPDATE listing_site SET {name} = :v, updated_by = :actor, updated_at = now() "
                    f"WHERE id = :id AND {empty}"
                ),
                {"v": value, "actor": ACTOR, "id": plan["site_id"]},
            )
            if result.rowcount != 1:
                raise RuntimeError(
                    f"{plan['site_key']}.{name}: changed {result.rowcount} rows, plan says 1"
                )
            filled += 1
    return filled


def run(
    conn,
    *,
    input_path: Path,
    apply: bool = False,
    expect_db: str | None = None,
    say: Callable[[str], None] = print,
    fail_before_commit: bool = False,
) -> int:
    """0 done (or nothing to do), 2 refused / input or plan error, 3 rolled back."""
    db = conn.execute(text("SELECT current_database()")).scalar()
    ro = conn.execute(text("SHOW transaction_read_only")).scalar()
    mode = "APPLY" if apply else "dry run, nothing is changed"
    say(f"current_database() = {db}; transaction_read_only = {ro}; {mode}")
    if apply and expect_db != db:
        say(f"refused: --apply needs --expect-db {db!r} (got {expect_db!r})")
        return 2
    try:
        tenant, wanted, sha = load_input(input_path)
    except (InputError, OSError) as exc:
        say(f"STOP: {exc}")
        return 2
    say(f"input {input_path} sha256 {sha}; tenant {tenant}; {len(wanted)} site(s)")
    plans = plan_sites(conn, tenant, wanted)
    errors = [p for p in plans if p.get("error")]
    for plan in plans:
        if plan.get("error"):
            say(f"\n{plan['site_key']}: ERROR {plan['error']}")
            continue
        state_before = (
            "reader OK"
            if not plan["missing_before"] and plan["is_active"]
            else f"no reader (missing: {', '.join(plan['missing_before']) or 'is_active'})"
        )
        state_after = (
            "reader OK"
            if not plan["missing_after"] and plan["is_active"]
            else f"still no reader (missing: {', '.join(plan['missing_after']) or 'is_active'})"
        )
        head = f"{plan['site_key']} (site {plan['site_id']}, {plan['due_listings']} due listings)"
        say(f"\n{head}: {state_before} -> {state_after}")
        for name, value in plan["fill"].items():
            say(f"  fill   {name}: {_jsonable(plan['before'].get(name))!r} -> {_jsonable(value)!r}")
        for name, rec in plan["kept"].items():
            say(
                f"  kept   {name}: {rec['current']!r} (file has {rec['file']!r}; "
                "a value already there is never replaced)"
            )
        for name in plan["already_set"]:
            say(f"  same   {name}: already {_jsonable(plan['before'].get(name))!r}")
        if plan["details_sample"] is not None:
            say(f"  details sample: {json.dumps(plan['details_sample'])}")
        if not plan["fill"]:
            say("  nothing to fill")
    if errors:
        say(f"\nSTOP: {len(errors)} site(s) cannot be planned; nothing is written")
        return 2
    to_fill = sum(len(p["fill"]) for p in plans)
    say(f"\n{to_fill} column(s) to fill on {sum(1 for p in plans if p['fill'])} site(s)")
    if not apply:
        return 0
    if to_fill == 0:
        say("nothing to fill; nothing written, no audit event")
        return 0
    nested = conn.begin_nested()
    try:
        filled = apply_plans(conn, plans)
        after_rows: dict[str, dict[str, Any]] = {}
        for plan in plans:
            row = read_site(conn, tenant, plan["site_key"])
            assert row is not None
            for name, value in plan["fill"].items():
                if not _same(row.get(name), value):
                    got = row.get(name)
                    raise RuntimeError(
                        f"{plan['site_key']}.{name}: reads back {got!r}, plan says {value!r}"
                    )
            after_rows[plan["site_key"]] = row
        detail = {
            "input_file": str(input_path.name),
            "input_sha256": sha,
            "columns_filled": filled,
            "sites": {
                p["site_key"]: {
                    "site_id": p["site_id"],
                    "filled": sorted(p["fill"]),
                    "kept": p["kept"],
                    "before": _row_for_audit(p["before"]),
                    "after": _row_for_audit(after_rows[p["site_key"]]),
                    "undo_sql": undo_sql(p),
                }
                for p in plans
            },
        }
        from app.services.platform_audit import record_platform_audit_sync
        from sqlalchemy.orm import Session

        # Its own SAVEPOINT inside this run's transaction: committing it keeps the row in the
        # run's transaction (a joined session would discard it on close).
        with Session(bind=conn, join_transaction_mode="create_savepoint") as session:
            event = record_platform_audit_sync(
                session,
                {"tenant_id": tenant},
                area="admin",
                action=AUDIT_ACTION,
                target_type="listing_site",
                target_id=",".join(p["site_key"] for p in plans if p["fill"]),
                actor_label=ACTOR,
                detail=detail,
            )
            session.flush()
            event_id = int(event.id)
            session.commit()
        if fail_before_commit:
            raise RuntimeError("forced failure before commit (rehearsal)")
        nested.commit()
    except Exception as exc:  # noqa: BLE001 - any failure rolls everything back
        nested.rollback()
        say(f"ROLLED BACK, nothing changed: {exc}")
        return 3
    say(f"filled {filled} column(s); platform_audit_event id {event_id}")
    for site_key, row in after_rows.items():
        say(f"  after {site_key}: {json.dumps(_row_for_audit(row), sort_keys=True)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--input", required=True, help="JSON file of per-site values")
    p.add_argument("--apply", action="store_true", help="write the plan (needs --expect-db)")
    p.add_argument(
        "--expect-db", default=None, help="required with --apply; must equal current_database()"
    )
    p.add_argument("--out", default=None, help="also write the report to this file")
    p.add_argument("--fail-before-commit", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    lines: list[str] = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        lines.append(msg)

    from app.db.session_sync import sync_engine

    with sync_engine.connect() as conn:
        if not args.apply:
            conn.exec_driver_sql("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            conn.commit()
        try:
            if not args.apply and conn.execute(text("SHOW transaction_read_only")).scalar() != "on":
                say("STOP: the dry run is not read-only")
                code = 2
            else:
                code = run(
                    conn,
                    input_path=Path(args.input),
                    apply=args.apply,
                    expect_db=args.expect_db,
                    say=say,
                    fail_before_commit=args.fail_before_commit,
                )
            if args.apply and code == 0:
                conn.commit()
                say("committed")
            else:
                conn.rollback()
        finally:
            if not args.apply:
                # The pooled connection goes back read-write for whoever uses it next.
                conn.rollback()
                conn.exec_driver_sql("SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE")
                conn.commit()
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
