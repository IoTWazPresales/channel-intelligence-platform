"""N-0065 rounds 3-5: row-security parity, migrations 0024 vs 0025 vs 0026 vs 0027 (cip_test only).

For each version, on a fresh connection, in ONE transaction that is always rolled back:
  * cip_test is at 20261009_0027; every run first applies 0027's own downgrade() (to 0026);
    the 0025 run then 0026's downgrade(), the 0024 run also 0025's downgrade(); the 0027 run
    applies 0027's downgrade() and then upgrade(), so it measures this round's upgrade();
  * fixture products on three lines (plus a NULL-line product) are added to dim_product;
  * every protected table gets one synthetic row per fixture product, one NULL-product row
    and one orphan-product row (FK/CHECK constraints, NOT NULL and user triggers are
    relaxed inside the transaction so any table can take them);
  * the base rows are read with row security off for the owner (NO FORCE), which is
    independent of either policy, and the expected visible rows are computed in Python from
    product_line membership;
  * every scope is then measured as role cip under the real policies (FORCE on):
    SELECT per product id, UPDATE/DELETE row counts, INSERT and UPDATE-to-another-product
    allowed or denied.

A policy decides only by the product id, so the multiset of visible product ids is the
visible row set exactly.

Expected differences 0025 -> 0026, by design (Warren 2026-10-08, round 4): on the three
lineage tables (shipment_evidence_observation, shipment_evidence_line, fact_inbound_shipment)
a row with no product is readable, updatable and deletable only under an open scope or by
role 'steward' (the synthetic rows have no identity, so they are "truly unresolved");
WITH CHECK is unchanged. Inheritance from a resolved identity and the view's current pick
are covered by test_shipment_evidence_lineage_rls_n0065_db.py.

Expected differences 0026 -> 0027, by design (Warren 2026-10-09, round 5): on
commercial_lineup_line, cst_listing_seed, customer_listing and historical_lineup_import_line
a row with no product is readable, updatable and deletable only under an open scope or by
role 'steward'; WITH CHECK is unchanged. 0027 also sets enable_sort = off and
enable_incremental_sort = off on the current pick (plan only, no row difference).

Expected differences 0024 -> 0025, by design (approved 2026-10-07):
  * '' : 0024 no lines; 0025 open (a pooled backend's leftover value). The app writes '!'.
  * '!': 0024 a line nobody has (no lines); 0025 the "no lines" sentinel. Same result.
  * orphan product ids (no dim_product row) under an open scope: 0024 hid them (the per-row
    EXISTS ran first); 0025 shows them (open means open). Hidden under any line list.
  * an edit line the caller cannot read (never produced by the app, where edit is a subset
    of read): 0025's inner dim_product read runs under dim_product's own policy, so it is
    not editable. 0024 matched when its SECURITY DEFINER owner is subject to row security
    (cip_test: owner cip, FORCE); on cip (owner postgres) 0024 allowed it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import uuid
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_M25 = "20261007_0025_product_line_rls_inline.py"
_M26 = "20261009_0026_shipment_evidence_lineage_rls.py"
_M27 = "20261009_0027_current_pick_index_order_no_product_steward.py"
LINEAGE = frozenset({"shipment_evidence_observation", "shipment_evidence_line", "fact_inbound_shipment"})
# Round 5 (0027): rows with no product are admin (open) / steward only, no inheritance.
NO_PRODUCT_STEWARD = frozenset(
    {"commercial_lineup_line", "cst_listing_seed", "customer_listing", "historical_lineup_import_line"})
# N-0096: append-only audit tables have SELECT and INSERT policies and deliberately no UPDATE or DELETE
# policy (N-0110 repair, 20261015_0038), so the update/delete/move cells of this matrix do not apply to
# them. They are left out of the measured set and checked for their policy shape below.
APPEND_ONLY = frozenset({"fact_customer_sellthrough_superseded", "fact_distributor_line_superseded"})
STEWARD = "steward"
ALL = "ALL"
NULL_PID = None


def _load(fname: str):
    spec = importlib.util.spec_from_file_location("_mig_" + fname.split("_")[1], _VERSIONS / fname)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _engine():
    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, poolclass=NullPool)


# ---------------------------------------------------------------- semantics (independent model)


def allowed(v: str | None, ver: int):
    if v is None:
        return ALL
    if ver >= 25 and v in ("", "*"):
        return ALL
    if ver == 24 and v == "*":
        return ALL
    if v == "":
        return frozenset()  # 0024: string_to_array('', ',') is empty
    if ver >= 25 and v == "!":
        return frozenset()
    return frozenset(v.split(","))


def line_ok(line: str | None, v: str | None, ver: int) -> bool:
    a = allowed(v, ver)
    return a == ALL or (line is not None and line in a)


def visible(pid, r, ver, lines, table=None, role=None) -> bool:
    if pid is None:
        if (ver >= 26 and table in LINEAGE) or (ver >= 27 and table in NO_PRODUCT_STEWARD):
            return allowed(r, 25) == ALL or role == STEWARD
        return True
    if ver >= 25 and allowed(r, 25) == ALL:
        return True
    if pid not in lines:
        return False
    return line_ok(lines[pid], r, 25 if ver >= 25 else ver)


def editable(pid, r, e, ver, lines, definer_rls: bool, table=None, role=None, check=False) -> bool:
    """UPDATE/DELETE USING (check=False) or INSERT/UPDATE WITH CHECK (check=True)."""
    if pid is None:
        if ((ver >= 26 and table in LINEAGE) or (ver >= 27 and table in NO_PRODUCT_STEWARD)) and not check:
            return allowed(e, 25) == ALL or role == STEWARD
        return True
    if ver >= 25:
        if allowed(e, 25) == ALL:
            return True
        if pid not in lines:
            return False
        return line_ok(lines[pid], e, 25) and line_ok(lines[pid], r, 25)
    if pid not in lines:
        return False
    ok = line_ok(lines[pid], e, 24)
    if definer_rls:
        ok = ok and line_ok(lines[pid], r, 24)
    return ok


# ---------------------------------------------------------------- database helpers


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _relax(conn, table: str, col: str) -> dict:
    """Let the table take synthetic rows: drop FK/CHECK/EXCLUDE, NOT NULL (non-key), user triggers."""
    t = _q(table)
    for (name,) in conn.execute(
        text("select conname from pg_constraint where conrelid = cast(:t as regclass) and contype in ('f','c','x')"),
        {"t": f"public.{t}"},
    ).all():
        conn.execute(text(f"ALTER TABLE {t} DROP CONSTRAINT {_q(name)}"))
    pk_cols = [
        r[0]
        for r in conn.execute(
            text(
                """select a.attname from pg_index i
                   join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
                   where i.indrelid = cast(:t as regclass) and i.indisprimary"""
            ),
            {"t": f"public.{t}"},
        ).all()
    ]
    for (name,) in conn.execute(
        text(
            """select a.attname from pg_attribute a
               where a.attrelid = cast(:t as regclass) and a.attnum > 0 and not a.attisdropped
                 and a.attnotnull and a.attidentity = '' """
        ),
        {"t": f"public.{t}"},
    ).all():
        if name not in pk_cols:
            conn.execute(text(f"ALTER TABLE {t} ALTER COLUMN {_q(name)} DROP NOT NULL"))
    conn.execute(text(f"ALTER TABLE {t} DISABLE TRIGGER USER"))
    # Key columns that need a value (no default, not identity, not the product column).
    need = conn.execute(
        text(
            """select a.attname, format_type(a.atttypid, a.atttypmod)
               from pg_attribute a
               where a.attrelid = cast(:t as regclass) and a.attname = any(:pk)
                 and a.attidentity = '' and a.attgenerated = ''
                 and not exists (select 1 from pg_attrdef d where d.adrelid = a.attrelid and d.adnum = a.attnum)"""
        ),
        {"t": f"public.{t}", "pk": pk_cols},
    ).all()
    return {"pk": pk_cols, "need": [(n, ty) for n, ty in need if n != col]}


def _insert_sql(table: str, col: str, meta: dict, seq: list[int]) -> tuple[str, dict]:
    cols = [_q(col)]
    vals = [":pid"]
    params: dict = {}
    for i, (name, ty) in enumerate(meta["need"]):
        cols.append(_q(name))
        key = f"k{i}"
        if ty in ("integer", "bigint", "smallint"):
            seq[0] += 1
            vals.append(f"(select coalesce(max({_q(name)}), 0) + 1 from {_q(table)})")
        elif ty == "uuid":
            vals.append("gen_random_uuid()")
        else:
            vals.append(f"cast(:{key} as {ty})")
            params[key] = "n0065-" + uuid.uuid4().hex
    return f"INSERT INTO {_q(table)} ({', '.join(cols)}) VALUES ({', '.join(vals)})", params


def _bind(conn, r, e, role=None) -> None:
    if r is not None:
        conn.execute(text("select set_config('cip.product_lines', :v, true)"), {"v": r})
    if e is not None:
        conn.execute(text("select set_config('cip.editable_product_lines', :v, true)"), {"v": e})
    if role is not None:
        conn.execute(text("select set_config('cip.request_role', :v, true)"), {"v": role})


def _sp(conn, fn):
    """Run fn inside a savepoint that is always rolled back; returns (ok, value_or_sqlstate)."""
    sp = conn.begin_nested()
    try:
        return True, fn()
    except Exception as exc:  # noqa: BLE001 - classify below
        orig = getattr(exc, "orig", None)
        state = getattr(orig, "sqlstate", None) or getattr(getattr(orig, "diag", None), "sqlstate", None)
        msg = str(orig or exc)
        return False, ("RLS" if "row-level security" in msg else f"ERR:{state}")
    finally:
        if sp.is_active:
            sp.rollback()


READ_SCOPES = [None, "", "!", "*", "A", "A,B", "NOPE"]  # None must run first (fresh backend)
# Round 4: the request role (0026 lineage tables), steward and non-steward.
ROLE_READ_SCOPES = [("!", STEWARD), ("A", STEWARD), ("A", "planner"),
                    # Round 5: admin as the app binds it, a no-lines planner, a two-line viewer.
                    ("*", "admin"), ("!", "planner"), ("A,B", "viewer")]
ROLE_EDIT_SCOPES = [(("A", "!"), STEWARD), (("!", "!"), STEWARD), (("A,B", "A"), "planner"),
                    (("*", "*"), "admin"), (("!", "!"), "planner")]
EDIT_SCOPES = [
    (None, None),
    ("*", "*"),
    ("A,B", "A"),
    ("A,B", "A,B"),
    ("A", "!"),
    ("!", "!"),
    ("", ""),
    ("*", "A"),
    ("!", "A"),  # edit line not readable: unreachable from the app
]


def _expand(v: str | None, names: dict[str, str]) -> str | None:
    if v is None or v in ("", "!", "*"):
        return v
    return ",".join(names.get(x, x) for x in v.split(","))


def run_version(ver: int) -> dict:
    eng = _engine()
    conn = eng.connect()
    try:
        db = conn.execute(text("select current_database()")).scalar_one()
        if db != "cip_test":
            pytest.skip(f"parity runs on cip_test only (current_database()={db})")
        conn.rollback()
        tx = conn.begin()
        out: dict = {"ver": ver, "tables": {}}
        try:
            from alembic.operations import Operations
            from alembic.runtime.migration import MigrationContext

            rev = conn.execute(text("select version_num from alembic_version")).scalar_one()
            # N-0096: cip_test moves on with every migration. The parity run needs 0027 applied, not
            # to be the head: 0027 must be the head itself or an ancestor of it.
            from alembic.config import Config
            from alembic.script import ScriptDirectory

            script = ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")))
            lineage = {r.revision for r in script.walk_revisions(base="base", head=rev)}
            assert "20261009_0027" in lineage, f"cip_test must have 0027 applied for the parity run, is {rev}"
            m25 = _load(_M25)
            m26 = _load(_M26)
            m27 = _load(_M27)
            with Operations.context(MigrationContext.configure(conn)):
                m27.downgrade()  # 0026 state, from 0027's own downgrade
                if ver <= 25:
                    m26.downgrade()  # 0025 policies and view, from 0026's own downgrade
                if ver == 24:
                    m25.downgrade()  # 0024 policies, from 0025's own downgrade
                if ver == 27:
                    m27.upgrade()  # and back: the 0027 run measures this file's upgrade()
            # Fresh backend: the settings have never been set here.
            assert conn.execute(text("select current_setting('cip.product_lines', true)")).scalar_one() is None
            definer = conn.execute(
                text(
                    """select r.rolsuper or r.rolbypassrls from pg_proc p join pg_roles r on r.oid = p.proowner
                       where p.proname = 'cip_product_id_editable'"""
                )
            ).scalar_one()
            definer_rls = not bool(definer)
            out["definer_bypasses_rls"] = bool(definer)
            tables = [(t, c) for t, c in m25.protected_tables(conn) if t not in APPEND_ONLY]
            out["n_tables"] = len(tables) + 1
            tag = uuid.uuid4().hex[:6]
            names = {"A": f"N0065P-A-{tag}", "B": f"N0065P-B-{tag}", "C": f"N0065P-C-{tag}"}
            fixture = []
            for i, line in enumerate([names["A"], names["A"], names["B"], names["B"], names["C"], None]):
                pid = conn.execute(
                    text(
                        "insert into dim_product (sku, name, is_active, product_line) "
                        "values (:s, :n, true, :l) returning id"
                    ),
                    {"s": f"N0065P-{tag}-{i}", "n": f"N0065 parity {i}", "l": line},
                ).scalar_one()
                fixture.append(int(pid))
            orphan = int(conn.execute(text("select coalesce(max(id), 0) + 1000000 from dim_product")).scalar_one())
            samples = {"A": fixture[0], "B": fixture[2], "C": fixture[4], "NULL_LINE": fixture[5],
                       "NULL_PID": None, "ORPHAN": orphan}
            # Seed and read the base rows with row security off for the owner (independent
            # of both policies; 0024 would refuse the orphan row even when unset).
            all_tabs = ["dim_product"] + [t for t, _ in tables]
            for t in all_tabs:
                conn.execute(text(f"ALTER TABLE {_q(t)} NO FORCE ROW LEVEL SECURITY"))
            metas = {}
            for table, col in tables:
                meta = _relax(conn, table, col)
                metas[table] = meta
                seq = [0]
                for pid in fixture + [orphan] + ([None] if col not in meta["pk"] else []):
                    sql, params = _insert_sql(table, col, meta, seq)
                    conn.execute(text(sql), {**params, "pid": pid})
            lines = {int(i): l for i, l in conn.execute(text("select id, product_line from dim_product")).all()}
            base = {}
            for table, col in tables:
                base[table] = Counter(
                    {(None if p is None else int(p)): int(n) for p, n in conn.execute(
                        text(f"select {_q(col)}, count(*) from {_q(table)} group by 1")).all()}
                )
            base_dim = Counter(dict(conn.execute(text("select product_line, count(*) from dim_product group by 1")).all()))
            for t in all_tabs:
                conn.execute(text(f"ALTER TABLE {_q(t)} FORCE ROW LEVEL SECURITY"))

            # ---------- reads
            def read_cell(r_raw, role=None):
                r = _expand(r_raw, names)
                lbl = f"read {r_raw!r}" + (f" role={role}" if role else "")
                if r_raw is None:
                    assert conn.execute(text("select current_setting('cip.product_lines', true)")).scalar_one() is None

                def measure():
                    _bind(conn, r, None, role)
                    res = {}
                    for table, col in tables:
                        res[table] = Counter({(None if p is None else int(p)): int(n) for p, n in conn.execute(
                            text(f"select {_q(col)}, count(*) from {_q(table)} group by 1")).all()})
                    res["dim_product"] = Counter(dict(conn.execute(
                        text("select product_line, count(*) from dim_product group by 1")).all()))
                    res["__view__"] = int(conn.execute(text("select count(*) from shipment_evidence_current")).scalar_one())
                    return res

                ok, got = _sp(conn, measure)
                assert ok, (ver, r_raw, role, got)
                for table, _col in tables:
                    exp = Counter({p: n for p, n in base[table].items() if visible(p, r, ver, lines, table, role)})
                    cell = out["tables"].setdefault(table, {})
                    cell[lbl] = {"got": sum(got[table].values()), "exp": sum(exp.values()),
                                 "match": got[table] == exp}
                exp_dim = Counter({l: n for l, n in base_dim.items() if line_ok(l, r, ver)})
                out["tables"].setdefault("dim_product", {})[lbl] = {
                    "got": sum(got["dim_product"].values()), "exp": sum(exp_dim.values()),
                    "match": got["dim_product"] == exp_dim}
                out.setdefault("view", {})[lbl] = got["__view__"]

            # ---------- edits
            def edit_cell(r_raw, e_raw, role=None):
                r, e = _expand(r_raw, names), _expand(e_raw, names)
                label = f"edit r={r_raw!r} e={e_raw!r}" + (f" role={role}" if role else "")
                if r_raw is None and e_raw is None:
                    assert conn.execute(text(
                        "select current_setting('cip.editable_product_lines', true)")).scalar_one() is None
                for table, col in tables:
                    cell = out["tables"][table]  # noqa: B023
                    exp_upd = sum(n for p, n in base[table].items()
                                  if visible(p, r, ver, lines, table, role)
                                  and editable(p, r, e, ver, lines, definer_rls, table, role))
                    exp_del = sum(n for p, n in base[table].items()
                                  if editable(p, r, e, ver, lines, definer_rls, table, role))

                    def upd():
                        _bind(conn, r, e, role)
                        return conn.execute(text(f"UPDATE {_q(table)} SET {_q(col)} = {_q(col)}")).rowcount

                    def dele():
                        _bind(conn, r, e, role)
                        return conn.execute(text(f"DELETE FROM {_q(table)}")).rowcount

                    ok_u, n_u = _sp(conn, upd)
                    ok_d, n_d = _sp(conn, dele)
                    ins = {}
                    for sname, pid in samples.items():
                        if pid is None and col in metas[table]["pk"]:
                            continue
                        sql, params = _insert_sql(table, col, metas[table], [0])

                        def do_ins(sql=sql, params=params, pid=pid):
                            _bind(conn, r, e, role)
                            conn.execute(text(sql), {**params, "pid": pid})
                            return "ok"

                        ok_i, v_i = _sp(conn, do_ins)
                        allowed_i = ok_i or v_i != "RLS"
                        ins[sname] = {"allowed": allowed_i,
                                      "exp": editable(pid, r, e, ver, lines, definer_rls, table, role, check=True),
                                      "raw": v_i}
                    # Move an editable row to another product (UPDATE WITH CHECK on the new row).
                    move = {}
                    src = next((p for p in fixture if visible(p, r, ver, lines, table, role)
                                and editable(p, r, e, ver, lines, definer_rls, table, role)), None)
                    if src is not None:
                        for sname, pid in samples.items():
                            if pid is None and col in metas[table]["pk"]:
                                continue

                            def do_move(pid=pid, src=src):
                                _bind(conn, r, e, role)
                                return conn.execute(
                                    text(f"UPDATE {_q(table)} SET {_q(col)} = :to WHERE {_q(col)} = :src"),
                                    {"to": pid, "src": src}).rowcount

                            ok_m, v_m = _sp(conn, do_move)
                            # WITH CHECK on the new row; the WHERE reads the column, so the
                            # SELECT policy applies to the new row as well.
                            move[sname] = {"allowed": ok_m or v_m != "RLS",
                                           "exp": editable(pid, r, e, ver, lines, definer_rls, table, role, check=True)
                                           and visible(pid, r, ver, lines, table, role), "raw": v_m}
                    cell[label] = {
                        "update": n_u if ok_u else n_u, "update_exp": exp_upd,
                        "delete": n_d if ok_d else n_d, "delete_exp_edit_only": exp_del,
                        "insert": ins, "move": move,
                        "match": (ok_u and n_u == exp_upd)
                        and all(v["allowed"] == v["exp"] for v in ins.values())
                        and all(v["allowed"] == v["exp"] for v in move.values()),
                    }
                # dim_product edits by line
                cell = out["tables"]["dim_product"]
                exp_upd = sum(n for l, n in base_dim.items() if line_ok(l, r, ver) and line_ok(l, e, ver))

                def upd_dim():
                    _bind(conn, r, e, role)
                    return conn.execute(text("UPDATE dim_product SET product_line = product_line")).rowcount

                ok_u, n_u = _sp(conn, upd_dim)
                ins = {}
                for sname in ("A", "B", "C", "NULL_LINE"):
                    line = names.get(sname)

                    def do_ins_dim(line=line):
                        _bind(conn, r, e, role)
                        conn.execute(text("insert into dim_product (sku, name, is_active, product_line) "
                                          "values (:s, 'n0065 ins', true, :l)"),
                                     {"s": "N0065I-" + uuid.uuid4().hex, "l": line})
                        return "ok"

                    ok_i, v_i = _sp(conn, do_ins_dim)
                    ins[sname] = {"allowed": ok_i or v_i != "RLS", "exp": line_ok(line, e, ver), "raw": v_i}
                cell[label] = {"update": n_u, "update_exp": exp_upd, "insert": ins,
                               "match": ok_u and n_u == exp_upd and all(v["allowed"] == v["exp"] for v in ins.values())}

            # The genuinely unset cells first: once a backend has set the settings, even a
            # rolled-back savepoint leaves them defined as ''.
            out["tables"].setdefault("dim_product", {})
            for table, _col in tables:
                out["tables"].setdefault(table, {})
            edit_cell(None, None)
            read_cell(None)
            for r_raw in READ_SCOPES[1:]:
                read_cell(r_raw)
            for r_raw, e_raw in EDIT_SCOPES[1:]:
                edit_cell(r_raw, e_raw)
            for r_raw, role in ROLE_READ_SCOPES:
                read_cell(r_raw, role)
            for (r_raw, e_raw), role in ROLE_EDIT_SCOPES:
                edit_cell(r_raw, e_raw, role)
            out["setting_after_rollbacks"] = conn.execute(
                text("select current_setting('cip.product_lines', true)")).scalar_one()

            # ---------- plan shape (one fact table, one line)
            def plan():
                _bind(conn, names["A"], None)
                rows = conn.execute(text("EXPLAIN (COSTS OFF) SELECT count(*) FROM fact_sales_sellout")).all()
                return [x[0] for x in rows]

            ok, out["plan_one_line"] = _sp(conn, plan)
            out["view_reloptions"] = conn.execute(
                text("select reloptions from pg_class where relname = 'shipment_evidence_current'")).scalar_one()
            out["pick_config"] = conn.execute(text(
                "select proconfig from pg_proc where proname = 'cip_sev_current_observation_ids'")).scalar()
        finally:
            tx.rollback()
        return out
    finally:
        conn.close()
        eng.dispose()


def _summary(res: dict) -> dict:
    bad = []
    for table, cells in res["tables"].items():
        for label, cell in cells.items():
            if not cell.get("match"):
                bad.append((table, label, cell))
    return {"cells": sum(len(c) for c in res["tables"].values()), "mismatches": bad}


def _same(ca: dict, cb: dict, label: str) -> bool:
    if label.startswith("read"):
        return ca["got"] == cb["got"]
    return (ca["update"] == cb["update"]
            and {k: v["allowed"] for k, v in ca["insert"].items()}
            == {k: v["allowed"] for k, v in cb["insert"].items()}
            and {k: v["allowed"] for k, v in ca.get("move", {}).items()}
            == {k: v["allowed"] for k, v in cb.get("move", {}).items()})


def test_parity_0024_to_0027_every_protected_table() -> None:
    r24 = run_version(24)
    r25 = run_version(25)
    r26 = run_version(26)
    r27 = run_version(27)
    s24, s25, s26, s27 = _summary(r24), _summary(r25), _summary(r26), _summary(r27)
    report = {
        "n_tables": r25["n_tables"],
        "definer_bypasses_rls": r24["definer_bypasses_rls"],
        "cells_0024": s24["cells"], "mismatches_0024": s24["mismatches"],
        "cells_0025": s25["cells"], "mismatches_0025": s25["mismatches"],
        "cells_0026": s26["cells"], "mismatches_0026": s26["mismatches"],
        "cells_0027": s27["cells"], "mismatches_0027": s27["mismatches"],
        "view_counts_0024": r24["view"], "view_counts_0025": r25["view"], "view_counts_0026": r26["view"],
        "view_counts_0027": r27["view"],
        "view_reloptions_0024": r24["view_reloptions"], "view_reloptions_0025": r25["view_reloptions"],
        "view_reloptions_0026": r26["view_reloptions"], "view_reloptions_0027": r27["view_reloptions"],
        "pick_config_0026": r26["pick_config"], "pick_config_0027": r27["pick_config"],
        "plan_0024": r24["plan_one_line"], "plan_0025": r25["plan_one_line"], "plan_0026": r26["plan_one_line"],
        "plan_0027": r27["plan_one_line"],
    }
    # 0026 -> 0027: differences only on the four no-product tables (by design).
    cross27 = [(t, lbl) for t in r27["tables"] for lbl, c27 in r27["tables"][t].items()
               if not _same(r26["tables"][t][lbl], c27, lbl)]
    report["cross_0026_0027"] = cross27
    report["per_table_0027"] = {
        t: {lbl: (c["got"] if lbl.startswith("read") else c["update"]) for lbl, c in cells.items()}
        for t, cells in r27["tables"].items() if t in NO_PRODUCT_STEWARD
    }
    # 0025 -> 0026: differences only on the lineage tables (no-product rows, by design).
    cross26 = [(t, lbl) for t in r26["tables"] for lbl, c26 in r26["tables"][t].items()
               if not _same(r25["tables"][t][lbl], c26, lbl)]
    report["cross_0025_0026"] = cross26
    report["per_table_0026"] = {
        t: {lbl: (c["got"] if lbl.startswith("read") else c["update"]) for lbl, c in cells.items()}
        for t, cells in r26["tables"].items() if t in LINEAGE
    }
    # Cross-version: identical cells except the designed differences.
    designed = {"read ''", "edit r='' e=''", "edit r='!' e='A'"}
    cross = []
    for table in r25["tables"]:
        for label, c25 in r25["tables"][table].items():
            c24 = r24["tables"][table][label]
            if label.startswith("read"):
                same = c24["got"] == c25["got"]
            else:
                same = (c24["update"] == c25["update"]
                        and {k: v["allowed"] for k, v in c24["insert"].items()}
                        == {k: v["allowed"] for k, v in c25["insert"].items()}
                        and {k: v["allowed"] for k, v in c24.get("move", {}).items()}
                        == {k: v["allowed"] for k, v in c25.get("move", {}).items()})
            if not same:
                cross.append((table, label, label in designed))
    report["cross_version_differences"] = cross
    report["per_table_0025"] = {
        t: {lbl: (c["got"] if lbl.startswith("read") else c["update"]) for lbl, c in cells.items()}
        for t, cells in r25["tables"].items()
    }
    out = os.environ.get("N0065_PARITY_OUT")
    if out:
        Path(out).write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if not k.startswith("per_table")}, indent=1,
                     default=str)[:20000])
    # 45 when written; N-0087 dropped four scaffold tables (20261011_0032), and the append-only
    # superseded table is measured separately (APPEND_ONLY). A new protected table must be added here.
    assert r25["n_tables"] == 42 and r26["n_tables"] == 42 and r27["n_tables"] == 42
    assert not s24["mismatches"], s24["mismatches"][:5]
    assert not s25["mismatches"], s25["mismatches"][:5]
    assert not s26["mismatches"], s26["mismatches"][:5]
    assert not s27["mismatches"], s27["mismatches"][:5]
    assert cross26, "0026 must differ from 0025 on the lineage tables"
    assert {t for t, _ in cross26} <= LINEAGE, cross26
    assert {t for t, _ in cross27} == NO_PRODUCT_STEWARD, cross27
    assert r26["view_reloptions"] and "security_invoker=true" in r26["view_reloptions"]
    assert r27["view_reloptions"] and "security_invoker=true" in r27["view_reloptions"]
    assert r27["pick_config"] and "enable_sort=off" in r27["pick_config"], r27["pick_config"]
    assert "enable_incremental_sort=off" in r27["pick_config"], r27["pick_config"]
    assert "enable_sort=off" not in (r26["pick_config"] or []), r26["pick_config"]
    assert "enable_incremental_sort=off" not in (r26["pick_config"] or []), r26["pick_config"]
    plan27 = "\n".join(r27["plan_one_line"])
    assert "cip_product_id_visible" not in plan27 and "hashed SubPlan" in plan27, plan27
    plan26 = "\n".join(r26["plan_one_line"])
    assert "cip_product_id_visible" not in plan26 and "hashed SubPlan" in plan26, plan26
    # Orphan rows under open scopes are the one data-dependent designed difference: exactly
    # the one orphan row per table, visible and updatable under 0025, hidden under 0024.
    open_labels = ("read None", "read '*'", "edit r=None e=None", "edit r='*' e='*'",
                   "read '*' role=admin", "edit r='*' e='*' role=admin")
    undesigned = []
    for table, label, is_designed in cross:
        if is_designed:
            continue
        if label in open_labels and table != "dim_product":
            c24, c25 = r24["tables"][table][label], r25["tables"][table][label]
            key = "got" if label.startswith("read") else "update"
            if c25[key] - c24[key] == 1:
                continue
        undesigned.append((table, label))
    assert not undesigned, undesigned[:10]
    assert r25["view_reloptions"] and "security_invoker=true" in r25["view_reloptions"]
    plan25 = "\n".join(r25["plan_one_line"])
    assert "cip_product_id_visible" not in plan25 and "hashed SubPlan" in plan25, plan25


def test_append_only_audit_tables_have_select_and_insert_policies_and_no_update_or_delete():
    eng = _engine()
    try:
        with eng.connect() as conn:
            if conn.execute(text("select current_database()")).scalar_one() != "cip_test":
                pytest.skip("policy shape is read on cip_test only")
            for table in sorted(APPEND_ONLY):
                if not conn.execute(text("select to_regclass(:t)"), {"t": table}).scalar_one():
                    pytest.skip(f"{table} is not on this database")
                cmds = {
                    r[0]: r[1]
                    for r in conn.execute(
                        text("select cmd, policyname from pg_policies where tablename = :t"), {"t": table}
                    )
                }
                assert sorted(cmds) == ["INSERT", "SELECT"], (table, cmds)
                rls = conn.execute(
                    text("select relrowsecurity, relforcerowsecurity from pg_class where relname = :t"),
                    {"t": table},
                ).one()
                assert tuple(rls) == (True, True), table
    finally:
        eng.dispose()
