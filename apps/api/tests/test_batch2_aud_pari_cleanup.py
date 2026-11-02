"""GOV-008 minor: the guarded cleanup of the leaked AUD-PARI test facts. cip_test only; every test rolls back."""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.models.iam import Tenant
from app.models.platform_audit import PlatformAuditEvent

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "remove_leaked_test_shipment_facts.py"


def _script():
    spec = importlib.util.spec_from_file_location("remove_leaked", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def world():
    with SessionLocal() as db:
        if db.scalar(text("select current_database()")) != "cip_test":
            pytest.skip("cip_test only")
        tenant = f"pari-{uuid.uuid4().hex[:8]}"
        db.add(Tenant(id=tenant, name="AUD-PARI fixture"))
        db.flush()

        def fact(item, *, job=None, qty=10):
            f = FactInboundShipment(
                tenant_id=tenant, import_job_id=job, source_key=f"audit-parity-fact-{uuid.uuid4().hex[:8]}",
                fact_upsert_key=f"ship:AUD-PAR|{item}|{uuid.uuid4().hex}", line_state="open_order", report_type="shipped",
                raw_source_row={}, item_code=item, quantity=qty, product_resolution_status="ok", distributor_resolution_status="ok",
                status="scheduled",
            )
            db.add(f)
            db.flush()
            return f

        leaked = [fact(f"AUD-PARI-{uuid.uuid4().hex[:6]}") for _ in range(3)]
        control = fact("REAL-ITEM-1")  # an ordinary fact with no job must survive
        yield db, tenant, leaked, control
        db.rollback()


def _count(db, ids):
    return db.scalar(text("SELECT count(*) FROM fact_inbound_shipment WHERE id = ANY(:ids)"), {"ids": list(ids)})


def test_dry_run_is_the_default_and_changes_nothing(world):
    db, tenant, leaked, control = world
    mod = _script()
    out = mod.execute(db, expect_db="cip_test", apply=False)
    assert {f.id for f in leaked} <= set(out["ids"]) and control.id not in out["ids"]
    assert out["matched"] >= 3 and out["apply"] is False
    assert _count(db, [f.id for f in leaked]) == 3 and "deleted" not in out
    with pytest.raises(Exception):  # the dry run is a READ ONLY transaction: a write is refused by the database
        db.execute(text("DELETE FROM fact_inbound_shipment WHERE id = :i"), {"i": control.id})


def test_apply_refuses_a_wrong_database_name_and_a_wrong_count(world):
    db, tenant, leaked, control = world
    mod = _script()
    with pytest.raises(SystemExit, match="current_database"):
        mod.execute(db, expect_db="cip", apply=True)
    with pytest.raises(SystemExit, match="expect-count"):
        mod.execute(db, expect_db="cip_test", apply=True, expect_count=2)
    assert _count(db, [f.id for f in leaked]) == 3


def test_apply_removes_exactly_the_leaked_facts_and_keeps_every_row_in_the_audit_event(world):
    db, tenant, leaked, control = world
    mod = _script()
    before = mod.find_leaked(db)
    ids = {int(r["id"]) for r in before}
    out = mod.execute(db, expect_db="cip_test", apply=True, expect_count=len(before))
    assert out["deleted"] == len(before) and ids >= {f.id for f in leaked}
    assert _count(db, ids) == 0 and _count(db, [control.id]) == 1
    event = db.scalars(select(PlatformAuditEvent).where(PlatformAuditEvent.action == "leaked_test_shipment_facts_removed")
                       .order_by(PlatformAuditEvent.id.desc())).first()
    assert event is not None and event.detail_json["count"] == len(before)
    assert {r["id"] for r in event.detail_json["removed_rows"]} == ids
    again = mod.execute(db, expect_db="cip_test", apply=False)
    assert again["matched"] == 0
