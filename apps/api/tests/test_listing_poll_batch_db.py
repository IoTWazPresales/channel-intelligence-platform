"""A listing poll yields after one batch so an import starts within 10 seconds.

Fixtures are inserted on cip_test and always rolled back. No network.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.listing_capture import CustomerListing, ListingObservation
from app.models.listing_site import ListingSite
from app.services.listing_capture.registry import poll_active_listings
from app.worker.tasks import listing_capture_poll_listings_task, process_import_job_task


@pytest.fixture()
def db_session():
    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url)
    try:
        conn = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = conn.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        conn.close()
        eng.dispose()
        pytest.skip(f"poll batch DB test runs on cip_test only (current_database()={db})")
    conn.rollback()
    tx = conn.begin()
    session = Session(bind=conn)
    try:
        yield session
    finally:
        session.close()
        tx.rollback()
        conn.close()
        eng.dispose()


def test_import_starts_within_10s_while_poll_batches(db_session: Session, monkeypatch, caplog) -> None:
    # Fictional customer, site and import source in a fresh tenant (rolled back).
    tag = uuid.uuid4().hex[:8]
    tenant = f"t-poll-{tag}"
    customer = DimCustomer(
        code=f"PB-{tag}", name=f"Poll Batch {tag}", customer_status="active", is_key_account=False, tenant_id=tenant
    )
    template = ImportTemplate(slug=f"pb-{tag}", display_name="Poll batch proof", pipeline_handler="inbound_shipments")
    db_session.add_all([customer, template])
    db_session.flush()
    source = SourceDefinition(
        import_template_id=int(template.id), code=f"pb-{tag}", name="Poll batch proof", source_kind="file"
    )
    db_session.add(source)
    marketplace = "pb" + tag
    db_session.add(
        ListingSite(
            tenant_id=tenant,
            site_key=marketplace,
            display_name="Poll batch site",
            adapter_key="html_page",
            rate_limit_seconds=1.0,
        )
    )
    db_session.flush()
    customer_id, source_id = int(customer.id), int(source.id)
    listings = []
    for i in range(50):
        row = CustomerListing(
            customer_id=int(customer_id),
            url=f"https://example.test/{marketplace}/{i}-{uuid.uuid4().hex}",
            marketplace=marketplace,
            status="active",
            source="manual",
        )
        db_session.add(row)
        listings.append(row)
    db_session.flush()
    listing_ids = [int(row.id) for row in listings]

    job = ImportJob(
        source_id=int(source_id),
        file_name="poll-batch-proof.csv",
        status="pending",
        stage="uploaded",
        template_slug="inbound_shipments",
    )
    db_session.add(job)
    db_session.flush()
    job_id = int(job.id)

    class _SameSession:
        def __enter__(self):
            return db_session

        def __exit__(self, *_exc):
            return False

    monkeypatch.setattr("app.db.session_sync.SessionLocal", lambda: _SameSession())
    monkeypatch.setattr(db_session, "commit", db_session.flush)
    monkeypatch.setenv("CIP_LISTING_LIVE_FETCH", "1")
    monkeypatch.setenv("CIP_LISTING_CAPTURE_SCHEDULE", "1")
    monkeypatch.setattr("app.worker.celery_queues.dev_beat_disabled", lambda: False)

    real_poll = poll_active_listings

    def _only_fixtures(session, **kwargs):
        kwargs["marketplaces"] = [marketplace]
        return real_poll(session, **kwargs)

    monkeypatch.setattr("app.services.listing_capture.registry.poll_active_listings", _only_fixtures)

    calls: list[float] = []
    submitted: dict[str, float] = {}
    batch_q: list[int] = []

    def http_get(_url: str, headers=None):
        calls.append(time.monotonic())
        if len(calls) == 1:
            submitted["t"] = calls[0]
            batch_q.append(job_id)
        return 200, json.dumps({"price": 10.0, "availability": "in_stock"})

    monkeypatch.setattr("app.services.listing_capture.observation.default_http_get", http_get)

    celery_q: list[dict] = []

    def _enqueue(*_a, **kwargs):
        celery_q.append(kwargs["kwargs"]["run"])

    monkeypatch.setattr(listing_capture_poll_listings_task, "apply_async", _enqueue)

    started: dict[str, float] = {}

    def _fake_process(db, import_job_id, on_progress=None):
        started["t"] = time.monotonic()
        row = db.get(ImportJob, import_job_id)
        row.status = "running"
        row.started_at = datetime.now(timezone.utc)
        db.flush()

    monkeypatch.setattr("app.worker.tasks.process_import_job_sync", _fake_process)
    monkeypatch.setattr("app.worker.tasks._persist_process_job_celery_slot", lambda *_a, **_k: None)

    def _run_import(import_job_id: int) -> None:
        process_import_job_task.run(import_job_id)

    with caplog.at_level(logging.INFO, logger="app.worker.tasks"):
        out = listing_capture_poll_listings_task()
        guard = 0
        while out.get("continued"):
            guard += 1
            assert guard < 20
            if batch_q:
                _run_import(batch_q.pop(0))
            assert celery_q, "a full batch must enqueue the next one"
            out = listing_capture_poll_listings_task(run=celery_q.pop(0))

    assert started["t"] - submitted["t"] < 10
    assert len(calls) >= 6
    assert started["t"] < calls[5]
    assert out["skipped"] is False
    assert out["polled"] == 50
    assert out["stopped_reason"] is None
    poll_logs = [r for r in caplog.records if r.message.startswith("listing capture poll:")]
    assert len(poll_logs) == 1
    assert db_session.get(ImportJob, job_id).status == "running"

    counts = dict(
        db_session.execute(
            select(ListingObservation.listing_id, func.count())
            .where(ListingObservation.listing_id.in_(listing_ids))
            .group_by(ListingObservation.listing_id)
        ).all()
    )
    assert set(counts) == set(listing_ids)
    assert set(counts.values()) == {1}
