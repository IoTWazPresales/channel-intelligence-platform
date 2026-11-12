"""Find a local superuser login. Prints no secrets."""

import os
from pathlib import Path

from sqlalchemy import create_engine, text

print("PGPASSWORD_set", bool(os.environ.get("PGPASSWORD")))
home = Path.home()
appdata = Path(os.environ.get("APPDATA", ""))
candidates = [
    home / ".pgpass",
    appdata / "postgresql" / "pgpass.conf",
]
for path in candidates:
    print("pgpass_exists", path.name, path.exists())

urls = [
    "postgresql+psycopg://postgres@127.0.0.1:5432/postgres",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/postgres",
    "postgresql+psycopg://postgres:cip@127.0.0.1:5432/postgres",
]
for url in urls:
    label = url.split("@", 1)[0].rsplit(":", 1)[0]
    try:
        engine = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            print("ok", label, "db", conn.execute(text("SELECT current_database()")).scalar_one(),
                  "user", conn.execute(text("SELECT current_user")).scalar_one())
        break
    except Exception as exc:
        print("fail", label, type(exc).__name__, str(exc).splitlines()[0][:160])
