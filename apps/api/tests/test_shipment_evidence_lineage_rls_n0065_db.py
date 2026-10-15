"""N-0065 rounds 4-5 (migrations 20261009_0026/0027): shipment evidence lineage under row security, cip_test only.

Round 5 (0027, Warren 2026-10-09) adds, at the end of this module: the current pick walks
ix_shipment_ev_obs_identity_latest in order (function-level enable_sort = off and enable_incremental_sort = off; same rows),
and rows with no product in commercial_lineup_line, cst_listing_seed, customer_listing and
historical_lineup_import_line are visible/editable only under an open scope or to stewards.

GOV-008 VER2 S3/F1: under 0025 a narrow scope saw stale observations with no product of
identities whose current row is another line, and every row with no product was visible to
everyone. Warren's decision (2026-10-08): a row with no product inherits the line of its
identity's resolved observation; with none it is visible only to admins (open scope) and
stewards; ``shipment_evidence_current`` picks the current row before row security applies.

Fixture (one transaction, always rolled back; constraints relaxed inside it):
  products pA (line A), pB (line B)
  K1: older observation O1o with no product (line L1o, no product), newer O1n on pB (L1n on pB)
  K2: one observation O2 with no product (L2, no product): truly unresolved
  K3: one observation O3 on pA (L3 on pA)
  K4: older observation O4o on pA (L5o), newer O4n on pB (L5n): re-resolved to another line, so
      only a scope-independent current pick keeps O4o from surfacing as "current" for line A
  L4: a line with no product and no observation
  inbound I1 -> L1o (no product), I2 -> L2 (no product), I3 no line (no product), I4 on pA
Each scope is bound with the app's own statement (product_line_scope_statement), measured as
role cip with FORCE row security, and the rows of the fixture are counted per table.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.product_line_scope import (
    product_line_scope_statement,
    request_editable_product_lines,
    request_product_lines,
    request_role,
)

TABLES = ("shipment_evidence_observation", "shipment_evidence_line", "fact_inbound_shipment")


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _relax(conn, table: str) -> None:
    t = _q(table)
    for (name,) in conn.execute(
        text("select conname from pg_constraint where conrelid = cast(:t as regclass) and contype in ('f','c','x')"),
        {"t": f"public.{t}"},
    ).all():
        conn.execute(text(f"ALTER TABLE {t} DROP CONSTRAINT {_q(name)}"))
    for (name,) in conn.execute(
        text(
            """select a.attname from pg_attribute a
               where a.attrelid = cast(:t as regclass) and a.attnum > 0 and not a.attisdropped
                 and a.attnotnull and a.attname <> 'id'"""
        ),
        {"t": f"public.{t}"},
    ).all():
        conn.execute(text(f"ALTER TABLE {t} ALTER COLUMN {_q(name)} DROP NOT NULL"))
    conn.execute(text(f"ALTER TABLE {t} DISABLE TRIGGER USER"))


@contextmanager
def _scope(read, edit, role):
    tokens = (request_product_lines.set(read), request_editable_product_lines.set(edit), request_role.set(role))
    try:
        yield
    finally:
        request_product_lines.reset(tokens[0])
        request_editable_product_lines.reset(tokens[1])
        request_role.reset(tokens[2])


def _applied(rev: str, target: str) -> bool:
    """N-0096: cip_test moves on with every migration; these tests need ``target`` applied, not to be
    the head. True when ``target`` is ``rev`` or one of its ancestors."""
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")))
    return target in {r.revision for r in script.walk_revisions(base="base", head=rev)}


@pytest.fixture()
def lineage():
    from app.core.config import get_settings

    get_settings.cache_clear()
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1),
                        poolclass=NullPool)
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"lineage test runs on cip_test only (current_database()={db})")
    rev = conn.execute(text("select version_num from alembic_version")).scalar_one()
    conn.rollback()
    tx = conn.begin()
    try:
        assert _applied(rev, "20261009_0026"), f"cip_test must have 0026 applied, is at {rev}"
        tag = uuid.uuid4().hex[:8]
        lines = {"A": f"N0065L-A-{tag}", "B": f"N0065L-B-{tag}"}
        for t in ("dim_product", *TABLES):
            conn.execute(text(f"ALTER TABLE {_q(t)} NO FORCE ROW LEVEL SECURITY"))
        for t in TABLES:
            _relax(conn, t)
        pid = {}
        for k in ("A", "B"):
            pid[k] = conn.execute(
                text("insert into dim_product (sku, name, is_active, product_line) values (:s, :n, true, :l) returning id"),
                {"s": f"N0065L-{tag}-{k}", "n": f"N0065 lineage {k}", "l": lines[k]},
            ).scalar_one()

        def line(product):
            return conn.execute(
                text("insert into shipment_evidence_line (product_id, item_code) values (:p, :i) returning id"),
                {"p": product, "i": f"N0065L-{tag}"},
            ).scalar_one()

        def obs(key, product, line_id, valid_from):
            return conn.execute(
                text(
                    """insert into shipment_evidence_observation
                       (line_identity_key, product_id, evidence_line_id, valid_from, item_code, quantity)
                       values (:k, :p, :l, cast(:v as timestamptz), :i, 1) returning id"""
                ),
                {"k": key, "p": product, "l": line_id, "v": valid_from, "i": f"N0065L-{tag}"},
            ).scalar_one()

        def inbound(product, line_id):
            return conn.execute(
                text("insert into fact_inbound_shipment (product_id, shipment_evidence_line_id) values (:p, :l) returning id"),
                {"p": product, "l": line_id},
            ).scalar_one()

        keys = {k: f"n0065lineage:{tag}:{k}" for k in ("K1", "K2", "K3", "K4")}
        L = {"L1o": line(None), "L1n": line(pid["B"]), "L2": line(None), "L3": line(pid["A"]), "L4": line(None),
             "L5o": line(pid["A"]), "L5n": line(pid["B"])}
        O = {
            "O1o": obs(keys["K1"], None, L["L1o"], "2026-01-01"),
            "O1n": obs(keys["K1"], pid["B"], L["L1n"], "2026-02-01"),
            "O2": obs(keys["K2"], None, L["L2"], "2026-01-01"),
            "O3": obs(keys["K3"], pid["A"], L["L3"], "2026-01-01"),
            "O4o": obs(keys["K4"], pid["A"], L["L5o"], "2026-01-01"),
            "O4n": obs(keys["K4"], pid["B"], L["L5n"], "2026-02-01"),
        }
        inb = {"I1": inbound(None, L["L1o"]), "I2": inbound(None, L["L2"]), "I3": inbound(None, None),
               "I4": inbound(pid["A"], L["L3"])}
        for t in ("dim_product", *TABLES):
            conn.execute(text(f"ALTER TABLE {_q(t)} FORCE ROW LEVEL SECURITY"))
        yield conn, lines, keys, {"shipment_evidence_observation": O, "shipment_evidence_line": L,
                                  "fact_inbound_shipment": inb}
    finally:
        tx.rollback()
        conn.close()
        eng.dispose()


def _names(ids: dict[str, int], got: set[int]) -> set[str]:
    return {n for n, i in ids.items() if i in got}


def _bind(conn, scope):
    """scope: None (worker), '' (pooled leftover) or (read set, edit set, role)."""
    if scope is None:
        return
    if scope == "":
        conn.execute(text("select set_config('cip.product_lines', '', true), "
                          "set_config('cip.editable_product_lines', '', true), set_config('cip.request_role', '', true)"))
        return
    stmt = product_line_scope_statement()
    assert stmt is not None
    conn.execute(text(stmt[0]), stmt[1])


def _measure(conn, lines, keys, fx, read, edit, role, raw=None):
    """Visible fixture rows per table and the view's current row per identity, in a savepoint."""
    sp = conn.begin_nested()
    try:
        expand = (lambda s: None if s is None else frozenset(lines.get(x, x) for x in s))
        with _scope(expand(read), expand(edit), role):
            _bind(conn, raw if raw is not None or read is None else (read, edit, role))
            setting_before = conn.execute(text("select current_setting('cip.product_lines', true)")).scalar()
            out = {}
            for t in TABLES:
                ids = fx[t]
                got = {r[0] for r in conn.execute(text(f"select id from {t} where id = any(:ids)"),
                                                  {"ids": list(ids.values())}).all()}
                out[t] = _names(ids, got)
            view = dict(conn.execute(text("select line_identity_key, id from shipment_evidence_current "
                                          "where line_identity_key = any(:k)"), {"k": list(keys.values())}).all())
            inv = {v: k for k, v in keys.items()}
            obs = fx["shipment_evidence_observation"]
            out["view"] = {inv[k]: next(n for n, i in obs.items() if i == v) for k, v in view.items()}
            # The helpers restore the caller's value: the setting is unchanged after the reads.
            assert conn.execute(text("select current_setting('cip.product_lines', true)")).scalar() == setting_before
            return out
    finally:
        sp.rollback()


