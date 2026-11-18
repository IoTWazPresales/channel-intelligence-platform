"""GET /ops/overview health block on cip_test: tenant-scoped expected-report counts and the
supervisor/backup status files (one rolled-back transaction)."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from app.api.v1.endpoints import ops as ops_endpoint
from app.db.session import AsyncSessionLocal
from app.models.customer_cst_report_slot import CustomerCstReportSlot
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from sqlalchemy import text

TAG = secrets.token_hex(3)
TA = f"opsh-a-{TAG}"
TB = f"opsh-b-{TAG}"


async def _session_or_skip():
    db = AsyncSessionLocal()
    name = (await db.execute(text("select current_database()"))).scalar_one()
    if name != "cip_test":
        await db.close()
        pytest.skip("cip_test only")
    return db


@pytest.mark.anyio
async def test_overview_health_counts_only_the_callers_tenant(tmp_path, monkeypatch):
    (tmp_path / "backups").mkdir()
    now_local = datetime.now().replace(microsecond=0)
    (tmp_path / "backups" / "last_backup.json").write_text(
        json.dumps(
            {
                "result": "ok",
                "finished": (now_local - timedelta(hours=2)).isoformat(),
                "verified": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ops_endpoint, "get_settings", lambda: SimpleNamespace(cip_ops_state_dir=str(tmp_path))
    )
    db = await _session_or_skip()
    try:
        ca1 = DimCustomer(code=f"opsh-{TAG}-a1", name=f"Ops A1 {TAG}", tenant_id=TA)
        ca2 = DimCustomer(code=f"opsh-{TAG}-a2", name=f"Ops A2 {TAG}", tenant_id=TA)
        cb1 = DimCustomer(code=f"opsh-{TAG}-b1", name=f"Ops B1 {TAG}", tenant_id=TB)
        db.add_all([ca1, ca2, cb1])
        await db.flush()
        db.add_all(
            [
                CustomerReportConfig(customer_id=ca1.id, reports_expected=True),
                CustomerReportConfig(customer_id=ca2.id, reports_expected=False),
                CustomerReportConfig(customer_id=cb1.id, reports_expected=True),
            ]
        )
        received = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
        db.add_all(
            [
                CustomerCstReportSlot(
                    customer_id=ca1.id,
                    week_start_date=date(2026, 11, 2),
                    status="received",
                    received_at=received,
                ),
                CustomerCstReportSlot(
                    customer_id=ca1.id, week_start_date=date(2026, 11, 9), status="late"
                ),
                CustomerCstReportSlot(
                    customer_id=ca2.id, week_start_date=date(2026, 11, 9), status="missing"
                ),
                # Tenant B: would show if it leaked.
                CustomerCstReportSlot(
                    customer_id=cb1.id, week_start_date=date(2026, 11, 9), status="late"
                ),
                CustomerCstReportSlot(
                    customer_id=cb1.id, week_start_date=date(2026, 11, 2), status="late"
                ),
                CustomerCstReportSlot(
                    customer_id=cb1.id,
                    week_start_date=date(2026, 10, 26),
                    status="received",
                    received_at=received + timedelta(days=5),
                ),
            ]
        )
        await db.flush()
        out = await ops_endpoint.ops_overview(
            db=db, user={"id": "1", "tenant_id": TA, "role": "admin"}, failed_limit=5
        )
        rep = out["health"]["reports"]
        # ca2 has reports_expected False: its retained missing slot does not count.
        assert rep["late"] == 1 and rep["missing"] == 0 and rep["expected_customers"] == 1
        assert rep["state"] == "late"
        assert rep["newest_received"] == received.isoformat()
        assert out["health"]["backups"]["backup"]["state"] == "ok"
        assert out["health"]["backups"]["restore"]["state"] == "unknown"
        assert out["health"]["services"]["state"] == "unknown"

        other = await ops_endpoint.ops_overview(
            db=db, user={"id": "1", "tenant_id": TB, "role": "admin"}, failed_limit=5
        )
        assert (
            other["health"]["reports"]["late"] == 2 and other["health"]["reports"]["missing"] == 0
        )
    finally:
        await db.rollback()
        await db.close()


@pytest.mark.anyio
async def test_overview_reports_pending_and_untracked_are_not_ok(tmp_path, monkeypatch):
    """Review fix P2: a due slot reads pending and an expected customer with no recent slot reads
    untracked; neither is 'ok' without receipt evidence."""
    monkeypatch.setattr(
        ops_endpoint, "get_settings", lambda: SimpleNamespace(cip_ops_state_dir=str(tmp_path))
    )
    tc, td = f"opsh-c-{TAG}", f"opsh-d-{TAG}"
    today = datetime.now(UTC).astimezone().date()
    last_week = today - timedelta(days=today.weekday() + 7)
    db = await _session_or_skip()
    try:
        c1 = DimCustomer(code=f"opsh-{TAG}-c1", name=f"Ops C1 {TAG}", tenant_id=tc)
        c2 = DimCustomer(code=f"opsh-{TAG}-c2", name=f"Ops C2 {TAG}", tenant_id=tc)
        d1 = DimCustomer(code=f"opsh-{TAG}-d1", name=f"Ops D1 {TAG}", tenant_id=td)
        db.add_all([c1, c2, d1])
        await db.flush()
        db.add_all(
            [
                CustomerReportConfig(customer_id=c1.id, reports_expected=True),
                CustomerReportConfig(customer_id=c2.id, reports_expected=True),
                CustomerReportConfig(customer_id=d1.id, reports_expected=True),
                CustomerCstReportSlot(customer_id=c1.id, week_start_date=last_week, status="due"),
                # A fresh upload for an older period must not hide this week's missing tracker.
                CustomerCstReportSlot(
                    customer_id=c2.id, week_start_date=last_week - timedelta(days=7),
                    status="received", received_at=datetime.now(UTC) - timedelta(days=1),
                ),
                CustomerCstReportSlot(customer_id=d1.id, week_start_date=last_week, status="due"),
            ]
        )
        await db.flush()
        mixed = await ops_endpoint.ops_overview(
            db=db, user={"id": "1", "tenant_id": tc, "role": "admin"}, failed_limit=5
        )
        rep = mixed["health"]["reports"]
        assert rep["due"] == 1 and rep["untracked_customers"] == 1 and rep["expected_customers"] == 2
        assert rep["state"] == "untracked" and rep["newest_received"] is not None

        pending = await ops_endpoint.ops_overview(
            db=db, user={"id": "1", "tenant_id": td, "role": "admin"}, failed_limit=5
        )
        rep = pending["health"]["reports"]
        assert rep["due"] == 1 and rep["untracked_customers"] == 0 and rep["state"] == "pending"
    finally:
        await db.rollback()
        await db.close()
