"""Batch (distributor, month) scopes for unresolved product tokens from DSI staging evidence."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.orm import Session

EvidenceScope = tuple[int, str]  # (resolved_distributor_id, YYYY-MM)


def load_product_staging_evidence_scopes(session: Session, job_id: int) -> dict[str, list[EvidenceScope]]:
    """Map normalized product token → distinct (distributor_id, evidence month) from staging rows.

    Used at plan-compute time when validate-time corroboration context is incomplete (e.g. job #43).
    """
    rows = session.execute(
        text(
            """
            SELECT lower(btrim(raw_product_token)) AS nk,
                   resolved_distributor_id,
                   to_char(
                       date_trunc('month', COALESCE(transaction_date, snapshot_date)),
                       'YYYY-MM'
                   ) AS ev_month
            FROM import_distributor_si_staging_line
            WHERE import_job_id = :jid
              AND raw_product_token IS NOT NULL
              AND btrim(raw_product_token) <> ''
              AND resolved_distributor_id IS NOT NULL
              AND COALESCE(transaction_date, snapshot_date) IS NOT NULL
              AND resolved_product_id IS NULL
            GROUP BY 1, 2, 3
            """
        ),
        {"jid": int(job_id)},
    ).fetchall()
    out: dict[str, list[EvidenceScope]] = defaultdict(list)
    seen: dict[str, set[EvidenceScope]] = defaultdict(set)
    for nk, dist_id, ev_month in rows:
        if not nk or dist_id is None or not ev_month:
            continue
        key = str(nk)
        scope: EvidenceScope = (int(dist_id), str(ev_month)[:7])
        if scope in seen[key]:
            continue
        seen[key].add(scope)
        out[key].append(scope)
    return dict(out)