ALL_ROWS = {
    "shipment_evidence_observation": {"O1o", "O1n", "O2", "O3", "O4o", "O4n"},
    "shipment_evidence_line": {"L1o", "L1n", "L2", "L3", "L4", "L5o", "L5n"},
    "fact_inbound_shipment": {"I1", "I2", "I3", "I4"},
    "view": {"K1": "O1n", "K2": "O2", "K3": "O3", "K4": "O4n"},
}
NOTHING = {"shipment_evidence_observation": set(), "shipment_evidence_line": set(),
           "fact_inbound_shipment": set(), "view": {}}

# (label, read lines, edit lines, role) -> expected visible fixture rows
CASES = [
    ("admin", {"*"}, {"*"}, "admin", ALL_ROWS),
    ("steward A", {"A"}, {"A"}, "steward", {
        "shipment_evidence_observation": {"O2", "O3", "O4o"},
        "shipment_evidence_line": {"L2", "L3", "L4", "L5o"},
        "fact_inbound_shipment": {"I2", "I3", "I4"},
        "view": {"K2": "O2", "K3": "O3"}}),
    ("steward, no lines", set(), set(), "steward", {
        "shipment_evidence_observation": {"O2"},
        "shipment_evidence_line": {"L2", "L4"},
        "fact_inbound_shipment": {"I2", "I3"},
        "view": {"K2": "O2"}}),
    ("planner A", {"A"}, {"A"}, "planner", {
        "shipment_evidence_observation": {"O3", "O4o"},
        "shipment_evidence_line": {"L3", "L5o"},
        "fact_inbound_shipment": {"I4"},
        # K1's and K4's current rows are on B: hidden. Their older rows (K1: no product,
        # inherits B; K4: on A) do NOT surface as current.
        "view": {"K3": "O3"}}),
    ("planner B", {"B"}, {"B"}, "planner", {
        # O1o has no product and inherits B from K1's resolved observation.
        "shipment_evidence_observation": {"O1o", "O1n", "O4n"},
        "shipment_evidence_line": {"L1o", "L1n", "L5n"},
        "fact_inbound_shipment": {"I1"},
        "view": {"K1": "O1n", "K4": "O4n"}}),
    ("viewer A,B", {"A", "B"}, set(), "viewer", {
        "shipment_evidence_observation": {"O1o", "O1n", "O3", "O4o", "O4n"},
        "shipment_evidence_line": {"L1o", "L1n", "L3", "L5o", "L5n"},
        "fact_inbound_shipment": {"I1", "I4"},
        "view": {"K1": "O1n", "K3": "O3", "K4": "O4n"}}),
    ("planner, no lines", set(), set(), "planner", NOTHING),
    ("viewer, no lines, no role", set(), set(), None, NOTHING),
]


