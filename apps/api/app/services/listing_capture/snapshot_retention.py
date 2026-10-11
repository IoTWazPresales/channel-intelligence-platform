"""Raw page snapshot retention (Warren, 2026-10-08, N-0101; all retailers).

Clears ``listing_observation.raw_snapshot`` on observations fetched more than 90 days
ago. Only the payload goes: the observation row, its extracted price, availability,
promo badge and parse flags are kept forever. Rows are never deleted.

Bounded: batches of ``batch_size`` rows in id order (keyset, so no batch rescans the
ones before it), committed one by one, and no new batch starts after the time limit.
A cleared row gets ``parse_flags.snapshot_cleared`` so re-parse and readers know why
there is no payload. Postgres frees the space for reuse after (auto)vacuum; the table
file itself does not shrink without a VACUUM FULL.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

SNAPSHOT_RETENTION_DAYS = 90
SNAPSHOT_RETENTION_BATCH_SIZE = 5000
SNAPSHOT_RETENTION_TIME_LIMIT_SECONDS = 240.0

_SELECT_BATCH = text(
    """
    SELECT id, octet_length(raw_snapshot) AS bytes
    FROM listing_observation
    WHERE id > :after_id
      AND fetched_at < :cutoff
      AND raw_snapshot IS NOT NULL
    ORDER BY id
    LIMIT :batch_size
    """
)

_CLEAR_BATCH = text(
    """
    UPDATE listing_observation
    SET raw_snapshot = NULL,
        -- An ORM None is stored as JSON null, which COALESCE does not catch and which
        -- || would turn into an array: merge into an object in every case, losslessly.
        parse_flags = (
            CASE
                WHEN jsonb_typeof(parse_flags) = 'object' THEN parse_flags
                WHEN parse_flags IS NULL OR jsonb_typeof(parse_flags) = 'null' THEN '{}'::jsonb
                ELSE jsonb_build_object('previous_parse_flags', parse_flags)
            END
        )
            || jsonb_build_object(
                'snapshot_cleared',
                jsonb_build_object(
                    'reason', 'retention',
                    'retention_days', CAST(:days AS integer),
                    'cleared_at', CAST(:cleared_at AS text)
                )
            )
    WHERE id = ANY(:ids)
      AND raw_snapshot IS NOT NULL
    """
)


def clear_expired_snapshots(
    session: Session,
    *,
    now: datetime | None = None,
    retention_days: int = SNAPSHOT_RETENTION_DAYS,
    batch_size: int = SNAPSHOT_RETENTION_BATCH_SIZE,
    time_limit_seconds: float = SNAPSHOT_RETENTION_TIME_LIMIT_SECONDS,
    clock: Callable[[], float] | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """Null ``raw_snapshot`` on observations older than ``retention_days``. Never deletes rows.

    ``commit=False`` leaves the transaction to the caller (tests run inside one that is
    rolled back).
    """
    clock = clock or time.monotonic
    run_now = now or datetime.now(timezone.utc)
    cutoff = run_now - timedelta(days=int(retention_days))
    started = clock()
    after_id = 0
    batches = 0
    cleared = 0
    bytes_cleared = 0
    stopped_reason: str | None = None

    while True:
        if clock() - started >= float(time_limit_seconds):
            stopped_reason = "time_limit"
            break
        rows = session.execute(
            _SELECT_BATCH,
            {"after_id": after_id, "cutoff": cutoff, "batch_size": int(batch_size)},
        ).all()
        if not rows:
            break
        ids = [int(r.id) for r in rows]
        res = session.execute(
            _CLEAR_BATCH,
            {"ids": ids, "days": int(retention_days), "cleared_at": run_now.isoformat()},
        )
        cleared += int(res.rowcount or 0)
        bytes_cleared += sum(int(r.bytes or 0) for r in rows)
        batches += 1
        after_id = ids[-1]
        if commit:
            session.commit()
        if len(ids) < int(batch_size):
            break

    result = {
        "cutoff": cutoff.isoformat(),
        "retention_days": int(retention_days),
        "batches": batches,
        "snapshots_cleared": cleared,
        "bytes_cleared": bytes_cleared,
        "rows_deleted": 0,
        "stopped_reason": stopped_reason,
        "duration_seconds": round(clock() - started, 3),
    }
    log.info("listing capture snapshot retention: %s", result)
    return result
