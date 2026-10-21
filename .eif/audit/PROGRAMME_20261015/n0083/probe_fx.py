"""N-0083: read-only look at fx_daily_rate on one database. usage: python probe_fx.py <dbname>"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PROGRAMME_20261014" / "n0110"))

import psycopg  # noqa: E402

from n0110_numbers import url_for  # noqa: E402


def main() -> int:
    db = sys.argv[1]
    url = url_for(db)
    if len(sys.argv) > 2 and sys.argv[2] == "app":
        from urllib.parse import urlparse, urlunparse

        from app.core.config import get_settings

        raw = get_settings().database_url_sync.replace("postgresql+psycopg://", "postgresql://")
        url = urlunparse(urlparse(raw)._replace(path="/" + db))
    with psycopg.connect(url) as conn:
        q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
        print("current_database", q("select current_database()")[0][0], "user", q("select current_user")[0][0])
        print("alembic", q("select version_num from alembic_version"))
        print("owner", q("select tablename, tableowner from pg_tables where tablename in ('fx_daily_rate','cpor_case')"))
        print(
            "privs",
            q(
                "select grantee, privilege_type from information_schema.role_table_grants "
                "where table_name = 'fx_daily_rate' order by 1, 2"
            ),
        )
        print("can_insert", q("select has_table_privilege(current_user, 'fx_daily_rate', 'INSERT')"))
        print("can_update", q("select has_table_privilege(current_user, 'fx_daily_rate', 'UPDATE')"))
        print("seq_owner", q("select c.relname, pg_get_userbyid(c.relowner) from pg_class c where c.relname = 'fx_daily_rate_id_seq'"))
        print("seq_usage", q("select has_sequence_privilege(current_user, 'fx_daily_rate_id_seq', 'USAGE')"))
        print("rows", q("select count(*), min(rate_date), max(rate_date) from fx_daily_rate"))
        print(
            "cases",
            q(
                "select status, count(*), count(roe_snapshot), count(fx_mode), count(fx_proposed_rate) "
                "from cpor_case group by status order by 1"
            ),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
