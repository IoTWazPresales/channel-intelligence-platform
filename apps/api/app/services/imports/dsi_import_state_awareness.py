"""DSI import intelligence state — read-only awareness for validate and steward UX."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ingestion.pipeline import STAGE_LOADED
from app.models.facts import FactInboundShipment, FactSalesSellout
from app.models.ingestion import ImportJob
from app.utils.json_safe import to_jsonable

AutoResolutionTier = Literal["none", "supervised", "automatic"]
LayerStatus = Literal["active", "degraded", "initialising", "inactive"]


@dataclass(frozen=True)
class DsiImportIntelligenceState:
    prior_applied_job_count: int
    last_applied_job_id: int | None
    last_applied_period_end: date | None
    has_shipment_evidence: bool
    has_cpor_data: bool
    velocity_weeks_available: int
    detected_mode: str
    auto_resolution_tier: AutoResolutionTier
    intelligence_layers: dict[str, LayerStatus]
    banners: list[dict[str, str]] = field(default_factory=list)

    def to_metadata_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        if raw.get("last_applied_period_end") is not None:
            raw["last_applied_period_end"] = raw["last_applied_period_end"].isoformat()
        return to_jsonable(raw)


def _table_exists(session: Session, table_name: str) -> bool:
    from sqlalchemy import inspect as sa_inspect

    try:
        return bool(sa_inspect(session.get_bind()).has_table(table_name))
    except Exception:
        return False


def _count_prior_applied_dsi_jobs(
    session: Session,
    *,
    source_definition_id: int,
    current_job_id: int,
) -> tuple[int, int | None]:
    q = (
        select(ImportJob.id)
        .where(
            ImportJob.source_id == int(source_definition_id),
            ImportJob.template_slug == "distributor_inventory",
            ImportJob.id != int(current_job_id),
            or_(
                ImportJob.import_mode == "apply",
                ImportJob.stage == STAGE_LOADED,
            ),
        )
        .order_by(ImportJob.completed_at.desc().nullslast(), ImportJob.id.desc())
    )
    ids = [int(x) for x in session.scalars(q).all()]
    if not ids:
        return 0, None
    return len(ids), ids[0]


def _last_applied_period_end(
    session: Session,
    *,
    distributor_id: int | None,
    last_applied_job_id: int | None,
) -> date | None:
    if distributor_id is None:
        return None
    dist_id = int(distributor_id)
    if last_applied_job_id is not None:
        row = session.execute(
            select(func.max(FactSalesSellout.transaction_date)).where(
                FactSalesSellout.distributor_id == dist_id,
                FactSalesSellout.source_import_job_id == int(last_applied_job_id),
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    row = session.execute(
        select(func.max(FactSalesSellout.transaction_date)).where(
            FactSalesSellout.distributor_id == dist_id,
        )
    ).scalar_one_or_none()
    return row


def _has_shipment_evidence(session: Session, distributor_id: int | None) -> bool:
    if distributor_id is None:
        return False
    n = session.scalar(
        select(func.count())
        .select_from(FactInboundShipment)
        .where(FactInboundShipment.distributor_id == int(distributor_id))
        .limit(1)
    )
    return int(n or 0) > 0


def _has_cpor_data(session: Session, distributor_id: int | None) -> bool:
    """CPOR pricing intelligence is inactive until a dedicated CPOR import module lands.

    There is no distributor-scoped CPOR fact table in the schema today (``FactPromotionPlan`` and
    ``FactPricing`` are not CPOR import evidence). Returning ``False`` keeps
    ``pricing_intelligence`` in ``degraded`` state and surfaces the CPOR banner honestly.
    """
    _ = session, distributor_id
    return False


def _velocity_weeks_available(session: Session, distributor_id: int | None) -> int:
    if distributor_id is None:
        return 0
    if not _table_exists(session, "fact_customer_velocity"):
        return 0
    try:
        from sqlalchemy import text

        row = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT week_start_date)::int
                FROM fact_customer_velocity
                WHERE distributor_id = :dist_id
                """
            ),
            {"dist_id": int(distributor_id)},
        ).scalar_one_or_none()
        return int(row or 0)
    except Exception:
        return 0


def _tier_from_prior_count(count: int) -> AutoResolutionTier:
    if count >= 2:
        return "automatic"
    if count == 1:
        return "supervised"
    return "none"


def _layer_statuses(
    *,
    prior_applied_job_count: int,
    has_shipment_evidence: bool,
    has_cpor_data: bool,
    velocity_weeks_available: int,
) -> dict[str, LayerStatus]:
    token: LayerStatus = "active" if prior_applied_job_count >= 1 else "inactive"
    soh: LayerStatus = "active" if has_shipment_evidence else "degraded"
    if velocity_weeks_available >= 4:
        velocity: LayerStatus = "active"
    elif velocity_weeks_available >= 1:
        velocity = "initialising"
    else:
        velocity = "inactive"
    pricing: LayerStatus = "active" if has_cpor_data else "degraded"
    if velocity_weeks_available >= 52:
        forecasting: LayerStatus = "active"
    elif velocity_weeks_available >= 13:
        forecasting = "initialising"
    else:
        forecasting = "inactive"
    return {
        "token_auto_resolution": token,
        "soh_reconciliation": soh,
        "velocity_learning": velocity,
        "pricing_intelligence": pricing,
        "forecasting": forecasting,
    }


