"""GOV-008 N-0065 VER2: NULL-product evidence rows visible to a no-lines user, base tables vs view (READ ONLY, cip)."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})

Q_OBS_KEYS_RESOLVED_ELSEWHERE = """
    select count(*) from shipment_evidence_observation o
    where o.product_id is null and o.line_identity_key in (
        select line_identity_key from shipment_evidence_observation where product_id is not null)
"""

with eng.connect() as c:
    db = c.execute(sa.text("select current_database()")).scalar_one()
    print("current_database() =", db, "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    assert db == "cip"
    c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    for t in ("shipment_evidence_observation", "shipment_evidence_line"):
        tot = c.execute(sa.text(f"select count(*) from {t}")).scalar_one()
        nul = c.execute(sa.text(f"select count(*) from {t} where product_id is null")).scalar_one()
        print(f"[*] {t}: total={tot} null_product={nul}")
    print("[*] observations with NULL product whose identity has a resolved observation =",
          c.execute(sa.text(Q_OBS_KEYS_RESOLVED_ELSEWHERE)).scalar_one())
    print("[*] observations with superseded_by_id NULL =", c.execute(sa.text(
        "select count(*) from shipment_evidence_observation where superseded_by_id is null")).scalar_one(),
        "| identities =", c.execute(sa.text(
        "select count(distinct line_identity_key) from shipment_evidence_observation where superseded_by_id is null")).scalar_one())
    c.rollback()
    c.execute(sa.text("select set_config('cip.product_lines', '!', true)"))
    for t in ("shipment_evidence_observation", "shipment_evidence_line"):
        print(f"['!'] {t}: visible={c.execute(sa.text(f'select count(*) from {t}')).scalar_one()}")
    print("['!'] shipment_evidence_current:", c.execute(sa.text("select count(*) from shipment_evidence_current")).scalar_one())
    c.rollback()
eng.dispose()
