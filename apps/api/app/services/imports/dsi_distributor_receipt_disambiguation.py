"""Distributor-receipt product disambiguation for ambiguous DSI sales-model tokens (Unit 3).

Runs after standard ``_resolve_product`` when ``ambiguous_eligible`` remains. Uses unwindowed
``shipment_evidence_line`` receipt-sets keyed by canonical distributor + sales model name.
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


@dataclass(frozen=True, slots=True)
class ReceiptDisambiguationResult:
    product_id: int | None
    tier: str | None
    provenance: dict[str, Any] = field(default_factory=dict)


class DistributorReceiptProductIndex:
    """Unwindowed shipment receipt index: canonical distributor × sales_model → product evidence."""

    __slots__ = ("_dist", "_global", "_line_counts")

    def __init__(self) -> None:
        self._dist: dict[tuple[str, str], dict[int, list[date]]] = defaultdict(lambda: defaultdict(list))
        self._global: dict[str, dict[int, list[date]]] = defaultdict(lambda: defaultdict(list))
        self._line_counts: dict[tuple[str, str] | tuple[str], int] = defaultdict(int)

    @classmethod
    def load(cls, db: Session, dist_id_to_canonical: dict[int, str]) -> "DistributorReceiptProductIndex":
        idx = cls()
        rows = db.execute(
            text(
                """
                SELECT
                    distributor_id,
                    product_id,
                    lower(btrim(coalesce(sales_model_name, ''))) AS sm_key,
                    COALESCE(ship_confirm_date, schedule_ship_date, promise_date)::date AS ship_dt
                FROM shipment_evidence_line
                WHERE product_resolution_status IN ('resolved', 'resolved_unique')
                  AND product_id IS NOT NULL
                  AND btrim(coalesce(sales_model_name, '')) <> ''
                  AND COALESCE(ship_confirm_date, schedule_ship_date, promise_date) IS NOT NULL
                """
            )
        ).fetchall()
        for dist_id, pid, sm_key, ship_dt in rows:
            if not sm_key or pid is None or ship_dt is None:
                continue
            sm = str(sm_key).strip()
            p = int(pid)
            sd = ship_dt if isinstance(ship_dt, date) else ship_dt
            canon = dist_id_to_canonical.get(int(dist_id)) if dist_id is not None else ""
            if canon:
                idx._dist[(canon, sm)][p].append(sd)
                idx._line_counts[(canon, sm)] += 1
            idx._global[sm][p].append(sd)
            idx._line_counts[(sm,)] += 1
        return idx

    def receipt_product_ids(self, canonical_distributor_key: str, sales_model_key: str) -> set[int]:
        bucket = self._dist.get((canonical_distributor_key, sales_model_key), {})
        return {int(k) for k in bucket if int(k) > 0}

    def global_receipt_product_ids(self, sales_model_key: str) -> set[int]:
        bucket = self._global.get(sales_model_key, {})
        return {int(k) for k in bucket if int(k) > 0}

    def line_count(self, *, canonical_distributor_key: str | None, sales_model_key: str) -> int:
        if canonical_distributor_key:
            return int(self._line_counts.get((canonical_distributor_key, sales_model_key), 0))
        return int(self._line_counts.get((sales_model_key,), 0))

    def ship_dates_for_scope(
        self, canonical_distributor_key: str, sales_model_key: str
    ) -> dict[int, list[date]]:
        return dict(self._dist.get((canonical_distributor_key, sales_model_key), {}))


def _sales_model_key_from_token(raw: str | None) -> str:
    keys = []
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


def _windows_strictly_separated(pid_dates: dict[int, list[date]]) -> bool:
    """True when each product's shipments end strictly before the next product's first ship."""
    if len(pid_dates) < 2:
        return True
    ordered = sorted(
        ((pid, min(dates), max(dates)) for pid, dates in pid_dates.items() if dates),
        key=lambda t: (t[1], t[0]),
    )
    for i in range(len(ordered) - 1):
        _, _, max_a = ordered[i]
        _, min_b, _ = ordered[i + 1]
        if max_a >= min_b:
            return False
    return True


def _pick_by_transition_date(
    inter: set[int],
    pid_dates: dict[int, list[date]],
    evidence_date: date,
) -> int | None:
    ordered = sorted(
        ((pid, min(dates)) for pid, dates in pid_dates.items() if pid in inter and dates),
        key=lambda t: (t[1], t[0]),
    )
    if len(ordered) < 2:
        return None
    if not _windows_strictly_separated({pid: pid_dates[pid] for pid in inter}):
        return None
    # Last product whose first_ship <= evidence_date; if before first transition use earliest pid.
    pick: int | None = None
    for pid, first_ship in ordered:
        if evidence_date >= first_ship:
            pick = int(pid)
        else:
            break
    if pick is None:
        pick = int(ordered[0][0])
    return pick


def try_receipt_disambiguate_product(
    receipt_index: DistributorReceiptProductIndex | None,
    *,
    distributor_id: int | None,
    dist_id_to_canonical: dict[int, str],
    raw_product_token: str | None,
    eligible_product_ids: list[int],
    evidence_date: date | None,
    ambiguous_eligible: dict[str, Any] | None,
) -> ReceiptDisambiguationResult:
    """Apply T1–T4 receipt tiers. Never returns a pick outside ``eligible_product_ids``."""
    if receipt_index is None or not eligible_product_ids or ambiguous_eligible is None:
        return ReceiptDisambiguationResult(None, None)
    sm_key = _sales_model_key_from_token(raw_product_token)
    if not sm_key:
        return ReceiptDisambiguationResult(None, None)

    canon = ""
    if distributor_id is not None:
        canon = dist_id_to_canonical.get(int(distributor_id)) or canonical_provisional_entity_name_key(
            str(distributor_id)
        )

    def _prov(tier: str, pick: int, receipt_set: set[int], scope: str) -> dict[str, Any]:
        return {
            "receipt_disambiguation": {
                "tier": tier,
                "resolved_product_id": int(pick),
                "receipt_product_ids": sorted(int(x) for x in receipt_set),
                "receipt_line_count": receipt_index.line_count(
                    canonical_distributor_key=canon if scope.startswith("distributor") else None,
                    sales_model_key=sm_key,
                ),
                "scope": scope,
                "canonical_distributor_key": canon or None,
                "sales_model_key": sm_key,
                "unwindowed": True,
            }
        }

    if canon:
        dist_receipt = receipt_index.receipt_product_ids(canon, sm_key)
        inter = _intersect_eligible(eligible_product_ids, dist_receipt)
        if len(inter) == 1:
            pick = int(next(iter(inter)))
            return ReceiptDisambiguationResult(pick, "T1", _prov("T1", pick, dist_receipt, "distributor+sales_model"))
        if len(inter) > 1 and evidence_date is not None:
            pid_dates = receipt_index.ship_dates_for_scope(canon, sm_key)
            pick = _pick_by_transition_date(inter, pid_dates, evidence_date)
            if pick is not None:
                return ReceiptDisambiguationResult(
                    pick, "T2", _prov("T2", pick, dist_receipt, "distributor+sales_model_transition")
                )

    global_receipt = receipt_index.global_receipt_product_ids(sm_key)
    inter_g = _intersect_eligible(eligible_product_ids, global_receipt)
    if len(inter_g) == 1:
        pick = int(next(iter(inter_g)))
        return ReceiptDisambiguationResult(pick, "T3", _prov("T3", pick, global_receipt, "global+sales_model"))

    return ReceiptDisambiguationResult(None, "T4")


def preview_receipt_disambiguation_for_staging_rows(
    db: Session,
    *,
    import_job_id: int,
    receipt_index: DistributorReceiptProductIndex,
    dist_id_to_canonical: dict[int, str],
) -> dict[str, Any]:
    """Dry-run tier counts for unresolved staging rows on a DSI job."""
    from app.models.import_distributor_si import ImportDistributorSiStagingLine

    rows = db.execute(
        text(
            """
            SELECT id, raw_product_token, resolved_distributor_id, transaction_date, snapshot_date
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

    for _id, raw, dist_id, tx, snap in rows:
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
        res = try_receipt_disambiguate_product(
            receipt_index,
            distributor_id=int(dist_id) if dist_id is not None else None,
            dist_id_to_canonical=dist_id_to_canonical,
            raw_product_token=str(raw) if raw else None,
            eligible_product_ids=elig,
            evidence_date=ev_date if isinstance(ev_date, date) else None,
            ambiguous_eligible=pev.ambiguous_eligible,
        )
        if res.product_id is not None and res.tier:
            tier_counts[res.tier] += 1
        else:
            tier_counts["T4"] += 1
            tier_counts["still_ambiguous"] += 1

    return dict(tier_counts)


