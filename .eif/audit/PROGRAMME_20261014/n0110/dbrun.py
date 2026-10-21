"""N-0110: run a command with DATABASE_URL, DATABASE_URL_SYNC and DATABASE_URL_SYNC_MIGRATE
pointed at one database. Passwords are never printed.

usage: python dbrun.py <dbname> -- <command...>    (cwd = apps/api)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from app.core.config import get_settings  # noqa: E402


def swap_db(url: str, db: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path="/" + db))


def redact(url: str) -> str:
    p = urlparse(url)
    if p.password:
        return url.replace(f":{p.password}@", ":***@")
    return url


def main() -> int:
    db = sys.argv[1]
    cmd = sys.argv[sys.argv.index("--") + 1 :]
    if cmd and cmd[0] == "python":
        cmd[0] = sys.executable
    s = get_settings()
    env = dict(os.environ)
    env["DATABASE_URL"] = swap_db(s.database_url, db)
    env["DATABASE_URL_SYNC"] = swap_db(s.database_url_sync, db)
    env["DATABASE_URL_SYNC_MIGRATE"] = swap_db(s.database_url_sync_migrate or s.database_url_sync, db)
    for k in ("DATABASE_URL", "DATABASE_URL_SYNC", "DATABASE_URL_SYNC_MIGRATE"):
        print(f"{k}={redact(env[k])}", flush=True)
    import psycopg  # noqa: PLC0415

    with psycopg.connect(env["DATABASE_URL_SYNC_MIGRATE"].replace("postgresql+psycopg://", "postgresql://")) as conn:
        print("current_database()=" + conn.execute("select current_database()").fetchone()[0], flush=True)
    return subprocess.call(cmd, env=env, cwd=API)


if __name__ == "__main__":
    raise SystemExit(main())
