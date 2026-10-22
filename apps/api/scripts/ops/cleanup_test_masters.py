"""Remove test customers, distributors and products together with every row that references them (guarded).

A test record goes only when every row that references it, directly or through other rows, is test data:
a test record itself, a row from an import job that no longer exists (the test jobs were deleted), or an
unlinked row (no import job) that points only at test records. One row from a real job, a real customer,
distributor or product, or a real case (any other record that stays) keeps the record, and the report
says which row. Records a kept record depends on are kept too.

Dry run (default): read-only. Lists every test record, what references it (table, row count, and whether
each row is from a real job, real record, a deleted test job or unlinked) and whether it would go.
``--apply --expect-db <name>``: one transaction. Removes the removable records and their rows, checks
every delete's row count against the plan, writes one platform_audit_event holding every removed row in
full, and commits. Any mismatch or error rolls everything back.

Usage (from apps/api):
  python scripts/ops/cleanup_test_masters.py                          dry run on the configured database
  python scripts/ops/cleanup_test_masters.py --apply --expect-db cip  remove (all or nothing)
  --out FILE    also write the report to FILE
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402

from app.services.customer_test_fixtures import is_test_fixture_customer  # noqa: E402

MASTERS = {"dim_customer": "customer", "dim_distributor": "distributor", "dim_product": "product"}

# Test record rules (census 2026-10-22, each pattern traced to a test in apps/api/tests or its history).
# Customers: is_test_fixture_customer (codes tests mint, fixture names), plus these names tests give
# real-shaped codes.
TEST_CUSTOMER_CODES = ("CUST-1001",)
TEST_CUSTOMER_NAMES = ("metro market group", "jane doe - staff", "john roe - staff", "nobody known ltd", "acme widgets (pty) ltd")
TEST_CUSTOMER_NAME_RE = re.compile(
    r"^(steward map dealer|fresh dealer|metro reporting group|batch dealer group (alpha|beta)) [0-9a-f]{8}$"
    r"|^batch dealer [0-9a-f]{8}-agg-[ab]$",
    re.IGNORECASE,
)
# Distributors: real ones carry DIST-nnnnnn, TMP-DIST-… or UNASSIGNED.
TEST_DISTRIBUTOR_CODE_RE = re.compile(r"^(DIST-01|DIST-(FULL|PO|T|HL)-.+)$")
TEST_DISTRIBUTOR_NAME_RE = re.compile(r"^(Summit Supply Co\.|Novel Disti NOVEL-DIST-[0-9a-f]{8})$")
TEST_PRODUCT_SKU_RE = re.compile(r"^(SKU-ALPHA-01|bulk-n[br]-\d+|sku-older|sku-newer|only-one|SKU-HL-\d+|SKU-RES-\w+|SKU-STEP2-TEST)$")
# Placeholders loads point at; a link to one says nothing about whether a row is real.
NEUTRAL_CODES = {"dim_customer": ("OPEN_CHANNEL",), "dim_distributor": ("UNASSIGNED",)}

# Columns that hold a master id without a foreign key: (table, column, master table, extra condition).
LOOSE_REFS = (
    ("import_entity_mapping_candidate", "suggested_entity_id", "dim_customer",
     "entity_type IN ('customer_dealer_token', 'shipment_customer_token')"),
    ("import_entity_mapping_candidate", "suggested_entity_id", "dim_distributor",
     "entity_type IN ('distributor_token', 'shipment_distributor')"),
    ("import_entity_mapping_candidate", "suggested_entity_id", "dim_product",
     "entity_type IN ('product_identifier', 'cst_product_token')"),
    ("task_run", "entity_id", "dim_customer", "entity_type IN ('customer_full_merge', 'customer_alias_scope_merge')"),
    ("budget_ledger_entry", "customer_id", "dim_customer", None),
    ("budget_ledger_entry", "product_id", "dim_product", None),
    ("fact_customer_sellthrough_superseded", "customer_id", "dim_customer", None),
    ("fact_customer_sellthrough_superseded", "product_id", "dim_product", None),
    ("fact_distributor_line_superseded", "customer_id", "dim_customer", None),
    ("fact_distributor_line_superseded", "distributor_id", "dim_distributor", None),
    ("fact_distributor_line_superseded", "product_id", "dim_product", None),
)
# Lookup and set-up tables a row may point at without that saying anything about the row.
CONTEXT_TABLES = frozenset({"dim_region", "dim_channel", "app_user", "tenant", "source_definition", "import_template"})


@dataclass(frozen=True)
class Ref:
    child: str
    col: str
    parent: str
    pcol: str
    extra: str | None = None


@dataclass
class Row:
    table: str
    pk: Any
    data: dict[str, Any]
    origins: set[tuple[str, int]] = field(default_factory=set)
    real: str | None = None  # why the row is real; None while it is test or unlinked
    # test record | deleted test job | unlinked, or real job | real customer | real distributor | real product
    # | real <table> (it belongs to a record outside the test data)
    kind: str = "unlinked"


@dataclass
class Schema:
    refs: list[Ref]
    pk: dict[str, str]
    job_cols: dict[str, list[str]]
    rls: set[str]


def load_schema(conn: Connection) -> Schema:
    fks = conn.execute(
        text(
            """
            SELECT cl.relname, a.attname, rf.relname, ra.attname
            FROM pg_constraint con
            JOIN pg_class cl ON cl.oid = con.conrelid
            JOIN pg_class rf ON rf.oid = con.confrelid
            JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = con.conkey[1]
            JOIN pg_attribute ra ON ra.attrelid = con.confrelid AND ra.attnum = con.confkey[1]
            JOIN pg_namespace n ON n.oid = cl.relnamespace
            WHERE con.contype = 'f' AND n.nspname = 'public' AND array_length(con.conkey, 1) = 1
            """
        )
    ).all()
    refs = [Ref(c, col, p, pcol) for c, col, p, pcol in fks]
    refs += [Ref(t, c, p, "id", extra) for t, c, p, extra in LOOSE_REFS]
    pk = dict(
        conn.execute(
            text(
                """
                SELECT c.relname, a.attname FROM pg_index i
                JOIN pg_class c ON c.oid = i.indrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = i.indkey[0]
                WHERE i.indisprimary AND n.nspname = 'public' AND array_length(i.indkey::int[], 1) = 1
                """
            )
        ).all()
    )
    job_cols: dict[str, list[str]] = defaultdict(list)
    for r in refs:
        if r.parent == "import_job":
            job_cols[r.child].append(r.col)
    for t, c in conn.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name LIKE '%import_job_id'"
        )
    ):
        if c not in job_cols[t]:
            job_cols[t].append(c)
    rls = set(
        conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relrowsecurity"
            )
        ).scalars()
    )
    return Schema(refs, pk, dict(job_cols), rls)


def test_masters(conn: Connection) -> dict[str, dict[int, str]]:
    out: dict[str, dict[int, str]] = {t: {} for t in MASTERS}
    for r in conn.execute(text("SELECT id, code, name FROM dim_customer")):
        name = (r.name or "").strip()
        if (
            r.code in TEST_CUSTOMER_CODES
            or name.lower() in TEST_CUSTOMER_NAMES
            or TEST_CUSTOMER_NAME_RE.match(name)
            or is_test_fixture_customer(r.code, r.name)
        ):
            out["dim_customer"][r.id] = f"{r.code} {name}"
    for r in conn.execute(text("SELECT id, code, name FROM dim_distributor")):
        if TEST_DISTRIBUTOR_CODE_RE.match(r.code or "") or TEST_DISTRIBUTOR_NAME_RE.match((r.name or "").strip()):
            out["dim_distributor"][r.id] = f"{r.code} {r.name}"
    for r in conn.execute(text("SELECT id, sku FROM dim_product")):
        if TEST_PRODUCT_SKU_RE.match(r.sku or ""):
            out["dim_product"][r.id] = r.sku
    return out


def neutral_ids(conn: Connection) -> dict[str, set[int]]:
    return {
        t: set(conn.execute(text(f"SELECT id FROM {t} WHERE code = ANY(:c)"), {"c": list(codes)}).scalars())
        for t, codes in NEUTRAL_CODES.items()
    }


def master_label(conn: Connection, table: str, eid: int) -> str:
    if table == "dim_product":
        return f"product {eid} {conn.execute(text('SELECT sku FROM dim_product WHERE id = :i'), {'i': eid}).scalar()}"
    r = conn.execute(text(f"SELECT code, name FROM {table} WHERE id = :i"), {"i": eid}).first()
    return f"{MASTERS[table]} {eid} {r.code if r else '?'} {r.name if r else ''}".strip()


class Plan:
    """Every row reachable from the test records, each classified, and which records can go."""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self.schema = load_schema(conn)
        self.test = test_masters(conn)
        self.neutral = neutral_ids(conn)
        self.jobs = set(conn.execute(text("SELECT id FROM import_job")).scalars())
        self.rows: dict[tuple[str, Any], Row] = {}
        self.missing_pk: set[str] = set()
        self._walk()
        self._outside_parents()
        self._decide()

    # ------------------------------------------------------------------ walk
    def _classify(self, table: str, data: dict[str, Any]) -> tuple[str, str | None]:
        if table in MASTERS:
            if data["id"] in self.test[table]:
                return "test record", None
            return f"real {MASTERS[table]}", f"real {master_label(self.conn, table, data['id'])}"
        for col in self.schema.job_cols.get(table, []):
            job = data.get(col)
            if job is not None and job in self.jobs:
                return "real job", f"from import job {job} ({col})"
        for ref in self.schema.refs:
            if ref.child != table or ref.parent not in MASTERS or data.get(ref.col) is None:
                continue
            if ref.extra and not self._extra_holds(ref, data):
                continue
            v = data[ref.col]
            if v not in self.test[ref.parent] and v not in self.neutral.get(ref.parent, set()):
                return f"real {MASTERS[ref.parent]}", f"{ref.col} -> real {master_label(self.conn, ref.parent, v)}"
        if any(data.get(c) is not None for c in self.schema.job_cols.get(table, [])):
            return "deleted test job", None
        return "unlinked", None

    def _extra_holds(self, ref: Ref, data: dict[str, Any]) -> bool:
        # The loose refs' conditions are all "entity_type IN (...)".
        allowed = re.findall(r"'([^']+)'", ref.extra or "")
        return data.get("entity_type") in allowed

    def _add(self, table: str, data: dict[str, Any], origins: set[tuple[str, int]]) -> Row | None:
        pkcol = self.schema.pk.get(table)
        if not pkcol:
            self.missing_pk.add(table)
            return None
        key = (table, data[pkcol])
        row = self.rows.get(key)
        if row is None:
            kind, why = self._classify(table, data)
            row = Row(table, data[pkcol], data, set(origins), why, kind)
            self.rows[key] = row
            return row
        if origins - row.origins:
            row.origins |= origins
            return row
        return None

    def _walk(self) -> None:
        frontier: dict[str, list[Row]] = defaultdict(list)
        for table, ids in self.test.items():
            if not ids:
                continue
            for d in self.conn.execute(
                text(f"SELECT to_jsonb(t) AS j FROM {table} t WHERE id = ANY(:ids)"), {"ids": list(ids)}
            ).scalars():
                row = self._add(table, d, {(table, d["id"])})
                if row:
                    frontier[table].append(row)
        while frontier:
            nxt: dict[str, list[Row]] = defaultdict(list)
            for parent, prow in frontier.items():
                live = [r for r in prow if r.real is None]  # do not walk below real rows
                if not live:
                    continue
                for ref in self.schema.refs:
                    if ref.parent != parent:
                        continue
                    by_value: dict[Any, set[tuple[str, int]]] = defaultdict(set)
                    for r in live:
                        if r.data.get(ref.pcol) is not None:
                            by_value[r.data[ref.pcol]] |= r.origins
                    if not by_value:
                        continue
                    where = f"{ref.col} = ANY(:v)" + (f" AND {ref.extra}" if ref.extra else "")
                    for d in self.conn.execute(
                        text(f"SELECT to_jsonb(c) AS j FROM {ref.child} c WHERE {where}"), {"v": list(by_value)}
                    ).scalars():
                        row = self._add(ref.child, d, by_value[d[ref.col]])
                        if row:
                            nxt[ref.child].append(row)
            frontier = nxt

    def _outside_parents(self) -> None:
        """A test or unlinked row that belongs to a record outside the test data (a case, a plan) is real."""
        for row in self.rows.values():
            if row.real is not None:
                continue
            for ref in self.schema.refs:
                if ref.child != row.table or ref.parent in MASTERS or ref.parent == "import_job":
                    continue
                v = row.data.get(ref.col)
                if v is None or ref.parent in CONTEXT_TABLES or ref.parent == row.table and v == row.pk:
                    continue
                if ref.pcol == self.schema.pk.get(ref.parent) and (ref.parent, v) in self.rows:
                    continue
                row.kind, row.real = f"real {ref.parent}", f"{ref.col} -> {ref.parent} {v}, which is not test data"
                break

    # ---------------------------------------------------------------- decide
    def _decide(self) -> None:
        self.tree: dict[tuple[str, int], list[Row]] = defaultdict(list)
        for row in self.rows.values():
            for o in row.origins:
                self.tree[o].append(row)
        records = [(t, i) for t, ids in self.test.items() for i in ids]
        self.blocked: dict[tuple[str, int], str] = {}
        for rec in records:
            real = [r for r in self.tree[rec] if r.real is not None]
            if real:
                self.blocked[rec] = f"{real[0].table} {real[0].pk}: {real[0].real}" + (
                    f" (+{len(real) - 1} more real rows)" if len(real) > 1 else ""
                )
        # A record stays too when its rows include another test record that stays, or a row that belongs to a
        # case, order or other row that stays (removing it would leave that record half-emptied).
        changed = True
        while changed:
            changed = False
            self._collect()
            for rec in records:
                if rec in self.blocked:
                    continue
                why = self._stays_with(rec)
                if why:
                    self.blocked[rec] = why
                    changed = True

    def _collect(self) -> None:
        self.removable = [(t, i) for t, ids in self.test.items() for i in ids if (t, i) not in self.blocked]
        self.doomed = {(r.table, r.pk): r for rec in self.removable for r in self.tree[rec]}

    def _stays_with(self, rec: tuple[str, int]) -> str | None:
        for r in self.tree[rec]:
            other = (r.table, r.pk)
            if r.table in MASTERS and other != rec and other in self.blocked:
                return f"depends on {master_label(self.conn, *other)}, which stays"
            for ref in self.schema.refs:
                if ref.child != r.table or ref.parent in MASTERS or ref.parent in CONTEXT_TABLES or ref.parent == "import_job":
                    continue
                parent = (ref.parent, r.data.get(ref.col))
                if parent[1] is not None and parent in self.rows and parent not in self.doomed:
                    return f"{r.table} {r.pk} belongs to {ref.parent} {parent[1]}, which stays"
        return None

    def fingerprint(self) -> str:
        keys = sorted(f"{t}:{pk}" for t, pk in self.doomed)
        return hashlib.sha256("\n".join(keys).encode()).hexdigest()[:16]

    def delete_order(self) -> list[str]:
        """Children before parents: a table goes once no table still to go points at it."""
        tables = {t for t, _ in self.doomed}
        parents = {t: {r.parent for r in self.schema.refs if r.child == t and r.parent in tables and r.parent != t} for t in tables}
        order: list[str] = []
        while parents:
            ready = sorted(t for t in parents if not any(t in ps for u, ps in parents.items() if u != t))
            if not ready:
                raise RuntimeError(f"foreign keys form a cycle among {sorted(parents)}")
            for t in ready:
                order.append(t)
                parents.pop(t)
        return order


def report(plan: Plan, say) -> None:
    conn = plan.conn
    say(f"test records: customers {len(plan.test['dim_customer'])}, distributors {len(plan.test['dim_distributor'])}, "
        f"products {len(plan.test['dim_product'])}")
    if plan.missing_pk:
        say(f"  tables without a single-column primary key, not followed: {sorted(plan.missing_pk)}")
    for table in MASTERS:
        say(f"\n== {MASTERS[table]}s")
        for eid in sorted(plan.test[table]):
            rec = (table, eid)
            verdict = "KEEP: " + plan.blocked[rec] if rec in plan.blocked else "REMOVE"
            say(f"  {MASTERS[table]} {eid} {plan.test[table][eid]}  -> {verdict}")
            counts: dict[tuple[str, str], int] = defaultdict(int)
            for r in plan.tree[rec]:
                if (r.table, r.pk) == rec:
                    continue
                counts[(r.table, r.kind)] += 1
            for (t, kind), n in sorted(counts.items()):
                say(f"      {t:<44} {n:>6}  {kind}")
    by_table: dict[str, int] = defaultdict(int)
    for t, _ in plan.doomed:
        by_table[t] += 1
    say("\n== Summary")
    for table in MASTERS:
        rem = [i for t, i in plan.removable if t == table]
        say(f"  {MASTERS[table]}s: remove {len(rem)}, keep {len(plan.test[table]) - len(rem)}")
    say(f"  rows to remove: {sum(by_table.values())} in {len(by_table)} tables (plan {plan.fingerprint()})")
    for t, n in sorted(by_table.items()):
        say(f"      {t:<44} {n:>6}")
    kept = sorted(plan.blocked.items())
    say(f"  kept for you to look at: {len(kept)}")
    for (t, i), why in kept:
        say(f"      {master_label(conn, t, i)}: {why}")


def preflight(plan: Plan) -> list[str]:
    """Tables the current role cannot delete from (privilege, or row security with no DELETE policy)."""
    problems = []
    for t in sorted({t for t, _ in plan.doomed}):
        if not plan.conn.execute(text("SELECT has_table_privilege(current_user, :t, 'DELETE')"), {"t": t}).scalar():
            problems.append(f"{t}: no DELETE privilege")
            continue
        bypass = plan.conn.execute(
            text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).scalar()
        if t in plan.schema.rls and not bypass:
            ok = plan.conn.execute(
                text("SELECT count(*) FROM pg_policies WHERE schemaname = 'public' AND tablename = :t AND cmd IN ('DELETE', 'ALL')"),
                {"t": t},
            ).scalar()
            if not ok:
                problems.append(f"{t}: row security on and no DELETE policy")
    return problems


def apply(plan: Plan, say, *, fail_before_commit: bool = False) -> dict[str, int]:
    conn = plan.conn
    for table in MASTERS:
        ids = [i for t, i in plan.removable if t == table]
        if ids:
            conn.execute(text(f"SELECT id FROM {table} WHERE id = ANY(:ids) FOR UPDATE"), {"ids": ids})
    by_table: dict[str, list[Any]] = defaultdict(list)
    for t, pk in plan.doomed:
        by_table[t].append(pk)
    # Self-references inside the removed set (merged_into …) are cleared first, then children go before parents.
    for ref in plan.schema.refs:
        if ref.child == ref.parent and ref.child in by_table:
            conn.execute(
                text(f"UPDATE {ref.child} SET {ref.col} = NULL WHERE {plan.schema.pk[ref.child]} = ANY(:ids) AND {ref.col} IS NOT NULL"),
                {"ids": by_table[ref.child]},
            )
    removed: dict[str, int] = {}
    for t in plan.delete_order():
        n = conn.execute(
            text(f"DELETE FROM {t} WHERE {plan.schema.pk[t]} = ANY(:ids)"), {"ids": by_table[t]}
        ).rowcount
        if n != len(by_table[t]):
            raise RuntimeError(f"{t}: deleted {n} rows, plan says {len(by_table[t])}")
        removed[t] = n
    from app.services.platform_audit import record_platform_audit_sync
    from sqlalchemy.orm import Session

    with Session(bind=conn) as session:
        record_platform_audit_sync(
            session,
            None,
            area="admin",
            action="test_masters_cleanup",
            target_type="test_masters",
            target_id=plan.fingerprint(),
            actor_label="scripts/ops/cleanup_test_masters.py",
            detail={
                "removed_records": {MASTERS[t]: sorted(i for tt, i in plan.removable if tt == t) for t in MASTERS},
                "kept_records": {f"{MASTERS[t]} {i}": why for (t, i), why in sorted(plan.blocked.items())},
                "counts": removed,
                # Every removed row in full, as it was before the delete.
                "rows_removed": {t: [plan.doomed[(t, pk)].data for pk in sorted(by_table[t], key=str)] for t in sorted(by_table)},
            },
        )
        session.flush()
    if fail_before_commit:
        raise RuntimeError("forced failure before commit (proof of all or nothing)")
    say(f"removed: {sum(removed.values())} rows ({', '.join(f'{t} {n}' for t, n in sorted(removed.items()))})")
    return removed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="remove the removable records (needs --expect-db)")
    p.add_argument("--expect-db", default=None, help="required with --apply; must equal current_database()")
    p.add_argument("--out", default=None, help="also write the report to this file")
    p.add_argument("--fail-before-commit", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    lines: list[str] = []

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        lines.append(msg)

    from app.db.session_sync import sync_engine

    code = 0
    with sync_engine.connect() as conn:
        if not args.apply:
            # The session setting applies from the next transaction, so end the one the SET opened.
            conn.exec_driver_sql("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            conn.commit()
        db = conn.execute(text("SELECT current_database()")).scalar()
        role = conn.execute(text("SELECT current_user")).scalar()
        ro = conn.execute(text("SHOW transaction_read_only")).scalar()
        say(f"current_database() = {db}; role {role}; transaction_read_only = {ro}; "
            f"{'APPLY' if args.apply else 'dry run, nothing is changed'}")
        if args.apply and args.expect_db != db:
            say(f"refused: --apply needs --expect-db {db!r} (got {args.expect_db!r})")
            return 2
        if not args.apply and ro != "on":
            say("STOP: the dry run is not read-only")
            return 2
        plan = Plan(conn)
        report(plan, say)
        problems = preflight(plan)
        say("  preflight: " + ("; ".join(problems) if problems else f"role {role} can delete from every table in the plan"))
        if args.apply:
            if problems:
                say("refused: fix the preflight first; nothing changed")
                conn.rollback()
                code = 2
            else:
                try:
                    apply(plan, say, fail_before_commit=args.fail_before_commit)
                    conn.commit()
                    say("committed")
                except Exception as exc:  # noqa: BLE001 - any failure rolls everything back
                    conn.rollback()
                    say(f"ROLLED BACK, nothing changed: {exc}")
                    code = 3
        else:
            conn.rollback()
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
