"""Per-distributor receipt disambiguation for product-ambiguous DSI rows (final tier).

Runs **after** standard ``_resolve_product`` when ``ambiguous_eligible`` remains. Uses
``shipment_evidence_line`` receipt sets keyed by canonical distributor + sales model name.
Does not alter earlier resolution tiers or month-grain shipment corroboration.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.imports.distributor_sales_inventory import _norm_key, _product_token_key
from app.services.imports.provisional_entity_identity import canonical_provisional_entity_name_key

REASON_SINGLE = "distributor_receipt_single"
REASON_OVERLAP_REFINED = "distributor_receipt_overlap_refined"

STATUS_NO_RECEIPT_EVIDENCE = "no_receipt_evidence"
STATUS_AMBIGUOUS_OVERLAP = "ambiguous_overlap"
STATUS_NO_ELIGIBLE_RECEIPT_INTERSECTION = "no_eligible_receipt_intersection"
STATUS_RESOLVED_SINGLE = "resolved_single"
STATUS_RESOLVED_OVERLAP_REFINED = "resolved_overlap_refined"


@dataclass(frozen=True, slots=True)
class ReceiptLineEvidence:
    product_id: int
    ship_date: date
    pod_date: date | None
    quantity: float


@dataclass(frozen=True, slots=True)
class ReceiptDisambiguationResult:
    product_id: int | None
    resolve_reason: str | None
    evidence: dict[str, Any] | None = None

    @property
    def tier(self) -> str | None:
        """Legacy preview-script label derived from resolve_reason."""
        if self.resolve_reason == REASON_SINGLE:
            return "T1"
        if self.resolve_reason == REASON_OVERLAP_REFINED:
            return "T2"
        if self.evidence and self.evidence.get("status") == STATUS_NO_RECEIPT_EVIDENCE:
            return "T4"
        if self.product_id is None:
            return "T4"
        return None

    @property
    def provenance(self) -> dict[str, Any]:
        if not self.evidence:
            return {}
        return {"receipt_disambiguation": self.evidence}


class DistributorReceiptProductIndex:
    """Shipment receipt index: canonical distributor × sales_model → per-product line evidence."""

    __slots__ = ("_dist", "_line_counts")

    def __init__(self) -> None:
        self._dist: dict[tuple[str, str], dict[int, list[ReceiptLineEvidence]]] = defaultdict(
            lambda: defaultdict(list)
        )
        self._line_counts: dict[tuple[str, str], int] = defaultdict(int)

    @classmethod
    def load(cls, db: Session, dist_id_to_canonical: dict[int, str]) -> "DistributorReceiptProductIndex":
        """Load receipt evidence for disambiguation (shipped lines with qty>1; no demo sales models)."""
        idx = cls()
        rows = db.execute(
            text(
                """
                SELECT
                    distributor_id,
                    product_id,
                    lower(btrim(coalesce(sales_model_name, ''))) AS sm_key,
                    COALESCE(ship_confirm_date, schedule_ship_date, promise_date)::date AS ship_dt,
                    COALESCE(pod_date, est_pod_date)::date AS pod_dt,
                    COALESCE(quantity, 0)::numeric AS qty
                FROM shipment_evidence_line
                WHERE product_resolution_status IN ('resolved', 'resolved_unique')
                  AND product_id IS NOT NULL
                  AND distributor_id IS NOT NULL
                  AND line_state = 'shipped'
                  AND COALESCE(quantity, 0) > 1
                  AND btrim(coalesce(sales_model_name, '')) <> ''
                  AND lower(btrim(coalesce(sales_model_name, ''))) NOT LIKE '%-demo'
                  AND lower(btrim(coalesce(sales_model_name, ''))) NOT LIKE '%-dem'
                  AND COALESCE(ship_confirm_date, schedule_ship_date, promise_date) IS NOT NULL
                """
            )
        ).fetchall()
        for dist_id, pid, sm_key, ship_dt, pod_dt, qty in rows:
            if not sm_key or pid is None or ship_dt is None:
                continue
            sm = str(sm_key).strip()
            p = int(pid)
            sd = ship_dt if isinstance(ship_dt, date) else ship_dt
            pd = pod_dt if isinstance(pod_dt, date) or pod_dt is None else pod_dt
            q = float(qty or 0)
            canon = dist_id_to_canonical.get(int(dist_id)) if dist_id is not None else ""
            if not canon:
                continue
            idx._dist[(canon, sm)][p].append(
                ReceiptLineEvidence(product_id=p, ship_date=sd, pod_date=pd, quantity=q)
            )
            idx._line_counts[(canon, sm)] += 1
        return idx

    def receipt_product_ids(self, canonical_distributor_key: str, sales_model_key: str) -> set[int]:
        bucket = self._dist.get((canonical_distributor_key, sales_model_key), {})
        return {int(k) for k in bucket if int(k) > 0}

    def line_count(self, *, canonical_distributor_key: str, sales_model_key: str) -> int:
        return int(self._line_counts.get((canonical_distributor_key, sales_model_key), 0))

    def lines_for_scope(
        self, canonical_distributor_key: str, sales_model_key: str
    ) -> dict[int, list[ReceiptLineEvidence]]:
        return dict(self._dist.get((canonical_distributor_key, sales_model_key), {}))


def _sales_model_key_from_token(raw: str | None) -> str:
    keys: list[str] = []
    full = _product_token_key(raw)
    if full:
        keys.append(full)
    nk = _norm_key(raw)
    if nk and nk not in keys:
        keys.append(nk)
    return keys[0] if keys else ""


def _intersect_eligible(eligible_ids: list[int], receipt_ids: set[int]) -> set[int]:
    elig = {int(x) for x in eligible_ids if int(x) > 0}
    return elig & receipt_ids


def _window_covers_tx(ship_dt: date, pod_dt: date | None, tx_date: date) -> bool:
    if tx_date < ship_dt:
        return False
    if pod_dt is not None and tx_date > pod_dt:
        return False
    return True


def _cumulative_shipped_qty(lines: list[ReceiptLineEvidence], tx_date: date) -> float:
    total = 0.0
    for ln in lines:
        if ln.ship_date <= tx_date:
            total += float(ln.quantity or 0)
    return total


def _refine_overlap_candidates(
    survivors: set[int],
    pid_lines: dict[int, list[ReceiptLineEvidence]],
    *,
    evidence_date: date,
    sell_out_qty: float | None,
) -> set[int]:
    """Keep SKUs whose shipment window covers tx_date and cumulative qty covers sell-out."""
    refined: set[int] = set()
    need_qty = sell_out_qty is not None and float(sell_out_qty) > 0
    for pid in sorted(survivors):
        lines = pid_lines.get(int(pid)) or []
        if not lines:
            continue
        window_ok = any(_window_covers_tx(ln.ship_date, ln.pod_date, evidence_date) for ln in lines)
        if not window_ok:
            continue
        if need_qty:
            if _cumulative_shipped_qty(lines, evidence_date) < float(sell_out_qty):
                continue
        refined.add(int(pid))
    return refined


def _serialize_receipt_lines(pid_lines: dict[int, list[ReceiptLineEvidence]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pid in sorted(pid_lines):
        for ln in sorted(pid_lines[pid], key=lambda x: (x.ship_date, x.pod_date or date.max)):
            out.append(
                {
                    "product_id": int(pid),
                    "ship_date": ln.ship_date.isoformat(),
                    "pod_date": ln.pod_date.isoformat() if ln.pod_date else None,
                    "quantity": float(ln.quantity or 0),
                }
            )
    return out


def _base_evidence(
    *,
    status: str,
    canon: str,
    sm_key: str,
    receipt_index: DistributorReceiptProductIndex,
    receipt_product_ids: set[int],
    pid_lines: dict[int, list[ReceiptLineEvidence]],
    eligible_product_ids: list[int],
    overlap_survivors: list[int] | None = None,
    resolve_reason: str | None = None,
    resolved_product_id: int | None = None,
) -> dict[str, Any]:
    ev: dict[str, Any] = {
        "status": status,
        "canonical_distributor_key": canon or None,
        "sales_model_key": sm_key,
        "receipt_line_count": receipt_index.line_count(
            canonical_distributor_key=canon, sales_model_key=sm_key
        ),
        "receipt_product_ids": sorted(int(x) for x in receipt_product_ids),
        "eligible_product_ids": sorted(int(x) for x in eligible_product_ids if int(x) > 0),
        "receipt_lines": _serialize_receipt_lines(pid_lines),
    }
    if overlap_survivors is not None:
        ev["overlap_refine_survivors"] = overlap_survivors
    if resolve_reason:
        ev["resolve_reason"] = resolve_reason
    if resolved_product_id is not None:
        ev["resolved_product_id"] = int(resolved_product_id)
    return ev


def try_receipt_disambiguate_product(
    receipt_index: DistributorReceiptProductIndex | None,
    *,
    distributor_id: int | None,
    dist_id_to_canonical: dict[int, str],
    raw_product_token: str | None,
    eligible_product_ids: list[int],
    evidence_date: date | None,
    ambiguous_eligible: dict[str, Any] | None,
    sell_out_qty: float | None = None,
) -> ReceiptDisambiguationResult:
    """Final receipt tier. Never returns a pick outside ``eligible_product_ids``."""
    if receipt_index is None or not eligible_product_ids or ambiguous_eligible is None:
        return ReceiptDisambiguationResult(None, None)
    if distributor_id is None or evidence_date is None:
        return ReceiptDisambiguationResult(None, None)

    sm_key = _sales_model_key_from_token(raw_product_token)
    if not sm_key:
        return ReceiptDisambiguationResult(None, None)

    canon = dist_id_to_canonical.get(int(distributor_id)) or canonical_provisional_entity_name_key(
        str(distributor_id)
    )
    if not canon:
        return ReceiptDisambiguationResult(None, None)

    dist_receipt = receipt_index.receipt_product_ids(canon, sm_key)
    pid_lines = receipt_index.lines_for_scope(canon, sm_key)

    if not dist_receipt:
        return ReceiptDisambiguationResult(
            None,
            None,
            evidence=_base_evidence(
                status=STATUS_NO_RECEIPT_EVIDENCE,
                canon=canon,
                sm_key=sm_key,
                receipt_index=receipt_index,
                receipt_product_ids=set(),
                pid_lines={},
                eligible_product_ids=eligible_product_ids,
            ),
        )

    inter = _intersect_eligible(eligible_product_ids, dist_receipt)
    if len(inter) == 1:
        pick = min(inter)
        return ReceiptDisambiguationResult(
            pick,
            REASON_SINGLE,
            evidence=_base_evidence(
                status=STATUS_RESOLVED_SINGLE,
                canon=canon,
                sm_key=sm_key,
                receipt_index=receipt_index,
                receipt_product_ids=dist_receipt,
                pid_lines={k: v for k, v in pid_lines.items() if k in inter},
                eligible_product_ids=eligible_product_ids,
                resolve_reason=REASON_SINGLE,
                resolved_product_id=pick,
            ),
        )

    if len(inter) > 1:
        refined = _refine_overlap_candidates(
            inter,
            {k: v for k, v in pid_lines.items() if k in inter},
            evidence_date=evidence_date,
            sell_out_qty=sell_out_qty,
        )
        survivors = sorted(int(x) for x in refined)
        if len(refined) == 1:
            pick = survivors[0]
            return ReceiptDisambiguationResult(
                pick,
                REASON_OVERLAP_REFINED,
                evidence=_base_evidence(
                    status=STATUS_RESOLVED_OVERLAP_REFINED,
                    canon=canon,
                    sm_key=sm_key,
                    receipt_index=receipt_index,
                    receipt_product_ids=dist_receipt,
                    pid_lines={k: v for k, v in pid_lines.items() if k in inter},
                    eligible_product_ids=eligible_product_ids,
                    overlap_survivors=survivors,
                    resolve_reason=REASON_OVERLAP_REFINED,
                    resolved_product_id=pick,
                ),
            )
        return ReceiptDisambiguationResult(
            None,
            None,
            evidence=_base_evidence(
                status=STATUS_AMBIGUOUS_OVERLAP,
                canon=canon,
                sm_key=sm_key,
                receipt_index=receipt_index,
                receipt_product_ids=dist_receipt,
                pid_lines={k: v for k, v in pid_lines.items() if k in inter},
                eligible_product_ids=eligible_product_ids,
                overlap_survivors=survivors,
            ),
        )

    status = (
        STATUS_NO_RECEIPT_EVIDENCE if not dist_receipt else STATUS_NO_ELIGIBLE_RECEIPT_INTERSECTION
    )
    return ReceiptDisambiguationResult(
        None,
        None,
        evidence=_base_evidence(
            status=status,
            canon=canon,
            sm_key=sm_key,
            receipt_index=receipt_index,
            receipt_product_ids=dist_receipt,
            pid_lines=pid_lines,
            eligible_product_ids=eligible_product_ids,
        ),
    )


def preview_receipt_disambiguation_for_staging_rows(
    db: Session,
    *,
    import_job_id: int,
    receipt_index: DistributorReceiptProductIndex,
    dist_id_to_canonical: dict[int, str],
) -> dict[str, Any]:
    """Dry-run tier counts for unresolved staging rows on a DSI job."""
    rows = db.execute(
        text(
            """
            SELECT id, raw_product_token, resolved_distributor_id, transaction_date, snapshot_date,
                   quantity_sold
            FROM import_distributor_si_staging_line
            WHERE import_job_id = :jid
              AND resolved_product_id IS NULL
              AND btrim(coalesce(raw_product_token, '')) <> ''
            """
        ),
        {"jid": int(import_job_id)},
    ).fetchall()

    from app.services.imports.distributor_sales_inventory import _load_product_resolution_index, _resolve_product

    prod_idx = _load_product_resolution_index(db)
    tier_counts: dict[str, int] = defaultdict(int)
    tier_counts["candidate_rows"] = 0
    tier_counts["still_ambiguous"] = 0

    for _id, raw, dist_id, tx, snap, qty_sold in rows:
        ev_date = tx or snap
        if ev_date is None:
            tier_counts["no_evidence_date"] += 1
            continue
        _rpid, perr, _tag, pev = _resolve_product(
            raw,
            prod_idx,
            ev_date if isinstance(ev_date, date) else None,
            relax_inactive_dim_product_for_historical_dsi=True,
        )
        if pev is None or not pev.ambiguous_eligible:
            continue
        tier_counts["candidate_rows"] += 1
        elig = [int(x) for x in (pev.ambiguous_eligible.get("product_ids") or []) if int(x) > 0]
        sell_qty = abs(float(qty_sold)) if qty_sold is not None and float(qty_sold) > 0 else None
        res = try_receipt_disambiguate_product(
            receipt_index,
            distributor_id=int(dist_id) if dist_id is not None else None,
            dist_id_to_canonical=dist_id_to_canonical,
            raw_product_token=str(raw) if raw else None,
            eligible_product_ids=elig,
            evidence_date=ev_date if isinstance(ev_date, date) else None,
            ambiguous_eligible=pev.ambiguous_eligible,
            sell_out_qty=sell_qty,
        )
        if res.product_id is not None and res.resolve_reason:
            tier_counts[res.resolve_reason] += 1
            if res.tier:
                tier_counts[res.tier] += 1
        else:
            tier_counts["T4"] += 1
            tier_counts["still_ambiguous"] += 1

    return dict(tier_counts)


_MISASSIGN_CANDIDATE_SQL = """
            SELECT s.id,
                   s.raw_product_token,
                   s.resolved_product_id,
                   s.resolved_distributor_id,
                   s.transaction_date,
                   s.snapshot_date,
                   s.quantity_sold
            FROM import_distributor_si_staging_line s
            WHERE s.import_job_id = :jid
              AND s.resolved_product_id IS NOT NULL
              AND s.resolved_distributor_id IS NOT NULL
              AND btrim(coalesce(s.raw_product_token, '')) <> ''
              AND NOT EXISTS (
                    SELECT 1
                    FROM shipment_evidence_line se
                    WHERE se.product_id = s.resolved_product_id
                      AND se.distributor_id = s.resolved_distributor_id
                      AND lower(btrim(coalesce(se.sales_model_name, '')))
                          = lower(btrim(coalesce(s.raw_product_token, '')))
                  )
              AND EXISTS (
                    SELECT 1
                    FROM shipment_evidence_line se2
                    WHERE se2.product_id = s.resolved_product_id
                      AND se2.distributor_id IS NOT NULL
                      AND se2.distributor_id <> s.resolved_distributor_id
                      AND lower(btrim(coalesce(se2.sales_model_name, '')))
                          = lower(btrim(coalesce(s.raw_product_token, '')))
                  )
            """


def _eligible_ids_for_receipt_reresolve(
    raw: str | None,
    prod_idx: Any,
    ev_date: date | None,
    *,
    historical_relaxed: bool,
) -> tuple[list[int], dict[str, Any] | None]:
    """Eligible PM ids for receipt re-resolve without shipment corroboration picks."""
    from app.services.imports.distributor_sales_inventory import _resolve_product

    _rpid, _perr, _tag, pev = _resolve_product(
        raw,
        prod_idx,
        ev_date,
        relax_inactive_dim_product_for_historical_dsi=historical_relaxed,
        db=None,
    )
    if pev and pev.ambiguous_eligible:
        elig = [int(x) for x in (pev.ambiguous_eligible.get("product_ids") or []) if int(x) > 0]
        return elig, pev.ambiguous_eligible
    return [], None


def _propose_misassign_correction(
    *,
    raw: str | None,
    cur_pid: int,
    dist_id: int,
    ev_date: date,
    prod_idx: Any,
    receipt_index: DistributorReceiptProductIndex,
    dist_id_to_canonical: dict[int, str],
    historical_relaxed: bool,
    sell_out_qty: float | None = None,
) -> ReceiptDisambiguationResult | None:
    elig, amb = _eligible_ids_for_receipt_reresolve(
        raw, prod_idx, ev_date, historical_relaxed=historical_relaxed
    )
    if not elig:
        return None
    res = try_receipt_disambiguate_product(
        receipt_index,
        distributor_id=dist_id,
        dist_id_to_canonical=dist_id_to_canonical,
        raw_product_token=str(raw) if raw else None,
        eligible_product_ids=elig,
        evidence_date=ev_date,
        ambiguous_eligible=amb,
        sell_out_qty=sell_out_qty,
    )
    if res.product_id is not None and int(res.product_id) != int(cur_pid):
        return res
    return None


def preview_cross_distributor_misassignments(
    db: Session,
    *,
    import_job_id: int,
    receipt_index: DistributorReceiptProductIndex,
    dist_id_to_canonical: dict[int, str],
    sample_limit: int = 3,
) -> dict[str, Any]:
    """Dry-run Unit 4: rows resolved to a SKU with no receipt for their distributor."""
    from app.services.imports.distributor_sales_inventory import (
        _load_product_resolution_index,
        dsi_historical_product_eligibility_relaxed_from_import_job,
    )
    from app.models.ingestion import ImportJob

    job = db.get(ImportJob, int(import_job_id))
    historical_relaxed = dsi_historical_product_eligibility_relaxed_from_import_job(job) if job else True

    rows = db.execute(text(_MISASSIGN_CANDIDATE_SQL), {"jid": int(import_job_id)}).fetchall()

    prod_idx = _load_product_resolution_index(db)
    counts: dict[str, int] = defaultdict(int)
    counts["misassign_candidate_rows"] = len(rows)
    scope_keys: set[tuple[int, str, int]] = set()
    samples: list[dict[str, Any]] = []

    for row_id, raw, cur_pid, dist_id, tx, snap, qty_sold in rows:
        cur_pid = int(cur_pid)
        dist_id = int(dist_id)
        sm = str(raw or "").strip()
        scope_keys.add((dist_id, _sales_model_key_from_token(raw), cur_pid))
        ev_date = tx or snap
        if ev_date is None:
            counts["no_evidence_date"] += 1
            continue
        if not isinstance(ev_date, date):
            ev_date = ev_date
        sell_qty = abs(float(qty_sold)) if qty_sold is not None and float(qty_sold) > 0 else None

        res = _propose_misassign_correction(
            raw=str(raw) if raw else None,
            cur_pid=cur_pid,
            dist_id=dist_id,
            ev_date=ev_date,
            prod_idx=prod_idx,
            receipt_index=receipt_index,
            dist_id_to_canonical=dist_id_to_canonical,
            historical_relaxed=historical_relaxed,
            sell_out_qty=sell_qty,
        )
        if res is not None and res.product_id is not None and res.resolve_reason:
            counts["would_reassign"] += 1
            counts[f"reassign_{res.resolve_reason}"] += 1
            if len(samples) < sample_limit:
                samples.append(
                    {
                        "staging_line_id": int(row_id),
                        "raw_product_token": sm,
                        "resolved_distributor_id": dist_id,
                        "current_product_id": cur_pid,
                        "proposed_product_id": int(res.product_id),
                        "resolve_reason": res.resolve_reason,
                        "evidence_date": str(ev_date),
                        "provenance": res.provenance,
                    }
                )
        else:
            elig, _amb = _eligible_ids_for_receipt_reresolve(
                str(raw) if raw else None,
                prod_idx,
                ev_date,
                historical_relaxed=historical_relaxed,
            )
            if elig:
                counts["still_unresolved"] += 1
            else:
                counts["not_ambiguous_eligible"] += 1

    counts["distinct_scopes"] = len(scope_keys)
    return {"counts": dict(counts), "sample_traces": samples}


def apply_cross_distributor_misassignment_corrections(
    db: Session,
    *,
    import_job_id: int,
    receipt_index: DistributorReceiptProductIndex,
    dist_id_to_canonical: dict[int, str],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Governed apply: re-resolve misassigned rows via receipt tiers (not raw DML)."""
    from app.models.import_distributor_si import ImportDistributorSiStagingLine
    from app.models.ingestion import ImportJob
    from app.services.imports.distributor_sales_inventory import (
        _load_product_resolution_index,
        dsi_historical_product_eligibility_relaxed_from_import_job,
    )

    job = db.get(ImportJob, int(import_job_id))
    if job is None:
        raise ValueError(f"import job {import_job_id} not found")
    historical_relaxed = dsi_historical_product_eligibility_relaxed_from_import_job(job)

    rows = db.execute(text(_MISASSIGN_CANDIDATE_SQL), {"jid": int(import_job_id)}).fetchall()
    prod_idx = _load_product_resolution_index(db)
    counts: dict[str, int] = defaultdict(int)
    counts["misassign_candidate_rows"] = len(rows)
    corrections: list[dict[str, Any]] = []

    for row_id, raw, cur_pid, dist_id, tx, snap, qty_sold in rows:
        cur_pid = int(cur_pid)
        dist_id = int(dist_id)
        ev_date = tx or snap
        if ev_date is None:
            counts["no_evidence_date"] += 1
            continue
        if not isinstance(ev_date, date):
            ev_date = ev_date
        sell_qty = abs(float(qty_sold)) if qty_sold is not None and float(qty_sold) > 0 else None

        res = _propose_misassign_correction(
            raw=str(raw) if raw else None,
            cur_pid=cur_pid,
            dist_id=dist_id,
            ev_date=ev_date,
            prod_idx=prod_idx,
            receipt_index=receipt_index,
            dist_id_to_canonical=dist_id_to_canonical,
            historical_relaxed=historical_relaxed,
            sell_out_qty=sell_qty,
        )
        if res is None or res.product_id is None or not res.resolve_reason:
            counts["skipped"] += 1
            continue

        counts["applied"] += 1
        counts[f"applied_{res.resolve_reason}"] += 1
        tag = f"product_{res.resolve_reason}_misassign_correction"
        corrections.append(
            {
                "staging_line_id": int(row_id),
                "from_product_id": cur_pid,
                "to_product_id": int(res.product_id),
                "resolve_reason": res.resolve_reason,
                "provenance": res.provenance,
            }
        )
        if dry_run:
            continue

        line = db.get(ImportDistributorSiStagingLine, int(row_id))
        if line is None:
            counts["missing_line"] += 1
            continue
        diag = list(line.diagnostic_codes or [])
        if tag not in diag:
            diag.append(tag)
        line.resolved_product_id = int(res.product_id)
        line.diagnostic_codes = diag
        db.add(line)

    if not dry_run and counts["applied"] > 0:
        db.commit()

    return {"dry_run": dry_run, "counts": dict(counts), "corrections": corrections[:50]}