@pytest.mark.parametrize("label,read,edit,role,expected", CASES, ids=[c[0] for c in CASES])
def test_lineage_visibility_per_scope(lineage, label, read, edit, role, expected) -> None:
    conn, lines, keys, fx = lineage
    got = _measure(conn, lines, keys, fx, read, edit, role)
    assert got == expected, (label, got)


def test_worker_and_pooled_leftover_are_open(lineage) -> None:
    conn, lines, keys, fx = lineage
    # Worker first, on a backend where the settings were never set in this transaction.
    assert _measure(conn, lines, keys, fx, None, None, None) == ALL_ROWS
    assert _measure(conn, lines, keys, fx, None, None, None, raw="") == ALL_ROWS


def _update_counts(conn, lines, fx, read, edit, role):
    out = {}
    for t in TABLES:
        sp = conn.begin_nested()
        try:
            with _scope(frozenset(lines.get(x, x) for x in read), frozenset(lines.get(x, x) for x in edit), role):
                _bind(conn, (read, edit, role))
                n = conn.execute(text(f"update {t} set product_id = product_id where id = any(:ids)"),
                                 {"ids": list(fx[t].values())}).rowcount
                d = conn.execute(text(f"delete from {t} where id = any(:ids)"),
                                 {"ids": list(fx[t].values())}).rowcount
            out[t] = (n, d)
        finally:
            sp.rollback()
    return out


