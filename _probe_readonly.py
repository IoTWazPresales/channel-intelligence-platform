"""Read-only cip probe. No writes."""
from __future__ import annotations
import sys
from pathlib import Path
API = Path(r"C:\Users\warren_eliason\channel-intelligence-platform\apps\api")
sys.path.insert(0, str(API))
from sqlalchemy import create_engine, text
from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
DRIFT = """
SELECT id, case_code, status, workflow_status
FROM cpor_case
WHERE workflow_status IS DISTINCT FROM (
  CASE WHEN status = 'proposed' THEN 'pending_approval' ELSE status END
)
ORDER BY id
"""
def main() -> int:
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database()", db)
        if db != "cip":
            print("STOP")
            return 2
        ver = [r[0] for r in conn.execute(text("SELECT version_num FROM alembic_version"))]
        print("alembic_version", ver)
        print("cpor_case", conn.execute(text("SELECT count(*) FROM cpor_case")).scalar())
        print("drift_rows")
        n = 0
        for row in conn.execute(text(DRIFT)):
            n += 1
            print(" ", row[0], row[1], row[2], row[3])
        print("drift_count", n)
        names = [r[0] for r in conn.execute(text("SELECT datname FROM pg_database WHERE datname LIKE 'cip%' ORDER BY 1"))]
        print("databases", ",".join(names))
        conn.rollback()
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
