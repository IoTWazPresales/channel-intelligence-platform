from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.db.sync_url import resolve_sync_engine_url

engine = create_engine(resolve_sync_engine_url(get_settings()))
with engine.connect() as conn:
    row = conn.execute(
        text(
            "SELECT id, case_code FROM cpor_case "
            "WHERE status <> 'cancelled' ORDER BY id DESC LIMIT 1"
        )
    ).one()
print(row[0])
print(row[1])
