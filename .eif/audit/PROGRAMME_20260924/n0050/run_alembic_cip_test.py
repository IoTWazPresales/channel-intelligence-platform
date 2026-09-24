"""N-0050: run an alembic command against cip_test ONLY (never prints credentials).

Usage: run_alembic_cip_test.py [--schema NAME] <alembic args...>
  e.g. run_alembic_cip_test.py upgrade 20260906_0022
       run_alembic_cip_test.py --schema n0050_scratch upgrade head

--schema sets search_path to that scratch schema (the scratch copy of cpor_case /
cpor_case_line + its own alembic_version). Prints current_database() and
search_path from the same URL before handing over to alembic.
"""
import os
import sys
from urllib.parse import quote, urlparse, urlunparse

API = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "apps", "api"))
sys.path.insert(0, API)
os.chdir(API)

args = sys.argv[1:]
schema = None
if args and args[0] == "--schema":
    schema = args[1]
    args = args[2:]

from app.core.config import get_settings  # noqa: E402

TARGET = "cip_test"
s = get_settings()


def swap(u: str) -> str:
    p = urlparse(u)._replace(path="/" + TARGET)
    if schema:
        opt = "options=" + quote(f"-csearch_path={schema}")
        p = p._replace(query=(p.query + "&" if p.query else "") + opt)
    return urlunparse(p)


url = swap(s.database_url_sync)
assert urlparse(url).path == "/" + TARGET
os.environ["DATABASE_URL"] = swap(s.database_url)
os.environ["DATABASE_URL_SYNC"] = url
os.environ["DATABASE_URL_SYNC_MIGRATE"] = url
os.environ["CIP_SMOKE_MIGRATE"] = "1"
get_settings.cache_clear()

from sqlalchemy import create_engine, text  # noqa: E402

from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

eng = create_engine(sqlalchemy_sync_engine_url(url))
with eng.connect() as c:
    db = c.execute(text("select current_database()")).scalar_one()
    sp = c.execute(text("show search_path")).scalar_one()
    print(f"current_database() = {db}  search_path = {sp}")
    if db != TARGET:
        raise SystemExit(f"refusing: current_database()={db} != {TARGET}")
eng.dispose()

from alembic.config import main  # noqa: E402

main(argv=args)