def _build_banners(
    *,
    prior_applied_job_count: int,
    has_shipment_evidence: bool,
    has_cpor_data: bool,
    velocity_weeks_available: int,
    auto_resolution_tier: AutoResolutionTier,
    detected_mode: str,
) -> list[dict[str, str]]:
    banners: list[dict[str, str]] = []
    if prior_applied_job_count == 0:
        banners.append(
            {
                "level": "warning",
                "layer": "token_auto_resolution",
                "message": (
                    "No baseline data found for this distributor. "
                    "Full steward review required."
                ),
            }
        )
    if not has_shipment_evidence:
        banners.append(
            {
                "level": "warning",
                "layer": "soh_reconciliation",
                "message": (
                    "Shipment data unavailable. "
                    "SOH reconciliation inactive."
                ),
            }
        )
    if not has_cpor_data:
        banners.append(
            {
                "level": "info",
                "layer": "pricing_intelligence",
                "message": (
                    "CPOR not loaded. "
                    "Price variance detection inactive."
                ),
            }
        )
    if 1 <= velocity_weeks_available < 4:
        banners.append(
            {
                "level": "info",
                "layer": "velocity_learning",
                "message": (
                    "Velocity baseline building. "
                    "Intelligence improves with each cycle."
                ),
            }
        )
    if (
        auto_resolution_tier == "supervised"
        and detected_mode == "weekly"
        and prior_applied_job_count == 1
    ):
        banners.append(
            {
                "level": "info",
                "layer": "token_auto_resolution",
                "message": (
                    "Prior steward decisions loaded. "
                    "Auto-resolved tokens require one-time review "
                    "before apply."
                ),
            }
        )
    return banners


def check_dsi_import_state(
    session: Session,
    job_id: int,
    distributor_id: int | None,
) -> DsiImportIntelligenceState:
    """Read-only intelligence snapshot for a DSI import job."""
    job = session.get(ImportJob, int(job_id))
    if job is None:
        raise ValueError(f"Import job {job_id} not found")

    sm = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    detected_mode = str(sm.get("dsi_workflow_mode") or "weekly").strip().lower()

    source_def_id: int | None = None
    if job.source is not None:
        source_def_id = int(job.source.id)
    elif job.source_id is not None:
        source_def_id = int(job.source_id)

    prior_count = 0
    last_job_id: int | None = None
    if source_def_id is not None:
        prior_count, last_job_id = _count_prior_applied_dsi_jobs(
            session,
            source_definition_id=source_def_id,
            current_job_id=int(job_id),
        )

    period_end = _last_applied_period_end(
        session,
        distributor_id=distributor_id,
        last_applied_job_id=last_job_id,
    )
    has_ship = _has_shipment_evidence(session, distributor_id)
    has_cpor = _has_cpor_data(session, distributor_id)
    velocity_weeks = _velocity_weeks_available(session, distributor_id)
    tier = _tier_from_prior_count(prior_count)
    layers = _layer_statuses(
        prior_applied_job_count=prior_count,
        has_shipment_evidence=has_ship,
        has_cpor_data=has_cpor,
        velocity_weeks_available=velocity_weeks,
    )
    banners = _build_banners(
        prior_applied_job_count=prior_count,
        has_shipment_evidence=has_ship,
        has_cpor_data=has_cpor,
        velocity_weeks_available=velocity_weeks,
        auto_resolution_tier=tier,
        detected_mode=detected_mode,
    )

    return DsiImportIntelligenceState(
        prior_applied_job_count=prior_count,
        last_applied_job_id=last_job_id,
        last_applied_period_end=period_end,
        has_shipment_evidence=has_ship,
        has_cpor_data=has_cpor,
        velocity_weeks_available=velocity_weeks,
        detected_mode=detected_mode,
        auto_resolution_tier=tier,
        intelligence_layers=layers,
        banners=banners,
    )


def persist_intelligence_state_on_job(
    session: Session,
    job: ImportJob,
    state: DsiImportIntelligenceState,
) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta["intelligence_state"] = state.to_metadata_dict()
    job.staged_metadata = to_jsonable(meta)
    if hasattr(job, "_sa_instance_state"):
        flag_modified(job, "staged_metadata")
    session.add(job)


def resolve_primary_distributor_id_from_dataframe(
    session: Session,
    df: Any,
    mapping: dict[str, str],
    source_def_id: int | None,
) -> int | None:
    """Resolve the first non-empty distributor token in the file (primary scope for intelligence)."""
    from app.services.imports.distributor_sales_inventory import (
        _build_resolution_cache,
        _clean_str,
        _col,
        _resolve_distributor_from_cache,
    )

    col = _col(mapping, "distributor_token")
    if not col or col not in df.columns:
        return None
    res_cache = _build_resolution_cache(session, source_def_id)
    for _, row in df.iterrows():
        raw = _clean_str(row.get(col))
        if not raw:
            continue
        did, _err = _resolve_distributor_from_cache(raw, source_def_id, res_cache)
        if did is not None:
            return int(did)
    return None
