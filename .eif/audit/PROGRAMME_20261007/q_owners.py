"""Read-only: who owns the objects migration 0025 changes on cip (prints no credentials)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "apps" / "api"))

import sqlalchemy as sa
from sqlalchemy.engine import make_url

from app.core.config import get_settings

url = make_url(get_settings().database_url_sync).set(drivername="postgresql+psycopg")
engine = sa.create_engine(url)
with engine.connect() as conn:
    conn.execute(sa.text("SET TRANSACTION READ ONLY"))
    print("database:", conn.execute(sa.text("select current_database()")).scalar(),
          "user:", conn.execute(sa.text("select current_user")).scalar())
    rows = conn.execute(sa.text(
        """
        select pg_get_userbyid(c.relowner) as owner, count(*)
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relrowsecurity
        group by 1 order by 2 desc
        """
    )).all()
    print("RLS tables by owner:", rows)
    print("functions:", conn.execute(sa.text(
        "select proname, pg_get_userbyid(proowner) from pg_proc where proname like 'cip_product%' order by 1"
    )).all())
    print("views:", conn.execute(sa.text(
        """
        select c.relname, pg_get_userbyid(c.relowner)
        from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind in ('v','m') order by 1
        """
    )).all())
    print("cip role:", conn.execute(sa.text(
        "select rolsuper, rolcreaterole, rolcreatedb, rolbypassrls from pg_roles where rolname = current_user"
    )).one())
    print("cip member of:", conn.execute(sa.text(
        "select r.rolname from pg_auth_members m join pg_roles r on r.oid = m.roleid "
        "where m.member = (select oid from pg_roles where rolname = current_user)"
    )).scalars().all())
