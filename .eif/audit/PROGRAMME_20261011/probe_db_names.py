"""Names only. No values."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[3]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))
os.chdir(API)

from app.db.session_sync import SessionLocal  # noqa: E402


def main() -> None:
    env_path = API / ".env"
    keys = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key.isidentifier() and (
            "MIGRATE" in key or "ADMIN" in key or "POSTGRES" in key or key.startswith("DATABASE")
        ):
            keys.append(key)
    print("environ_migrate_set", bool((os.environ.get("DATABASE_URL_SYNC_MIGRATE") or "").strip()))
    raw = env_path.read_bytes()
    body = raw.decode("utf-8-sig", errors="replace")
    names = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        folded = key.casefold()
        if "database" in folded or "migrate" in folded:
            value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            names.append(f"{key}:{'set' if value else 'empty'}")
    print("file_database_keys", ",".join(names))
    from sqlalchemy import text as sql_text

    with SessionLocal() as session:
        names = session.execute(
            sql_text("SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY datname")
        ).scalars().all()
        print("databases", ",".join(str(name) for name in names))


if __name__ == "__main__":
    main()
