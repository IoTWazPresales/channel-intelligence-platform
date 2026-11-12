"""Read-only N-0108 probe. Times the current latest-observation query and two narrower shapes.

Connects with the app sync URL. Prints current_database() and stops unless it is cip.
The transaction is READ ONLY and is rolled back.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

ROOT_ENV = Path(r"C:\Users\warren_eliason\channel-intelligence-platform\apps\api\.env")
OUT = Path(__file__).with_name("n0108_probe_out.txt")


def load_env(path: Path) -> list[str]:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
    else:
        text = raw.decode("utf-8-sig")
    loaded: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
        loaded.append(key)
    return loaded


def sync_url() -> str:
    url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL") or ""
    if not url:
        # apps/api/.env on this machine has no database URL. This is the app default
        # in app/core/config.py and apps/api/.env.example.
        url = "postgresql://cip:cip@localhost:5432/cip"
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql://" + url[len("postgresql+asyncpg://") :]
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + url[len("postgresql+psycopg2://") :]
    return url


ORDER = """
    distributor_id,
    product_id,
    cover_as_of_date DESC,
    CASE WHEN trigger = 'as_of_backfill' THEN 1 ELSE 0 END ASC,
    observed_at DESC
"""

WIDE = f"""
SELECT id
FROM (
    SELECT DISTINCT ON (distributor_id, product_id) id
    FROM weeks_of_cover_observation
    WHERE tenant_id = %(tenant)s
    ORDER BY {ORDER}
) picked
ORDER BY id
"""

# Same projection as the ORM today: the sort input is the full row.
WIDE_STAR = f"""
SELECT id
FROM (
    SELECT DISTINCT ON (distributor_id, product_id) *
    FROM weeks_of_cover_observation
    WHERE tenant_id = %(tenant)s
    ORDER BY {ORDER}
) picked
ORDER BY id
"""

NARROW = f"""
SELECT w.id
FROM weeks_of_cover_observation w
JOIN (
    SELECT DISTINCT ON (distributor_id, product_id) id
    FROM weeks_of_cover_observation
    WHERE tenant_id = %(tenant)s
    ORDER BY {ORDER}
) latest ON latest.id = w.id
ORDER BY w.id
"""

LATERAL = f"""
SELECT w.id
FROM (
    SELECT DISTINCT distributor_id, product_id
    FROM weeks_of_cover_observation
    WHERE tenant_id = %(tenant)s
) pairs
JOIN LATERAL (
    SELECT id
    FROM weeks_of_cover_observation w
    WHERE w.tenant_id = %(tenant)s
      AND w.distributor_id = pairs.distributor_id
      AND w.product_id = pairs.product_id
    ORDER BY {ORDER}
    LIMIT 1
) w ON true
ORDER BY w.id
"""


def main() -> None:
    loaded = load_env(ROOT_ENV)
    loaded = load_env(ROOT_ENV)
    print(
        f"env_path_exists={ROOT_ENV.exists()} env_bytes={ROOT_ENV.stat().st_size if ROOT_ENV.exists() else 0} "
        f"key_count={len(loaded)} has_database_url={'DATABASE_URL' in loaded or 'DATABASE_URL_SYNC' in loaded}",
        flush=True,
    )
    import psycopg

    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    url = sync_url()
    if not url:
        raise SystemExit("STOP: no DATABASE_URL_SYNC")

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SET statement_timeout = '90s'")
        conn.autocommit = False
        conn.execute("SET TRANSACTION READ ONLY")
        db = conn.execute("SELECT current_database()").fetchone()[0]
        user = conn.execute("SELECT current_user").fetchone()[0]
        log(f"current_database={db}")
        log(f"current_user={user}")
        if db != "cip":
            raise SystemExit(f"STOP: database is {db!r}, not cip")

        rls = conn.execute(
            """
            SELECT c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'weeks_of_cover_observation'
            """
        ).fetchone()
        log(f"rls rowsecurity={rls[0]} forcerowsecurity={rls[1]}")
        log("indexes:")
        for name, definition in conn.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = 'weeks_of_cover_observation'
            ORDER BY indexname
            """
        ):
            log(f"  {name}: {definition}")

        tenants = conn.execute(
            """
            SELECT tenant_id, count(*)
            FROM weeks_of_cover_observation
            GROUP BY tenant_id
            ORDER BY count(*) DESC
            """
        ).fetchall()
        log(f"tenants={tenants}")
        tenant = tenants[0][0]

        size = conn.execute(
            """
            SELECT count(*),
                   pg_size_pretty(pg_relation_size('weeks_of_cover_observation')),
                   pg_size_pretty(pg_indexes_size('weeks_of_cover_observation'))
            FROM weeks_of_cover_observation
            WHERE tenant_id = %(tenant)s
            """,
            {"tenant": tenant},
        ).fetchone()
        log(f"rows={size[0]} heap={size[1]} indexes={size[2]} tenant={tenant}")

        ties = conn.execute(
            f"""
            SELECT count(*) FROM (
                SELECT 1
                FROM weeks_of_cover_observation
                WHERE tenant_id = %(tenant)s
                GROUP BY distributor_id, product_id, cover_as_of_date,
                         CASE WHEN trigger = 'as_of_backfill' THEN 1 ELSE 0 END,
                         observed_at
                HAVING count(*) > 1
            ) t
            """,
            {"tenant": tenant},
        ).fetchone()[0]
        log(f"exact_sort_key_ties={ties}")

        lines_q = conn.execute(
            """
            SELECT p.product_line, count(*) AS products
            FROM dim_product p
            WHERE p.product_line IS NOT NULL AND btrim(p.product_line) <> ''
            GROUP BY p.product_line
            ORDER BY count(*) DESC
            LIMIT 8
            """
        ).fetchall()
        log("product_lines=" + ", ".join(f"{name}:{n}" for name, n in lines_q))
        one_line = lines_q[0][0] if lines_q else None

        scopes: list[tuple[str, str | None]] = [
            ("unset", None),
            ("star", "*"),
        ]
        if one_line:
            scopes.append(("one_line", one_line))

        queries = [
            ("wide_star", WIDE_STAR),
            ("narrow", NARROW),
            ("lateral", LATERAL),
        ]

        baseline_ids: list[int] | None = None
        for scope_name, setting in scopes:
            if setting is None:
                conn.execute("SELECT set_config('cip.product_lines', '', true)")
            else:
                conn.execute(
                    "SELECT set_config('cip.product_lines', %s, true)",
                    (setting,),
                )
            shown = conn.execute("SELECT current_setting('cip.product_lines', true)").fetchone()[0]
            log(f"--- scope={scope_name} setting={shown!r} ---")
            ids_by_query: dict[str, list[int]] = {}
            for label, sql in queries:
                try:
                    with conn.transaction():
                        started = time.perf_counter()
                        ids = [row[0] for row in conn.execute(sql, {"tenant": tenant})]
                        elapsed = time.perf_counter() - started
                    ids_by_query[label] = ids
                    log(f"  {label} rows={len(ids)} seconds={elapsed:.3f}")
                    with conn.transaction():
                        plan = conn.execute(
                            "EXPLAIN (ANALYZE, BUFFERS) " + sql,
                            {"tenant": tenant},
                        ).fetchall()
                    log(f"  plan {label}:")
                    for (line,) in plan:
                        log(f"    {line}")
                except Exception as exc:
                    log(f"  {label} ERROR {type(exc).__name__}: {exc}")
                    conn.rollback()
                    conn.execute("SET TRANSACTION READ ONLY")
                    if setting is None:
                        conn.execute("SELECT set_config('cip.product_lines', '', true)")
                    else:
                        conn.execute(
                            "SELECT set_config('cip.product_lines', %s, true)",
                            (setting,),
                        )
            if baseline_ids is None:
                baseline_ids = ids_by_query["wide_star"]
            for label, ids in ids_by_query.items():
                same = ids == ids_by_query["wide_star"]
                log(f"  match_wide_star {label}={same}")

        conn.rollback()
        log("rollback=ok")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(f"wrote {OUT}")


if __name__ == "__main__":
    main()
