"""Split Compuspeed (1152) and Syntech (4145) off OPEN_CHANNEL.

The 2026-08-08 absorb merged those two provisional customers into customer 1 and
repointed every customer foreign key. It did not keep the row ids, and both
customers now have zero foreign keys, so this script does not move facts,
aliases, or shipments. It only clears the merge on these two rows.

Distributors 12 (Compuspeed) and 51 (Syntech) are not modified. They were not merged.

Status goes back to ``unverified`` (the TMP-CUST status). ``--apply`` commits.
Default is a dry run. ``--expect-db`` must equal ``current_database()``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

WORKTREE_API = Path(__file__).resolve().parents[2]
MAIN_API = Path(__file__).resolve().parents[6] / "apps" / "api"
sys.path.insert(0, str(MAIN_API))
sys.path.insert(0, str(WORKTREE_API))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.services.customer_full_repoint import count_customer_fk_refs  # noqa: E402
from app.services.steward_audit import record_steward_audit_sync  # noqa: E402

TARGETS = (
    (1152, "TMP-CUST-20260607200144-FECF", "Compuspeed LTD"),
    (4145, "TMP-CUST-20260608094305-EB7E", "SYNTECH DISTRIBUTION (PTY) LTD"),
)
RESTORED_STATUS = "unverified"
OPEN_CHANNEL_ID = 1


def _rewrite_dbname(url: str, dbname: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{dbname}"))


def _identity(db: Session) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT id, code, name, customer_status, merged_into_customer_id,
                   tenant_id, preferred_distributor_id
            FROM dim_customer
            WHERE id = ANY(:ids)
            ORDER BY id
            """
        ),
        {"ids": [row[0] for row in TARGETS] + [OPEN_CHANNEL_ID]},
    ).mappings()
    return [dict(row) for row in rows]


def _other_open_channel_losers(db: Session) -> list[int]:
    rows = db.execute(
        text(
            """
            SELECT id FROM dim_customer
            WHERE merged_into_customer_id = :oc AND id <> ALL(:ids)
            ORDER BY id
            """
        ),
        {"oc": OPEN_CHANNEL_ID, "ids": [row[0] for row in TARGETS]},
    )
    return [int(row[0]) for row in rows]


def _distributors(db: Session) -> list[tuple]:
    rows = db.execute(
        text(
            """
            SELECT id, code, name, merged_into_distributor_id
            FROM dim_distributor
            WHERE id IN (12, 51)
            ORDER BY id
            """
        )
    )
    return [tuple(row) for row in rows]


def run(db: Session, *, apply: bool) -> int:
    print("current_database()", db.execute(text("SELECT current_database()")).scalar())
    print("alembic", [r[0] for r in db.execute(text("SELECT version_num FROM alembic_version"))])
    found = {int(row["id"]): row for row in _identity(db)}
    print("before", found)
    print("distributors", _distributors(db))
    others = _other_open_channel_losers(db)
    print("other_customers_merged_into_open_channel", others)
    hist = db.execute(
        text(
            """
            SELECT customer_status, count(*)
            FROM dim_customer
            WHERE code LIKE 'TMP-CUST-%'
            GROUP BY customer_status
            ORDER BY customer_status
            """
        )
    )
    print("tmp_customer_status", [tuple(row) for row in hist])

    already = []
    pending = []
    for cid, code, name in TARGETS:
        row = found.get(cid)
        if row is None:
            print("STOP missing", cid)
            return 2
        if row["code"] != code or row["name"] != name:
            print("STOP identity", cid, row["code"], row["name"])
            return 2
        if row["customer_status"] == RESTORED_STATUS and row["merged_into_customer_id"] is None:
            already.append(cid)
            continue
        if row["customer_status"] != "merged" or row["merged_into_customer_id"] != OPEN_CHANNEL_ID:
            print("STOP unexpected merge state", cid, row["customer_status"], row["merged_into_customer_id"])
            return 2
        refs = count_customer_fk_refs(db, cid)
        print("fk", cid, refs)
        if refs:
            print("STOP foreign keys remain; this script does not move them", cid)
            return 2
        pending.append(row)

    dists = _distributors(db)
    if [item[0] for item in dists] != [12, 51]:
        print("STOP distributors", dists)
        return 2
    if any(item[3] is not None for item in dists):
        print("STOP a distributor is itself merged", dists)
        return 2

    if not pending:
        print("already split", already)
        print("rows updated: 0")
        print("mode:", "APPLY (commit)" if apply else "DRY RUN (rollback)")
        return 0

    for row in pending:
        result = db.execute(
            text(
                """
                UPDATE dim_customer
                SET customer_status = :status,
                    merged_into_customer_id = NULL
                WHERE id = :id
                  AND code = :code
                  AND name = :name
                  AND customer_status = 'merged'
                  AND merged_into_customer_id = 1
                """
            ),
            {
                "status": RESTORED_STATUS,
                "id": int(row["id"]),
                "code": row["code"],
                "name": row["name"],
            },
        )
        print("updated", int(row["id"]), result.rowcount)
        if result.rowcount != 1:
            print("STOP rowcount", int(row["id"]), result.rowcount)
            db.rollback()
            return 2
        record_steward_audit_sync(
            {"tenant_id": row["tenant_id"], "display_name": "queue-step8"},
            action="customer_identity_unmerge",
            importer="queue",
            entity_type="customer",
            entity_token=row["code"],
            target_dim="dim_customer",
            target_id=int(row["id"]),
            payload={
                "customer_status_before": "merged",
                "customer_status_after": RESTORED_STATUS,
                "merged_into_customer_id_before": OPEN_CHANNEL_ID,
                "merged_into_customer_id_after": None,
                "facts_moved": 0,
                "reason": "distributor reporting keeps Compuspeed and Syntech separate; no stored row ids to reverse the 2026-08-08 absorb",
            },
            db=db,
        )

    after_others = _other_open_channel_losers(db)
    if after_others != others:
        print("STOP other losers changed", others, after_others)
        db.rollback()
        return 2
    print("after", _identity(db))
    print("distributors_after", _distributors(db))
    print("rows updated:", len(pending))
    print("mode:", "APPLY (commit)" if apply else "DRY RUN (rollback)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--expect-db", required=True)
    parser.add_argument("--db", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from app.core.config import get_settings
    from app.db.sync_url import sqlalchemy_sync_engine_url

    sync = get_settings().database_url_sync
    if args.db:
        sync = _rewrite_dbname(sync, args.db)
    engine = create_engine(sqlalchemy_sync_engine_url(sync))
    with Session(engine) as db:
        code = run(db, apply=args.apply)
        if code != 0:
            db.rollback()
            return code
        if args.apply:
            db.commit()
        else:
            db.rollback()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
