"""Read-only probe on cip. usage: python ro_probe.py <sql-file-or-inline> ; prints current_database() first.
Never writes: the connection is read-only. Passwords are never printed."""
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse
API = Path(__file__).resolve().parents[4] / "apps" / "api"
sys.path.insert(0, str(API))
import psycopg
from app.core.config import get_settings

def url_for(db):
    s = get_settings()
    raw = s.database_url_sync.replace("postgresql+psycopg://", "postgresql://")
    return urlunparse(urlparse(raw)._replace(path="/" + db))

db = sys.argv[1]
sql = sys.argv[2]
with psycopg.connect(url_for(db)) as conn:
    conn.read_only = True
    print("current_database() =", conn.execute("select current_database()").fetchone()[0], "| user", conn.execute("select current_user").fetchone()[0], flush=True)
    cur = conn.execute(sql)
    cols = [d.name for d in cur.description]
    print(" | ".join(cols))
    for r in cur.fetchall():
        print(" | ".join("" if v is None else str(v) for v in r))
