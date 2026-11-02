"""Apply alembic 20261102_0051 to cip as the table owner (postgres login, credential from the PG_OWNER env var, never printed). ONE attempt.

    apps/api/.venv/Scripts/python.exe -X utf8 .eif/audit/REVIEW_20261102/deploy/apply_migration.py
"""
import os
import subprocess
import sys

sys.path.insert(0, "apps/api")

from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402

owner_cred = os.environ["PG_OWNER"]
app_url = make_url(get_settings().database_url_sync)
if app_url.database != "cip":
    raise SystemExit("STOP: app URL does not point at cip")
owner_url = app_url.set(drivername="postgresql+psycopg", username="postgres", password=owner_cred)

env = dict(os.environ)
env["DATABASE_URL_SYNC"] = app_url.render_as_string(hide_password=False)
env["DATABASE_URL_SYNC_MIGRATE"] = owner_url.render_as_string(hide_password=False)
env.pop("CIP_SMOKE_MIGRATE", None)
print("target:", app_url.render_as_string(hide_password=True), "| migrate as", owner_url.render_as_string(hide_password=True))
for args in (["current"], ["upgrade", "20261102_0051"], ["current"]):
    p = subprocess.run([sys.executable, "-m", "alembic", *args], cwd="apps/api", env=env, capture_output=True, text=True)
    out = (p.stdout + p.stderr).replace(owner_cred, "***")
    print("== alembic", " ".join(args), "exit", p.returncode)
    print(out.strip())
    if p.returncode != 0:
        raise SystemExit(p.returncode)
