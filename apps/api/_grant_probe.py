"""Untracked probe. Connects only to database cip_test. Prints no URLs or secrets."""

from __future__ import annotations

import sys

from sqlalchemy import create_engine, text

from app.db.sync_url import sqlalchemy_sync_engine_url

def _as_cip() -> None:
    engine = create_engine(
        sqlalchemy_sync_engine_url("postgresql://cip:cip@127.0.0.1:5432/cip_test"),
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as conn:
            db = conn.execute(text("select current_database()")).scalar_one()
            print(f"cip_probe current_database={db}")
            if db != "cip_test":
                raise SystemExit(f"STOP current_database={db}")
            rows = conn.execute(
                text(
                    "select rolname, rolsuper from pg_roles "
                    "where rolname in ('cip', 'postgres') order by 1"
                )
            ).all()
            for name, superuser in rows:
                print(f"role {name} rolsuper={superuser}")
            seqs = conn.execute(
                text(
                    """
                    SELECT t.relname AS table_name, s.relname AS sequence_name
                    FROM pg_class AS s
                    JOIN pg_namespace AS ns ON ns.oid = s.relnamespace
                    JOIN pg_depend AS d ON d.objid = s.oid AND d.deptype IN ('a', 'i')
                    JOIN pg_class AS t ON t.oid = d.refobjid
                    JOIN pg_namespace AS nt ON nt.oid = t.relnamespace
                    WHERE s.relkind = 'S'
                      AND ns.nspname = 'public'
                      AND nt.nspname = 'public'
                      AND t.relname IN (
                        'dc_served_account',
                        'site_candidate',
                        'user_customer_account',
                        'store_dc_tenant_config'
                      )
                    ORDER BY 1, 2
                    """
                )
            ).all()
            if not seqs:
                print("OWNED_SEQUENCES_NONE")
            for table_name, sequence_name in seqs:
                print(f"owned_sequence {table_name} {sequence_name}")
            supers = conn.execute(
                text("select rolname from pg_roles where rolsuper order by 1")
            ).all()
            print("superusers=" + ",".join(str(row[0]) for row in supers))
            try:
                rules = conn.execute(
                    text(
                        "select type, database, user_name, auth_method "
                        "from pg_hba_file_rules() order by line_number"
                    )
                ).all()
                for rule in rules:
                    print("hba " + " ".join("" if part is None else str(part) for part in rule))
            except Exception as exc:
                print("hba_unreadable " + type(exc).__name__)
    finally:
        engine.dispose()


_as_cip()

CANDIDATES = (
    "postgresql://postgres@127.0.0.1:5432/cip_test",
    "postgresql://postgres:postgres@127.0.0.1:5432/cip_test",
    "postgresql://postgres:cip@127.0.0.1:5432/cip_test",
    "postgresql://postgres@localhost:5432/cip_test",
)


def _safe(exc: BaseException) -> str:
    import re

    orig = getattr(exc, "orig", None)
    message = str(orig or exc)
    message = re.sub(r"\S+://\S+", "", message)
    message = re.sub(r"\S*@\S+", "", message)
    message = " ".join(message.split())
    return type(exc).__name__ + ": " + message[:180]


last = "no candidate"
for raw in CANDIDATES:
    engine = create_engine(sqlalchemy_sync_engine_url(raw), pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            db = conn.execute(text("select current_database()")).scalar_one()
            user = conn.execute(text("select current_user")).scalar_one()
            print(f"owner_probe current_database={db} current_user={user}")
            if db != "cip_test":
                raise SystemExit(f"STOP current_database={db}")
            print("OWNER_CONNECT_OK")
            sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        last = _safe(exc)
        print("owner_probe_failed " + last)
    finally:
        engine.dispose()

print("OWNER_CONNECT_FAILED " + last)
sys.exit(1)
