"""Plan D bitemporal cutover orchestration (observation keys, backfill, gates, supersede)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_evidence_line_identity import (
    stable_line_identity_key_from_mapping,
)
from app.services.imports.shipment_evidence_observations import append_observations_for_job_lines

logger = logging.getLogger(__name__)

_BACKFILL_JOB_IDS = (153, 154)


@dataclass
class KeyMigrationReport:
    observations_scanned: int = 0
    observations_updated: int = 0
    prefix_before: dict[str, int] = field(default_factory=dict)
    prefix_after: dict[str, int] = field(default_factory=dict)


@dataclass
class GateReport:
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, *, ok: bool, detail: Any) -> None:
        self.checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            self.passed = False


def assert_database_is(db: Session, expected: str) -> None:
    actual = db.scalar(text("SELECT current_database()"))
    if actual != expected:
        raise RuntimeError(f"STOP: current_database()={actual!r}, expected {expected!r}")


def _key_prefix_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        text(
            """
            SELECT split_part(line_identity_key, ':', 1) AS prefix, count(*)::int
            FROM shipment_evidence_observation
            GROUP BY 1
            ORDER BY 1
            """
        )
    ).all()
    return {str(r[0]): int(r[1]) for r in rows}


def remigrate_observation_line_identity_keys(db: Session, *, chunk_size: int = 500) -> KeyMigrationReport:
    """Recompute ``line_identity_key`` on all observations (state-aware ship grain)."""
    report = KeyMigrationReport()
    report.prefix_before = _key_prefix_counts(db)

    obs_rows = db.execute(
        select(ShipmentEvidenceObservation).order_by(ShipmentEvidenceObservation.id)
    ).scalars().all()
    report.observations_scanned = len(obs_rows)

    line_ids = {int(o.evidence_line_id) for o in obs_rows if o.evidence_line_id is not None}
    line_by_id: dict[int, ShipmentEvidenceLine] = {}
    if line_ids:
        for line in db.execute(
            select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.id.in_(line_ids))
        ).scalars():
            line_by_id[int(line.id)] = line

    for obs in obs_rows:
        line = line_by_id.get(int(obs.evidence_line_id)) if obs.evidence_line_id else None
        values = {
            "line_state": obs.line_state,
            "operating_unit": obs.operating_unit or (line.operating_unit if line else None),
            "order_no": obs.order_no or (line.order_no if line else None),
            "order_line": obs.order_line or (line.order_line if line else None),
            "delivery_no": obs.delivery_no or (line.delivery_no if line else None),
            "invoice_line": obs.invoice_line or (line.invoice_line if line else None),
            "item_code": obs.item_code or (line.item_code if line else None),
            "purchase_order_id": obs.purchase_order_id
            if obs.purchase_order_id is not None
            else (line.purchase_order_id if line else None),
            "raw_source_row": obs.raw_source_row if isinstance(obs.raw_source_row, dict) else None,
        }
        new_key = stable_line_identity_key_from_mapping(values)
        if new_key != obs.line_identity_key:
            obs.line_identity_key = new_key
            report.observations_updated += 1
        if report.observations_updated and report.observations_updated % chunk_size == 0:
            db.flush()

    db.flush()
    report.prefix_after = _key_prefix_counts(db)
    return report


def backfill_observations_for_jobs(db: Session, job_ids: tuple[int, ...] = _BACKFILL_JOB_IDS) -> dict[int, int]:
    """Idempotent observation append for jobs missing from the observation store."""
    out: dict[int, int] = {}
    for jid in job_ids:
        job = db.get(ImportJob, int(jid))
        if job is None:
            out[int(jid)] = 0
            continue
        before = db.scalar(
            select(func.count())
            .select_from(ShipmentEvidenceObservation)
            .where(ShipmentEvidenceObservation.import_job_id == int(jid))
        )
        attempted = append_observations_for_job_lines(db, job)
        after = db.scalar(
            select(func.count())
            .select_from(ShipmentEvidenceObservation)
            .where(ShipmentEvidenceObservation.import_job_id == int(jid))
        )
        out[int(jid)] = int(after or 0) - int(before or 0)
        logger.info(
            "plan_d backfill job_id=%s before=%s after=%s attempted=%s",
            jid,
            before,
            after,
            attempted,
        )
    db.flush()
    return out


def count_current_view_rows(db: Session) -> int:
    return int(db.scalar(text("SELECT count(*) FROM shipment_evidence_current")) or 0)


def count_shipped_corpus_groups_in_evidence(db: Session) -> int:
    return int(
        db.scalar(
            text(
                """
                SELECT count(*) FROM (
                  SELECT 1
                  FROM shipment_evidence_line
                  WHERE lower(line_state) = 'shipped'
                    AND trim(coalesce(delivery_no, '')) <> ''
                    AND trim(coalesce(invoice_line, '')) <> ''
                    AND trim(coalesce(item_code, '')) <> ''
                    AND purchase_order_id IS NOT NULL
                    AND corpus_superseded_at IS NULL
                  GROUP BY
                    trim(delivery_no),
                    trim(item_code),
                    purchase_order_id,
                    trim(invoice_line)
                ) g
                """
            )
        )
        or 0
    )


def count_open_order_identity_keys_in_view(db: Session) -> int:
    return int(
        db.scalar(
            text(
                """
                SELECT count(*) FROM shipment_evidence_current
                WHERE line_identity_key LIKE 'order:%'
                """
            )
        )
        or 0
    )


def count_invoice_line_splits_collapsed(db: Session) -> int:
    """Groups sharing order-grain but distinct invoice lines that map to one view key."""
    return int(
        db.scalar(
            text(
                """
                WITH shipped AS (
                  SELECT
                    trim(coalesce(operating_unit, '')) AS ou,
                    trim(coalesce(delivery_no, '')) AS d,
                    trim(coalesce(item_code, '')) AS i,
                    purchase_order_id AS p,
                    trim(coalesce(invoice_line, '')) AS inv,
                    line_identity_key
                  FROM shipment_evidence_current
                  WHERE lower(line_state) = 'shipped'
                    AND line_identity_key LIKE 'ship:%'
                ),
                audit_groups AS (
                  SELECT d, i, p, inv, count(DISTINCT line_identity_key) AS view_keys
                  FROM shipped
                  GROUP BY d, i, p, inv
                )
                SELECT count(*) FROM audit_groups WHERE view_keys > 1
                """
            )
        )
        or 0
    )


def run_phase1_gate_assertions(db: Session) -> GateReport:
    """Clone/cip reconciliation gate after key migration + backfill."""
    report = GateReport(passed=True)

    view_count = count_current_view_rows(db)
    shipped_groups = count_shipped_corpus_groups_in_evidence(db)
    open_order_keys = count_open_order_identity_keys_in_view(db)
    collapsed = count_invoice_line_splits_collapsed(db)

    # View should cover canonical shipped corpus + open-order keys (approximate band).
    expected_min = shipped_groups + open_order_keys
    view_ok = (
        abs(view_count - (shipped_groups + open_order_keys)) <= 200
        and view_count >= shipped_groups
    )
    report.add(
        "view_row_reconciliation",
        ok=view_ok,
        detail={
            "view_count": view_count,
            "shipped_corpus_groups_active": shipped_groups,
            "open_order_keys_in_view": open_order_keys,
            "expected_min": expected_min,
        },
    )

    report.add(
        "invoice_line_splits_not_collapsed",
        ok=collapsed == 0,
        detail={"collapsed_audit_groups": collapsed},
    )

    total_obs = int(db.scalar(text("SELECT count(*) FROM shipment_evidence_observation")) or 0)
    total_ev = int(db.scalar(text("SELECT count(*) FROM shipment_evidence_line")) or 0)
    report.add(
        "observation_store_full_corpus",
        ok=total_obs >= total_ev,
        detail={"observations": total_obs, "evidence_lines": total_ev},
    )

    for jid in _BACKFILL_JOB_IDS:
        ev = int(
            db.scalar(
                text("SELECT count(*) FROM shipment_evidence_line WHERE import_job_id = :j"),
                {"j": jid},
            )
            or 0
        )
        obs = int(
            db.scalar(
                text("SELECT count(*) FROM shipment_evidence_observation WHERE import_job_id = :j"),
                {"j": jid},
            )
            or 0
        )
        report.add(
            f"job_{jid}_obs_matches_evidence",
            ok=ev == 0 or obs == ev,
            detail={"import_job_id": jid, "evidence": ev, "observations": obs},
        )

    return report


def open_order_shipped_fact_double_count_diagnostic(db: Session) -> dict[str, Any]:
    """Read-only: open-order facts whose order grain matches a shipped fact."""
    row = db.execute(
        text(
            """
            WITH open_f AS (
              SELECT id, operating_unit, order_no, item_code, quantity, fact_upsert_key
              FROM fact_inbound_shipment
              WHERE lower(line_state) = 'open_order'
                AND trim(coalesce(order_no, '')) <> ''
                AND trim(coalesce(item_code, '')) <> ''
            ),
            ship_f AS (
              SELECT id, operating_unit, order_no, item_code, quantity, fact_upsert_key
              FROM fact_inbound_shipment
              WHERE lower(line_state) = 'shipped'
                AND trim(coalesce(order_no, '')) <> ''
                AND trim(coalesce(item_code, '')) <> ''
            ),
            matched AS (
              SELECT o.id AS open_fact_id, s.id AS shipped_fact_id,
                     o.quantity AS open_qty, s.quantity AS shipped_qty
              FROM open_f o
              JOIN ship_f s
                ON lower(trim(coalesce(o.operating_unit, ''))) = lower(trim(coalesce(s.operating_unit, '')))
               AND lower(trim(o.order_no)) = lower(trim(s.order_no))
               AND lower(trim(o.item_code)) = lower(trim(s.item_code))
            )
            SELECT count(*)::int AS match_rows,
                   coalesce(sum(open_qty), 0)::float AS open_qty_sum,
                   coalesce(sum(shipped_qty), 0)::float AS shipped_qty_sum
            FROM matched
            """
        )
    ).one()
    return {
        "matching_open_shipped_fact_pairs": int(row[0]),
        "open_qty_sum": float(row[1]),
        "shipped_qty_sum": float(row[2]),
        "note": "Remediation deferred — diagnostic only",
    }


def soft_supersede_legacy_duplicate_evidence(db: Session, *, dry_run: bool = False) -> dict[str, Any]:
    """Mark non-canonical legacy evidence rows superseded (no deletes)."""
    now = datetime.now(timezone.utc)
    rows = db.execute(
        text(
            """
            WITH canonical AS (
              SELECT DISTINCT ON (line_identity_key)
                line_identity_key,
                evidence_line_id
              FROM shipment_evidence_current
              WHERE evidence_line_id IS NOT NULL
              ORDER BY line_identity_key, valid_from DESC NULLS LAST, id DESC
            ),
            dupes AS (
              SELECT sel.id AS evidence_id, c.evidence_line_id AS canonical_id
              FROM shipment_evidence_line sel
              JOIN canonical c ON c.evidence_line_id IS NOT NULL
              JOIN shipment_evidence_observation o ON o.evidence_line_id = sel.id
              WHERE sel.id <> c.evidence_line_id
                AND o.line_identity_key = c.line_identity_key
                AND sel.corpus_superseded_at IS NULL
            )
            SELECT count(*)::int AS rows_to_supersede,
                   count(DISTINCT canonical_id)::int AS canonical_groups
            FROM dupes
            """
        )
    ).one()

    if not dry_run and int(rows[0]) > 0:
        db.execute(
            text(
                """
                WITH canonical AS (
                  SELECT DISTINCT ON (line_identity_key)
                    line_identity_key,
                    evidence_line_id
                  FROM shipment_evidence_current
                  WHERE evidence_line_id IS NOT NULL
                  ORDER BY line_identity_key, valid_from DESC NULLS LAST, id DESC
                )
                UPDATE shipment_evidence_line sel
                SET corpus_superseded_at = :now
                FROM shipment_evidence_observation o, canonical c
                WHERE o.evidence_line_id = sel.id
                  AND o.line_identity_key = c.line_identity_key
                  AND sel.id <> c.evidence_line_id
                  AND sel.corpus_superseded_at IS NULL
                """
            ),
            {"now": now},
        )
        db.flush()

    return {
        "rows_to_supersede": int(rows[0]),
        "canonical_groups_touched": int(rows[1]),
        "dry_run": dry_run,
    }
