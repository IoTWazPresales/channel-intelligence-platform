"""GOV-008 N-0065 VER2: shipment_evidence_current respects row security (READ ONLY, cip).

Run from the project root with the API virtualenv. Prints current_database() first.
Expected counts per scope are derived under '*' (open) from the view's base rows by product id,
then compared with what the view returns under each scope. No writes.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})


def setp(c, v):
    if v is not None:
        c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": v})


with eng.connect() as c:
    db = c.execute(sa.text("select current_database()")).scalar_one()
    print("current_database() =", db, "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    assert db == "cip"
    print("view owner =", c.execute(sa.text(
        "select pg_get_userbyid(relowner) from pg_class where relname='shipment_evidence_current'")).scalar(),
        "| reloptions =", c.execute(sa.text(
            "select reloptions from pg_class where relname='shipment_evidence_current'")).scalar())
    cols = [r[0] for r in c.execute(sa.text(
        "select column_name from information_schema.columns where table_name='shipment_evidence_current' "
        "order by ordinal_position")).all()]
    print("view columns =", cols)
    deps = c.execute(sa.text("""
        select distinct d.refobjid::regclass::text from pg_depend d join pg_rewrite r on r.oid = d.objid
        where r.ev_class = 'shipment_evidence_current'::regclass and d.refobjid <> 'shipment_evidence_current'::regclass
        order by 1""")).scalars().all()
    print("view reads =", deps)
    pcol = "product_id" if "product_id" in cols else ("canonical_product_id" if "canonical_product_id" in cols else None)
    print("product column =", pcol)
    setp(c, "*")
    total = c.execute(sa.text("select count(*) from shipment_evidence_current")).scalar_one()
    nul = c.execute(sa.text(f"select count(*) from shipment_evidence_current where {pcol} is null")).scalar_one()
    lines = c.execute(sa.text(f"""
        select p.product_line, count(*) from shipment_evidence_current v join dim_product p on p.id = v.{pcol}
        group by 1 order by 2 desc""")).all()
    orphan = c.execute(sa.text(f"""select count(*) from shipment_evidence_current v where v.{pcol} is not null
        and not exists (select 1 from dim_product p where p.id = v.{pcol})""")).scalar_one()
    print(f"under '*': total={total} null_product={nul} orphan={orphan} by line={[(l, int(k)) for l, k in lines]}")
    c.rollback()
    exp = {None: total, "*": total, "!": nul}
    by = {l: int(k) for l, k in lines}
    for l in ("NB", "AZ"):
        exp[l] = nul + by.get(l, 0)
    two = [l for l, _ in lines if l][:2]
    if len(two) == 2:
        exp[",".join(two)] = nul + by[two[0]] + by[two[1]]
    exp[""] = total
    bad = 0
    for scope, e in exp.items():
        setp(c, scope)
        got = c.execute(sa.text("select count(*) from shipment_evidence_current")).scalar_one()
        st = c.execute(sa.text("select current_setting('cip.product_lines', true)")).scalar()
        other = 0
        if scope not in (None, "*", "", "!"):
            allowed = scope.split(",")
            other = c.execute(sa.text(f"""select count(*) from shipment_evidence_current v
                where v.{pcol} is not null and v.{pcol} not in
                (select id from dim_product where product_line = any(:a))"""), {"a": allowed}).scalar_one()
        ok = got == e
        bad += 0 if ok else 1
        print(f"  scope={scope!r:12} setting={st!r:12} view rows={got:6} expected={e:6} other-line rows={other} {'OK' if ok else 'MISMATCH'}")
        c.rollback()
    if nul:
        setp(c, "!")
        sample_cols = [x for x in cols if x in ("source_sku", "raw_sku", "sku", "item_code", "description",
                                                  "product_description", "raw_description", "customer_id",
                                                  "distributor_id", "quantity", "qty")]
        print("columns a no-lines user can read on null-product rows (subset, names only):", sample_cols)
        c.rollback()
    print("mismatches:", bad)
eng.dispose()