def test_lineage_edit_per_scope(lineage) -> None:
    conn, lines, keys, fx = lineage
    # Planner B, editable: K1's rows (inherited and resolved), O4n, their lines and I1.
    assert _update_counts(conn, lines, fx, {"B"}, {"B"}, "planner") == {
        "shipment_evidence_observation": (3, 3), "shipment_evidence_line": (3, 3), "fact_inbound_shipment": (1, 1)}
    # Planner B read-only: nothing.
    assert _update_counts(conn, lines, fx, {"B"}, set(), "planner") == {t: (0, 0) for t in TABLES}
    # Steward with read-only A: only the truly unresolved rows (steward work), not pA's rows.
    assert _update_counts(conn, lines, fx, {"A"}, set(), "steward") == {
        "shipment_evidence_observation": (1, 1), "shipment_evidence_line": (2, 2), "fact_inbound_shipment": (2, 2)}
    # Planner A editable: only pA's rows (O3, O4o; L3, L5o; I4).
    assert _update_counts(conn, lines, fx, {"A"}, {"A"}, "planner") == {
        "shipment_evidence_observation": (2, 2), "shipment_evidence_line": (2, 2), "fact_inbound_shipment": (1, 1)}


def test_insert_of_unresolved_row_still_allowed_without_returning(lineage) -> None:
    """WITH CHECK keeps the 0025 rule (imports unchanged). A RETURNING insert of a row the
    caller may not then read fails closed (row security), which imports in workers never meet."""
    conn, lines, keys, fx = lineage
    with _scope(frozenset(), frozenset(), "planner"):
        sp = conn.begin_nested()
        try:
            _bind(conn, (set(), set(), "planner"))
            conn.execute(text("insert into shipment_evidence_observation (line_identity_key, product_id, quantity) "
                              "values ('n0065lineage:ins', null, 1)"))
        finally:
            sp.rollback()
        sp = conn.begin_nested()
        try:
            _bind(conn, (set(), set(), "planner"))
            with pytest.raises(Exception, match="row-level security"):
                conn.execute(text("insert into shipment_evidence_observation (line_identity_key, product_id, quantity) "
                                  "values ('n0065lineage:ins2', null, 1) returning id"))
        finally:
            sp.rollback()


def test_current_pick_runs_once_and_only_when_scoped(lineage) -> None:
    conn, lines, keys, fx = lineage

    def plan(read, role):
        sp = conn.begin_nested()
        try:
            with _scope(frozenset(lines.get(x, x) for x in read), frozenset(), role):
                _bind(conn, (read, set(), role))
                return [r[0] for r in conn.execute(text(
                    "explain (analyze, costs off, timing off, summary off) "
                    "select count(*) from shipment_evidence_current")).all()]
        finally:
            sp.rollback()

    scoped = [ln for ln in plan({"B"}, "planner") if "cip_sev_current_observation_ids" in ln]
    assert scoped and all("loops=1" in ln for ln in scoped), scoped
    admin = [ln for ln in plan({"*"}, "admin") if "cip_sev_current_observation_ids" in ln]
    assert all("never executed" in ln for ln in admin), admin


