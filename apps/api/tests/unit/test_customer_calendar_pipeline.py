"""Calendar preview is read only; apply batches rows in the caller's transaction."""

from datetime import date
from unittest.mock import MagicMock

from app.services.cpor.customer_calendar import pipeline


def test_preview_without_a_saved_profile_never_writes(monkeypatch):
    db = MagicMock()
    db.scalar.return_value = None
    monkeypatch.setattr(pipeline, "_customer_names", lambda *args: {17: "Customer"})
    monkeypatch.setattr(pipeline, "is_reporting_customer", lambda *_a, **_k: True)
    monkeypatch.setattr(pipeline, "list_reporting_customers", lambda *_a: [{"id": 17}])
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
            "non_reporting_customers": [],
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


def test_listing_profiles_returns_a_computed_default_and_writes_nothing():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    out = pipeline.list_profiles(db, "tenant-a")
    assert [p["profile_code"] for p in out] == ["customer_calendar_default_v1"]
    assert out[0]["id"] is None and out[0]["is_default"] is True
    db.add.assert_not_called()
    db.flush.assert_not_called()
    db.commit.assert_not_called()
    statements = [call.args[0] for call in db.execute.call_args_list]
    assert not any(getattr(s, "is_insert", False) for s in statements)


def test_listing_profiles_keeps_saved_rows_and_a_saved_default_wins():
    saved = MagicMock()
    saved.configure_mock(
        id=7,
        profile_code="custom",
        display_name="Custom",
        header_row_index=2,
        sheet_name=None,
        column_map_json={"name": ["N"], "start_date": ["S"]},
        value_maps_json={"kind": {}},
        is_default=True,
        notes=None,
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [saved]
    out = pipeline.list_profiles(db, "tenant-a")
    assert [p["profile_code"] for p in out] == ["customer_calendar_default_v1", "custom"]
    assert [p["is_default"] for p in out] == [False, True]
    assert [p["id"] for p in out] == [None, 7]


def test_a_seeded_default_row_is_not_duplicated_by_the_computed_one():
    seeded = MagicMock()
    seeded.configure_mock(
        id=3,
        profile_code="customer_calendar_default_v1",
        display_name="Seeded",
        header_row_index=1,
        sheet_name=None,
        column_map_json={"name": ["N"], "start_date": ["S"]},
        value_maps_json={"kind": {}},
        is_default=True,
        notes=None,
    )
    db = MagicMock()
    db.scalars.return_value.all.return_value = [seeded]
    out = pipeline.list_profiles(db, "tenant-a")
    assert [p["id"] for p in out] == [3]


def test_named_generic_profile_can_preview_before_it_has_been_seeded(monkeypatch):
    db = MagicMock()
    db.scalar.return_value = None
    monkeypatch.setattr(pipeline, "_customer_names", lambda *args: {17: "Customer"})
    monkeypatch.setattr(pipeline, "is_reporting_customer", lambda *_a, **_k: True)
    monkeypatch.setattr(pipeline, "list_reporting_customers", lambda *_a: [{"id": 17}])
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
