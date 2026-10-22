"""N-0113 (Warren 2026-10-22): archive and unarchive import jobs by id, admin only.

The preview lists each job with its status and whether it would change; the confirm sets
``archived_at`` (unarchive clears it) and writes a ``platform_audit_event`` with the ids. No data
row changes: the job keeps its status, staging, row results and the facts it loaded.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.session_sync import SessionLocal
from app.main import app
from app.models.facts import FactInventoryDistributor, FactSalesSellout
from app.models.import_distributor_si import ImportDistributorSiStagingLine
from app.models.ingestion import ImportJob, ImportRowResult
from app.models.platform_audit import PlatformAuditEvent
from tests.test_import_job_bulk_delete import _seed_job_with_artifacts, _skip_mutations_on_shared_cip

ADMIN = {"X-User-Role": "admin", "X-User-Id": "test"}
PREVIEW = "/api/v1/imports/jobs/bulk-archive-preview"
CONFIRM = "/api/v1/imports/jobs/bulk-archive-confirm"


def _data_counts(session, job_id: int) -> tuple:
    def n(model, col) -> int:
        return int(session.scalar(select(func.count()).select_from(model).where(col == job_id)) or 0)

    job = session.get(ImportJob, job_id)
    return (
        job.status,
        job.stage,
        n(ImportRowResult, ImportRowResult.job_id),
        n(ImportDistributorSiStagingLine, ImportDistributorSiStagingLine.import_job_id),
        n(FactSalesSellout, FactSalesSellout.source_import_job_id),
        n(FactInventoryDistributor, FactInventoryDistributor.source_import_job_id),
    )


def _archived_at(job_id: int):
    with SessionLocal() as s:
        return s.get(ImportJob, job_id).archived_at


def _last_audit(action: str) -> PlatformAuditEvent | None:
    with SessionLocal() as s:
        return s.scalar(
            select(PlatformAuditEvent).where(PlatformAuditEvent.action == action).order_by(PlatformAuditEvent.id.desc())
        )


@pytest.mark.parametrize("path", [PREVIEW, CONFIRM])
def test_archive_requires_admin(path: str) -> None:
    with TestClient(app) as client:
        r = client.post(path, json={"job_ids": [1], "archive": True},
                        headers={"X-User-Role": "planner", "X-User-Id": "planner-probe"})
        assert r.status_code == 403


def test_archive_then_unarchive_changes_only_archived_at() -> None:
    _skip_mutations_on_shared_cip()
    with SessionLocal() as session:
        job_id = _seed_job_with_artifacts(session)
        before = _data_counts(session, job_id)
    assert before[4] >= 1 and before[5] >= 1  # it loaded facts

    try:
        with TestClient(app) as client:
            pr = client.post(PREVIEW, json={"job_ids": [job_id], "archive": True}, headers=ADMIN)
            assert pr.status_code == 200
            body = pr.json()
            assert body["action"] == "archive" and body["missing_job_ids"] == []
            (job,) = body["jobs"]
            assert (job["id"], job["status"], job["archived_at"], job["will_change"]) == (
                job_id, before[0], None, True)
            assert (body["to_change"], body["unchanged"]) == (1, 0)
            assert _archived_at(job_id) is None  # the preview writes nothing

            cr = client.post(CONFIRM, json={"job_ids": [job_id], "archive": True}, headers=ADMIN)
            assert cr.status_code == 200
            assert cr.json()["changed_ids"] == [job_id]
            assert _archived_at(job_id) is not None
            with SessionLocal() as session:
                assert _data_counts(session, job_id) == before
            ev = _last_audit("import_jobs_archive")
            assert ev is not None and ev.area == "admin" and ev.detail_json["job_ids"] == [job_id]
            assert ev.detail_json["changed_ids"] == [job_id]

            listed = client.get("/api/v1/imports/jobs?limit=200", headers=ADMIN).json()
            items = listed["items"] if isinstance(listed, dict) else listed
            assert job_id not in {i["id"] for i in items}
            listed = client.get("/api/v1/imports/jobs?limit=200&include_archived=true", headers=ADMIN).json()
            items = listed["items"] if isinstance(listed, dict) else listed
            assert job_id in {i["id"] for i in items}

            # Archiving again changes nothing; the preview says so.
            again = client.post(PREVIEW, json={"job_ids": [job_id], "archive": True}, headers=ADMIN).json()
            assert (again["to_change"], again["unchanged"], again["jobs"][0]["will_change"]) == (0, 1, False)

            ur = client.post(CONFIRM, json={"job_ids": [job_id], "archive": False}, headers=ADMIN)
            assert ur.status_code == 200 and ur.json()["changed_ids"] == [job_id]
            assert _archived_at(job_id) is None
            with SessionLocal() as session:
                assert _data_counts(session, job_id) == before
            ev = _last_audit("import_jobs_unarchive")
            assert ev is not None and ev.detail_json["job_ids"] == [job_id]
    finally:
        with TestClient(app) as client:
            client.post("/api/v1/imports/jobs/bulk-delete-confirm", json={"job_ids": [job_id]}, headers=ADMIN)


def test_archive_with_a_missing_id_changes_nothing() -> None:
    _skip_mutations_on_shared_cip()
    with SessionLocal() as session:
        job_id = _seed_job_with_artifacts(session)
        missing = int(session.scalar(select(func.max(ImportJob.id)))) + 1000
    try:
        with TestClient(app) as client:
            pr = client.post(PREVIEW, json={"job_ids": [job_id, missing], "archive": True}, headers=ADMIN)
            assert pr.status_code == 200 and pr.json()["missing_job_ids"] == [missing]
            cr = client.post(CONFIRM, json={"job_ids": [job_id, missing], "archive": True}, headers=ADMIN)
            assert cr.status_code == 409
            assert _archived_at(job_id) is None
    finally:
        with TestClient(app) as client:
            client.post("/api/v1/imports/jobs/bulk-delete-confirm", json={"job_ids": [job_id]}, headers=ADMIN)


def test_archive_refuses_more_than_200_ids() -> None:
    with TestClient(app) as client:
        r = client.post(PREVIEW, json={"job_ids": list(range(1, 202)), "archive": True}, headers=ADMIN)
        assert r.status_code in (400, 422)