def preview_cross_distributor_misassignments(
    db: Session,
    *,
    import_job_id: int,
    receipt_index: DistributorReceiptProductIndex,
    dist_id_to_canonical: dict[int, str],
    sample_limit: int = 3,
) -> dict[str, Any]:
    """Dry-run Unit 4: rows resolved to a SKU with no receipt for their distributor.

    Re-simulates receipt disambiguation (T1–T4) and counts rows where the tier pick differs
    from ``resolved_product_id``.
    """
    from app.services.imports.distributor_sales_inventory import _load_product_resolution_index, _resolve_product

    rows = db.execute(
        text(
            """
            SELECT s.id,
                   s.raw_product_token,
                   s.resolved_product_id,
                   s.resolved_distributor_id,
                   s.transaction_date,
                   s.snapshot_date
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
        ),
        {"jid": int(import_job_id)},
    ).fetchall()

    prod_idx = _load_product_resolution_index(db)
    counts: dict[str, int] = defaultdict(int)
    counts["misassign_candidate_rows"] = len(rows)
    scope_keys: set[tuple[int, str, int]] = set()
    samples: list[dict[str, Any]] = []

    for row_id, raw, cur_pid, dist_id, tx, snap in rows:
        cur_pid = int(cur_pid)
        dist_id = int(dist_id)
        sm = str(raw or "").strip()
        scope_keys.add((dist_id, _sales_model_key_from_token(raw), cur_pid))
        ev_date = tx or snap
        if ev_date is None:
            counts["no_evidence_date"] += 1
            continue

        _rpid, _perr, _tag, pev = _resolve_product(
            raw,
            prod_idx,
            ev_date if isinstance(ev_date, date) else None,
            relax_inactive_dim_product_for_historical_dsi=True,
        )
        elig: list[int] = []
        if pev and pev.ambiguous_eligible:
            elig = [int(x) for x in (pev.ambiguous_eligible.get("product_ids") or []) if int(x) > 0]
        elif cur_pid > 0:
            elig = [cur_pid]

        res = try_receipt_disambiguate_product(
            receipt_index,
            distributor_id=dist_id,
            dist_id_to_canonical=dist_id_to_canonical,
            raw_product_token=str(raw) if raw else None,
            eligible_product_ids=elig,
            evidence_date=ev_date if isinstance(ev_date, date) else None,
            ambiguous_eligible=pev.ambiguous_eligible if pev else None,
        )
        if res.product_id is not None and int(res.product_id) != cur_pid:
            counts["would_reassign"] += 1
            counts[f"reassign_{res.tier}"] += 1
            if len(samples) < sample_limit:
                samples.append(
                    {
                        "staging_line_id": int(row_id),
                        "raw_product_token": sm,
                        "resolved_distributor_id": dist_id,
                        "current_product_id": cur_pid,
                        "proposed_product_id": int(res.product_id),
                        "tier": res.tier,
                        "evidence_date": str(ev_date),
                        "provenance": res.provenance,
                    }
                )
        elif res.product_id is not None and int(res.product_id) == cur_pid:
            counts["receipt_confirms_current"] += 1
        else:
            counts["still_unresolved"] += 1

    counts["distinct_scopes"] = len(scope_keys)
    return {"counts": dict(counts), "sample_traces": samples}
