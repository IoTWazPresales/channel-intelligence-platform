"""GOV-008 N-0065 live read-only probe on cip (RUN-20261007-N0065-VER).

Run from apps/api with its virtualenv. Prints current_database() first, refuses
unless it is exactly cip, runs everything inside one READ ONLY transaction and
rolls it back. Never prints the URL, a credential, a user name or an email.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.core.product_line_scope import product_line_scope_for, scope_csv


def main() -> int:
    s = get_settings()
    print("settings.cip_auth_mode =", (s.cip_auth_mode or "stub"))
    eng = create_engine(
        s.database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1),
        connect_args={"options": "-c statement_timeout=60000"},
    )
    with eng.connect() as c:
        db = c.execute(text("select current_database()")).scalar_one()
        print("current_database() =", db)
        assert db == "cip", "refusing: not cip"
        c.rollback()
        tx = c.begin()
        try:
            c.execute(text("SET TRANSACTION READ ONLY"))
            print("transaction_read_only =", c.execute(text("show transaction_read_only")).scalar_one())
            r = c.execute(
                text("select rolname, rolsuper, rolbypassrls from pg_roles where rolname = current_user")
            ).one()
            print("role =", r.rolname, "super =", r.rolsuper, "bypassrls =", r.rolbypassrls)
            print("alembic =", c.execute(text("select version_num from alembic_version")).scalars().all())
            rls = c.execute(
                text("select relrowsecurity, relforcerowsecurity from pg_class where relname='dim_product'")
            ).one()
            print("dim_product rls =", rls.relrowsecurity, "force =", rls.relforcerowsecurity)
            print(
                "cip_product_% functions =",
                c.execute(text("select count(*) from pg_proc where proname like 'cip_product_%'")).scalar_one(),
            )
            print(
                "tables with cip_pl_select =",
                c.execute(text("select count(*) from pg_policies where policyname='cip_pl_select'")).scalar_one(),
            )
            owner = c.execute(
                text("select pg_get_userbyid(relowner) from pg_class where relname='dim_product'")
            ).scalar_one()
            print("dim_product owner is current_user =", owner == r.rolname)

            def setp(read: str | None, edit: str | None = None) -> None:
                c.execute(text("select set_config('cip.product_lines', :v, true)"), {"v": read})
                c.execute(text("select set_config('cip.editable_product_lines', :v, true)"), {"v": edit if edit is not None else ""})

            def n(sql: str = "select count(*) from dim_product", **kw) -> int:
                return int(c.execute(text(sql), kw).scalar_one())

            print("setting before any set =", c.execute(text("select current_setting('cip.product_lines', true)")).scalar_one())
            unset_total = n()
            print("UNSET (worker / own SessionLocal) dim_product count =", unset_total)

            setp("*", "*")
            star_total = n()
            print("'*' dim_product count =", star_total)
            lines = c.execute(
                text(
                    "select product_line, count(*) as k from dim_product "
                    "where product_line is not null group by product_line order by k"
                )
            ).all()
            nulls = n("select count(*) from dim_product where product_line is null")
            print("distinct non-null lines =", len(lines), "null-line products =", nulls)
            print("lines (name,count) =", [(x.product_line, int(x.k)) for x in lines])

            # Grant table state (no identities printed).
            print("user_product_line_access rows =", n("select count(*) from user_product_line_access"))
            print(
                "grant rows that are '*' or hold a comma =",
                n("select count(*) from user_product_line_access where product_line = '*' or product_line like '%,%'"),
            )
            print(
                "app_user roles =",
                [tuple(x) for x in c.execute(text("select lower(role), count(*) from app_user group by 1 order by 1")).all()],
            )

            setp("", "")
            print("'' (non-admin, no assignment) dim_product count =", n())

            if lines:
                one, k = lines[0].product_line, int(lines[0].k)
                setp(one, "")
                seen = n()
                other = n("select count(*) from dim_product where product_line is distinct from :l", l=one)
                print(f"one line ({one!r}, expected {k}) count =", seen, "rows of any other line =", other)
                print(
                    "  editable under read-only (no-op update would hit) =",
                    n("select count(*) from dim_product where cip_product_line_editable(product_line)"),
                )

            # Plant-false: non-admin grant rows of '*' and 'A,B' through the real helper.
            if len(lines) >= 2:
                a, b = lines[0].product_line, lines[1].product_line
                for label, rows in (
                    ("non-admin row '*'", [("*", True)]),
                    ("non-admin row 'A,B'", [(f"{a},{b}", True)]),
                    ("non-admin rows '*' + A", [("*", True), (a, False)]),
                ):
                    rd, ed = product_line_scope_for(is_admin=False, assignments=rows)
                    setp(scope_csv(rd), scope_csv(ed))
                    print(f"plant-false {label}: bound read={scope_csv(rd)!r} edit={scope_csv(ed)!r} count =", n(),
                          "editable =", n("select count(*) from dim_product where cip_product_line_editable(product_line)"))
                setp(f"{a},{b}", "")
                print("contrast raw setting 'A,B' (what an unfiltered row would bind) count =", n(),
                      "expected", int(lines[0].k) + int(lines[1].k))
                rd, ed = product_line_scope_for(is_admin=True, assignments=[(a, False)])
                setp(scope_csv(rd), scope_csv(ed))
                print("admin helper bind:", scope_csv(rd), scope_csv(ed), "count =", n())

            # One product-keyed table behind cip_product_id_visible: smallest non-empty policy table.
            setp("*", "*")
            tbls = [x[0] for x in c.execute(text("select tablename from pg_policies where policyname='cip_pl_select' and tablename <> 'dim_product' order by tablename")).all()]
            picked = None
            for t in tbls:
                est = c.execute(text("select reltuples from pg_class where relname = :t"), {"t": t}).scalar_one()
                if est is not None and 0 < est < 20000:
                    picked = t
                    break
            if picked:
                star_k = n(f'select count(*) from "{picked}"')
                setp("", "")
                empty_k = n(f'select count(*) from "{picked}"')
                print(f"product-keyed table {picked}: '*' count =", star_k, "'' count =", empty_k)
        finally:
            tx.rollback()
        print("after rollback setting =", c.execute(text("select current_setting('cip.product_lines', true)")).scalar_one())
        c.rollback()
    eng.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
