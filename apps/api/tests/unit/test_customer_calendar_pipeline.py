"""Calendar preview is read only; apply batches rows in the caller's transaction."""

from datetime import date
from unittest.mock import MagicMock

from app.services.cpor.customer_calendar import pipeline


def test_preview_without_a_saved_profile_never_writes(monkeypatch):
    db = MagicMock()
    db.scalar.return_value = None
    monkeypatch.setattr(pipeline, "_customer_names", lambda *args: {17: "Customer"})
    out = pipeline.preview_upload(
        db,
        "tenant-a",
        filename="calendar.csv",
        data=b"Name,Start\nCampaign,2026-03-01\n",
        customer_id=17,
    )
    assert out["ok"] is True
    assert out["will_insert"] == 1
    db.add.assert_not_called()
    db.flush.assert_not_called()
    db.commit.assert_not_called()


def test_apply_uses_bulk_insert_and_leaves_commit_to_audited_endpoint(monkeypatch):
    db = MagicMock()
    db.execute.return_value.rowcount = 2
    event = {
        "customer_id": 17,
        "row_number": 2,
        "name": "Campaign",
        "kind": "campaign",
        "start_date": date(2026, 3, 1),
        "end_date": date(2026, 3, 5),
        "raw_row": {},
    }
    monkeypatch.setattr(
        pipeline,
        "_plan",
        lambda *args, **kwargs: {
            "parsed": {"blocking_errors": [], "row_errors": []},
            "placed": [event, {**event, "row_number": 3, "name": "Pillar"}],
            "upload_id": "same-upload",
            "file_sha256": "f" * 64,
            "profile_id": None,
            "customers": [],
            "unresolved": [],
        },
    )
    out = pipeline.apply_upload(db, "tenant-a", filename="calendar.csv", data=b"bytes")
    assert (out["inserted"], out["replaced"]) == (2, 2)
    db.add.assert_not_called()
    db.commit.assert_not_called()
    inserts = [
        call for call in db.execute.call_args_list if getattr(call.args[0], "is_insert", False)
    ]
    assert len(inserts) == 1
    assert [row["name"] for row in inserts[0].args[1]] == ["Campaign", "Pillar"]
    assert all(row["tenant_id"] == "tenant-a" for row in inserts[0].args[1])


def test_named_generic_profile_can_preview_before_it_has_been_seeded(monkeypatch):
    db = MagicMock()
    db.scalar.return_value = None
    monkeypatch.setattr(pipeline, "_customer_names", lambda *args: {17: "Customer"})
    out = pipeline.preview_upload(
        db,
        "tenant-a",
        filename="calendar.csv",
        data=b"Name,Start\nEvent,2026-03-01\n",
        profile_code="customer_calendar_default_v1",
        customer_id=17,
    )
    assert out["ok"]
    db.add.assert_not_called()