def test_view_refresh_keeps_the_current_pick(lineage) -> None:
    """refresh_shipment_evidence_current_view (graduation) re-creates the view; it must keep
    security_invoker and the 0026 current pick, or a refresh would bring F1 back."""
    from sqlalchemy.orm import Session

    from app.services.imports.shipment_invoice_graduation import refresh_shipment_evidence_current_view

    conn, lines, keys, fx = lineage
    sp = conn.begin_nested()
    try:
        with Session(bind=conn, join_transaction_mode="create_savepoint") as s:
            refresh_shipment_evidence_current_view(s)
        definition = conn.execute(text("select pg_get_viewdef('shipment_evidence_current'::regclass)")).scalar_one()
        assert "cip_sev_current_observation_ids" in definition
        assert "security_invoker=true" in str(conn.execute(text(
            "select reloptions from pg_class where relname = 'shipment_evidence_current'")).scalar_one())
        planner_a = next(c for c in CASES if c[0] == "planner A")
        assert _measure(conn, lines, keys, fx, *planner_a[1:4]) == planner_a[4]
    finally:
        sp.rollback()


# ---------------------------------------------------------------- round 5 (migration 20261009_0027)

NO_PRODUCT_TABLES = ("commercial_lineup_line", "cst_listing_seed", "customer_listing", "historical_lineup_import_line")
PICK = "cip_sev_current_observation_ids"
INDEX = "ix_shipment_ev_obs_identity_latest"


def _require_0027(conn) -> None:
    rev = conn.execute(text("select version_num from alembic_version")).scalar_one()
    assert _applied(rev, "20261009_0027"), f"cip_test must have 0027 applied for the round-5 tests, is at {rev}"


@pytest.fixture()
def no_product():
    """Per table: one row with no product (N), one on line A, one on line B. Rolled back."""
    from app.core.config import get_settings

    get_settings.cache_clear()
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1),
                        poolclass=NullPool)
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"round-5 tests run on cip_test only (current_database()={db})")
    conn.rollback()
    tx = conn.begin()
    try:
        _require_0027(conn)
        tag = uuid.uuid4().hex[:8]
        lines = {"A": f"N0065N-A-{tag}", "B": f"N0065N-B-{tag}"}
        for t in ("dim_product", *NO_PRODUCT_TABLES):
            conn.execute(text(f"ALTER TABLE {_q(t)} NO FORCE ROW LEVEL SECURITY"))
        for t in NO_PRODUCT_TABLES:
            _relax(conn, t)
        pid = {}
        for k in ("A", "B"):
            pid[k] = conn.execute(
                text("insert into dim_product (sku, name, is_active, product_line) values (:s, :n, true, :l) returning id"),
                {"s": f"N0065N-{tag}-{k}", "n": f"N0065 no-product {k}", "l": lines[k]},
            ).scalar_one()
        fx = {}
        for t in NO_PRODUCT_TABLES:
            fx[t] = {name: conn.execute(text(f"insert into {_q(t)} (product_id) values (:p) returning id"),
                                        {"p": p}).scalar_one()
                     for name, p in (("N", None), ("A", pid["A"]), ("B", pid["B"]))}
        for t in ("dim_product", *NO_PRODUCT_TABLES):
            conn.execute(text(f"ALTER TABLE {_q(t)} FORCE ROW LEVEL SECURITY"))
        yield conn, lines, fx
    finally:
        tx.rollback()
        conn.close()
        eng.dispose()


def _visible_four(conn, lines, fx, read, edit, role, raw=None):
    sp = conn.begin_nested()
    try:
        expand = (lambda s: None if s is None else frozenset(lines.get(x, x) for x in s))
        with _scope(expand(read), expand(edit), role):
            _bind(conn, raw if raw is not None or read is None else (read, edit, role))
            out = {}
            for t in NO_PRODUCT_TABLES:
                got = {r[0] for r in conn.execute(text(f"select id from {_q(t)} where id = any(:ids)"),
                                                  {"ids": list(fx[t].values())}).all()}
                out[t] = _names(fx[t], got)
            return out
    finally:
        sp.rollback()


