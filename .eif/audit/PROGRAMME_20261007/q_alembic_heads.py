"""Read-only: alembic revision on cip and cip_test (prints no credentials)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "apps" / "api"))

import sqlalchemy as sa
from sqlalchemy.engine import make_url

from app.core.config import get_settings

base = make_url(get_settings().database_url_sync).set(drivername="postgresql+psycopg")
for db in ("cip", "cip_test"):
    engine = sa.create_engine(base.set(database=db))
    with engine.connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        name = conn.execute(sa.text("select current_database()")).scalar()
        rev = conn.execute(sa.text("select version_num from alembic_version")).scalars().all()
        fn = conn.execute(sa.text(
            "select count(*) from pg_proc where proname like 'cip_product%'"
        )).scalar()
        view = conn.execute(sa.text(
            "select coalesce(array_to_string(reloptions, ','), '') from pg_class "
            "where relname = 'shipment_evidence_current'"
        )).scalar()
        print(f"{name}: alembic={rev} cip_product_* functions={fn} shipment_evidence_current options='{view}'")
    engine.dispose()
