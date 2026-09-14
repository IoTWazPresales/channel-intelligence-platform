"""Read-only: print current_database() then exit. No DML."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine

env = Path(__file__).resolve().parents[3] / "apps/api/.env"
vals: dict[str, str] = {}
for line in env.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    vals[k] = v.strip().strip('"').strip("'")
url = vals.get("DATABASE_URL_SYNC") or vals.get("DATABASE_URL")
if not url:
    raise SystemExit("no DATABASE_URL_SYNC")
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://") :]
engine = create_engine(url)
with engine.connect() as conn:
    name = conn.exec_driver_sql("SELECT current_database()").scalar()
    print(f"current_database()={name}")
    print("readonly_ok")