def _all4(rows: set[str]) -> dict[str, set[str]]:
    return {t: set(rows) for t in NO_PRODUCT_TABLES}


# (label, read lines, edit lines, role) -> rows visible in each of the four tables
NO_PRODUCT_CASES = [
    ("admin", {"*"}, {"*"}, "admin", _all4({"N", "A", "B"})),
    ("steward A", {"A"}, {"A"}, "steward", _all4({"N", "A"})),
    ("steward, no lines", set(), set(), "steward", _all4({"N"})),
    ("planner A", {"A"}, {"A"}, "planner", _all4({"A"})),
    ("planner, no lines", set(), set(), "planner", _all4(set())),
    ("viewer A,B", {"A", "B"}, set(), "viewer", _all4({"A", "B"})),
    ("viewer, no lines, no role", set(), set(), None, _all4(set())),
]


@pytest.mark.parametrize("label,read,edit,role,expected", NO_PRODUCT_CASES, ids=[c[0] for c in NO_PRODUCT_CASES])
def test_no_product_rows_admin_and_steward_only(no_product, label, read, edit, role, expected) -> None:
    conn, lines, fx = no_product
    assert _visible_four(conn, lines, fx, read, edit, role) == expected, label


def test_no_product_rows_open_for_workers_and_pooled_leftover(no_product) -> None:
    conn, lines, fx = no_product
    assert _visible_four(conn, lines, fx, None, None, None) == _all4({"N", "A", "B"})
    assert _visible_four(conn, lines, fx, None, None, None, raw="") == _all4({"N", "A", "B"})


def _edit_four(conn, lines, fx, read, edit, role):
    out = {}
    for t in NO_PRODUCT_TABLES:
        sp = conn.begin_nested()
        try:
            with _scope(frozenset(lines.get(x, x) for x in read), frozenset(lines.get(x, x) for x in edit), role):
                _bind(conn, (read, edit, role))
                ids = list(fx[t].values())
                n = conn.execute(text(f"update {_q(t)} set product_id = product_id where id = any(:ids)"),
                                 {"ids": ids}).rowcount
                d = conn.execute(text(f"delete from {_q(t)} where id = any(:ids)"), {"ids": ids}).rowcount
            out[t] = (n, d)
        finally:
            sp.rollback()
    return out


def test_no_product_rows_edit_per_scope(no_product) -> None:
    conn, lines, fx = no_product
    assert _edit_four(conn, lines, fx, {"*"}, {"*"}, "admin") == {t: (3, 3) for t in NO_PRODUCT_TABLES}
    # Planner A, editable: only the line-A row (the row with no product is no longer editable).
    assert _edit_four(conn, lines, fx, {"A"}, {"A"}, "planner") == {t: (1, 1) for t in NO_PRODUCT_TABLES}
    # Steward with read-only A: only the row with no product.
    assert _edit_four(conn, lines, fx, {"A"}, set(), "steward") == {t: (1, 1) for t in NO_PRODUCT_TABLES}
    assert _edit_four(conn, lines, fx, set(), set(), "planner") == {t: (0, 0) for t in NO_PRODUCT_TABLES}


@pytest.mark.parametrize("table", NO_PRODUCT_TABLES)
def test_no_product_insert_check_unchanged_returning_fails_closed(no_product, table) -> None:
    """WITH CHECK keeps the 0025 rule: anyone may write a row with no product. A RETURNING
    insert (what the ORM's flush does) by a non-steward, non-admin request fails closed,
    because the new row must then be readable. Workers (unset), admins and stewards are fine."""
    conn, lines, fx = no_product

    def ins(read, edit, role, returning):
        sp = conn.begin_nested()
        try:
            with _scope(None if read is None else frozenset(read), None if edit is None else frozenset(edit), role):
                _bind(conn, None if read is None else (read, edit, role))
                conn.execute(text(f"insert into {_q(table)} (product_id) values (null)"
                                  + (" returning id" if returning else "")))
            return "ok"
        except Exception as exc:  # noqa: BLE001
            return "RLS" if "row-level security" in str(exc) else f"ERR {type(exc).__name__}"
        finally:
            if sp.is_active:
                sp.rollback()

    assert ins(set(), set(), "planner", returning=False) == "ok"
    assert ins(set(), set(), "planner", returning=True) == "RLS"
    assert ins(set(), set(), "steward", returning=True) == "ok"
    assert ins({"*"}, {"*"}, "admin", returning=True) == "ok"
    assert ins(None, None, None, returning=True) == "ok"


