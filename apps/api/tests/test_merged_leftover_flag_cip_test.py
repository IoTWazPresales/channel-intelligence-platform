"""BACKLOG-133/134 integration: shipment import-complete rail FLAGs merged-id leftovers.

Writes a tiny fixture (merged customer + distributor, aliases still on the losers, one
``inbound_shipments`` job) and cleans it up. Refuses ``cip``; run against ``cip_test``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.models.ingestion import ImportJob, ImportRowResult
from app.services.customer_leftover_repair import merged_id_leftover_check
from app.services.imports.merged_leftover_flag import (
    MERGED_LEFTOVER_FLAG_CODE,
    MERGED_LEFTOVER_META_KEY,
)


def _ins(db, sql: str, **p) -> int:
    return int(db.execute(text(sql + " RETURNING id"), p).scalar())


@pytest.fixture
def leftover_fixture(monkeypatch: pytest.MonkeyPatch):
    import app.services.report_schedule_runner as rsr
    import app.services.shipping_digest.dispatch as sdd

    # Keep the rail's unrelated best-effort side effects out of the fixture.
    monkeypatch.setattr(rsr, "dispatch_import_complete_report_fanout", lambda **k: None)
    monkeypatch.setattr(sdd, "dispatch_shipping_digest", lambda **k: None)

    db = SessionLocal()
    dbname = db.execute(text("select current_database()")).scalar()
    print(f"\ncurrent_database() = {dbname}")
    assert dbname != "cip", "integration fixture writes; never run on cip"
    tag = uuid.uuid4().hex[:10]
    before = merged_id_leftover_check(db)
    ids: dict[str, int] = {}
    try:
        ids["cw"] = _ins(
            db,
            "INSERT INTO dim_customer (code, name, customer_status, is_key_account) "
            "VALUES (:c, :n, 'active', false)",
            c=f"N51W-{tag}", n=f"N51 winner {tag}",
        )
        ids["cl"] = _ins(
            db,
            "INSERT INTO dim_customer (code, name, customer_status, is_key_account, merged_into_customer_id) "
            "VALUES (:c, :n, 'merged', false, :w)",
            c=f"N51L-{tag}", n=f"N51 loser {tag}", w=ids["cw"],
        )
        ids["dw"] = _ins(
            db,
            "INSERT INTO dim_distributor (code, name, distributor_status) VALUES (:c, :n, 'active')",
            c=f"N51DW-{tag}", n=f"N51 dist winner {tag}",
        )
        ids["dl"] = _ins(
            db,
            "INSERT INTO dim_distributor (code, name, distributor_status, merged_into_distributor_id) "
            "VALUES (:c, :n, 'merged', :w)",
            c=f"N51DL-{tag}", n=f"N51 dist loser {tag}", w=ids["dw"],
        )
        ids["ca"] = _ins(
            db,
            "INSERT INTO customer_source_token_alias (customer_id, raw_token, normalized_token, status) "
            "VALUES (:c, :t, :t, 'active')",
            c=ids["cl"], t=f"n51-cust-{tag}",
        )
        ids["da"] = _ins(
            db,
            "INSERT INTO distributor_source_token_alias (distributor_id, raw_token, normalized_token, status) "
            "VALUES (:d, :t, :t, 'active')",
            d=ids["dl"], t=f"n51-dist-{tag}",
        )
        src = int(db.execute(text("SELECT min(id) FROM source_definition")).scalar())
        job = ImportJob(
            source_id=src,
            template_slug="inbound_shipments",
            import_mode="apply",
            status="running",
            stage="validated",
            file_name=f"n51_{tag}.xlsx",
        )
        db.add(job)
        db.commit()
        ids["job"] = int(job.id)
        yield db, ids, before
    finally:
        db.rollback()
        if "job" in ids:
            db.execute(text("DELETE FROM import_row_result WHERE job_id = :j"), {"j": ids["job"]})
            db.execute(text("DELETE FROM import_job WHERE id = :j"), {"j": ids["job"]})
        for tbl, key in (
            ("customer_source_token_alias", "ca"),
            ("distributor_source_token_alias", "da"),
            ("dim_customer", "cl"),
            ("dim_customer", "cw"),
            ("dim_distributor", "dl"),
            ("dim_distributor", "dw"),
        ):
            if key in ids:
                db.execute(text(f"DELETE FROM {tbl} WHERE id = :i"), {"i": ids[key]})
        db.commit()
        after = merged_id_leftover_check(db)
        print(f"after cleanup total_leftover_rows={after['total_leftover_rows']} (before {before['total_leftover_rows']})")
        assert after["total_leftover_rows"] == before["total_leftover_rows"]
        db.close()


def test_shipment_complete_rail_flags_merged_leftovers(leftover_fixture) -> None:
    from app.services.imports.shipment_apply_sync import run_shipment_apply_sync

    db, ids, before = leftover_fixture
    out = run_shipment_apply_sync(db, ids["job"])
    db.expire_all()

    job = db.get(ImportJob, ids["job"])
    assert job.status == "completed"  # FLAG, not BLOCK
    meta = job.staged_metadata[MERGED_LEFTOVER_META_KEY]
    print(
        f"outcome={out.get('outcome')} status={job.status} flag={meta['flag']} "
        f"total={meta['total_leftover_rows']} (baseline {before['total_leftover_rows']}) "
        f"customer={meta['customer_fk_counts']} distributor={meta['distributor_fk_counts']}"
    )
    assert meta["flag"] is True
    assert meta["total_leftover_rows"] == before["total_leftover_rows"] + 2
    assert meta["customer_fk_counts"].get("customer_source_token_alias.customer_id", 0) >= 1
    assert meta["distributor_fk_counts"].get("distributor_source_token_alias.distributor_id", 0) >= 1
    warn = (
        db.query(ImportRowResult)
        .filter(ImportRowResult.job_id == ids["job"], ImportRowResult.code == MERGED_LEFTOVER_FLAG_CODE)
        .all()
    )
    assert len(warn) == 1 and warn[0].severity == "warning"
    print(f"warning row: {warn[0].message}")
    # Detection only: the loser aliases were not repointed.
    assert db.execute(
        text("SELECT customer_id FROM customer_source_token_alias WHERE id = :i"), {"i": ids["ca"]}
    ).scalar() == ids["cl"]