def _pick_query(conn) -> tuple[list[str], str]:
    cfg, src = conn.execute(text("select proconfig, prosrc from pg_proc where proname = :n"), {"n": PICK}).one()
    query = src.split("RETURN QUERY", 1)[1].split(";", 1)[0]
    return list(cfg or []), query


def test_current_pick_walks_the_index_in_order(lineage) -> None:
    """0027 (a): the pick's own query, planned under the function's own settings, walks
    ix_shipment_ev_obs_identity_latest in order with no Sort or Incremental Sort node.

    Index-only when the visibility map allows (cip, and cip_test after autovacuum); the
    fixture's uncommitted rows can make the planner cost it as a plain index scan of the
    same index, which is the same ordered walk. enable_sort = off alone is not enough on
    PostgreSQL 18: with a stale visibility map the planner chose an Incremental Sort over
    ix_shipment_ev_obs_line_identity (full cip_test run, round 5), so the function also
    carries enable_incremental_sort = off."""
    conn, lines, keys, fx = lineage
    _require_0027(conn)
    cfg, query = _pick_query(conn)

    def plan(with_function_config: bool) -> list[str]:
        # cip_test is small, so the default costs already favour the index here. A high
        # random_page_cost reproduces cip's choice (seq scan + sort) so that the function's
        # own setting is what decides the plan (the control below proves the test bites).
        sp = conn.begin_nested()
        try:
            conn.execute(text("select set_config('cip.product_lines', '*', true)"))
            conn.execute(text("set local random_page_cost = 1000"))
            for item in cfg if with_function_config else []:
                name, value = item.split("=", 1)
                conn.execute(text("select set_config(:n, :v, true)"), {"n": name, "v": value})
            rows = [r[0] for r in conn.execute(text("explain (costs off) " + query)).all()]
        finally:
            sp.rollback()
        return [ln.strip().removeprefix("->").strip() for ln in rows]

    control = plan(with_function_config=False)
    assert any(n.startswith(("Sort", "Incremental Sort")) for n in control), control
    nodes = plan(with_function_config=True)
    assert any(n.startswith((f"Index Only Scan using {INDEX}", f"Index Scan using {INDEX}")) for n in nodes), nodes
    assert not any(n.startswith(("Sort", "Incremental Sort")) for n in nodes), nodes
    assert "enable_sort=off" in cfg, cfg
    assert "enable_incremental_sort=off" in cfg, cfg


def test_current_pick_rows_unchanged_by_the_setting(lineage) -> None:
    """The setting changes the plan only: the function returns the same ids as its query
    planned with the defaults, under every scope (the helper reads every row), and the
    caller's enable_sort is back on after the call."""
    conn, lines, keys, fx = lineage
    _require_0027(conn)
    _cfg, query = _pick_query(conn)
    sp = conn.begin_nested()
    try:
        conn.execute(text("select set_config('cip.product_lines', '*', true)"))
        expected = {r[0] for r in conn.execute(text(query)).all()}
        for scope in ({"A"}, set(), {"*"}):
            with _scope(frozenset(lines.get(x, x) for x in scope), frozenset(), "planner"):
                _bind(conn, (scope, set(), "planner"))
                got = {r[0] for r in conn.execute(text(f"select row_id from public.{PICK}()")).all()}
                assert conn.execute(text("show enable_sort")).scalar_one() == "on"
                assert conn.execute(text("show enable_incremental_sort")).scalar_one() == "on"
            assert got == expected
        assert {fx["shipment_evidence_observation"][n] for n in ("O1n", "O2", "O3", "O4n")} <= expected
    finally:
        sp.rollback()
