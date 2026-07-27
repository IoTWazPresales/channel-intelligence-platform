"""DSI weekly coverage read model — missed sell-out / SOH weeks (FLAG only)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dimensions import DimDistributor
from app.models.facts import FactInventoryDistributor, FactSalesSellout
from app.models.ingestion import ImportJob

CoverageSignal = Literal["sellout", "soh"]
ACTIVE_MIN_WEEKS = 3
DEFAULT_WEEKS = 12
MAX_WEEKS = 26


def iso_week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def trailing_iso_weeks(*, end: date | None = None, count: int) -> list[date]:
    end = end or date.today()
    current = iso_week_start(end)
    return sorted(current - timedelta(weeks=i) for i in range(count))


def _table_exists(session: Session, table_name: str) -> bool:
    from sqlalchemy import inspect as sa_inspect

    try:
        return bool(sa_inspect(session.get_bind()).has_table(table_name))
    except Exception:
        return False


def _distributor_ids_for_source(session: Session, source_id: int | None) -> set[int] | None:
    if source_id is None:
        return None
    sellout_ids = session.scalars(
        select(FactSalesSellout.distributor_id)
        .join(ImportJob, ImportJob.id == FactSalesSellout.source_import_job_id)
        .where(ImportJob.source_id == int(source_id), FactSalesSellout.distributor_id.isnot(None))
        .distinct()
    ).all()
    soh_ids = session.scalars(
        select(FactInventoryDistributor.distributor_id)
        .join(ImportJob, ImportJob.id == FactInventoryDistributor.source_import_job_id)
        .where(ImportJob.source_id == int(source_id))
        .distinct()
    ).all()
    out = {int(x) for x in sellout_ids if x is not None} | {int(x) for x in soh_ids}
    return out


def _weeks_with_data(
    session: Session,
    *,
    signal: CoverageSignal,
    window_start: date,
    distributor_ids: set[int] | None,
) -> dict[int, set[date]]:
    out: dict[int, set[date]] = {}
    if signal == "sellout":
        if not _table_exists(session, "fact_sales_sellout"):
            return out
        week_expr = func.date_trunc("week", FactSalesSellout.transaction_date)
        q = (
            select(
                FactSalesSellout.distributor_id,
                week_expr.label("week_start"),
            )
            .where(
                FactSalesSellout.distributor_id.isnot(None),
                FactSalesSellout.transaction_date >= window_start,
            )
            .group_by(FactSalesSellout.distributor_id, week_expr)
        )
        if distributor_ids is not None:
            if not distributor_ids:
                return out
            q = q.where(FactSalesSellout.distributor_id.in_(sorted(distributor_ids)))
        for dist_id, week_ts in session.execute(q).all():
            if dist_id is None or week_ts is None:
                continue
            week = week_ts.date() if hasattr(week_ts, "date") else week_ts
            out.setdefault(int(dist_id), set()).add(week)
        return out

    if not _table_exists(session, "fact_inventory_distributor"):
        return out
    week_expr = func.date_trunc("week", FactInventoryDistributor.as_of_date)
    q = (
        select(
            FactInventoryDistributor.distributor_id,
            week_expr.label("week_start"),
        )
        .where(FactInventoryDistributor.as_of_date >= window_start)
        .group_by(FactInventoryDistributor.distributor_id, week_expr)
    )
    if distributor_ids is not None:
        if not distributor_ids:
            return out
        q = q.where(FactInventoryDistributor.distributor_id.in_(sorted(distributor_ids)))
    for dist_id, week_ts in session.execute(q).all():
        if dist_id is None or week_ts is None:
            continue
        week = week_ts.date() if hasattr(week_ts, "date") else week_ts
        out.setdefault(int(dist_id), set()).add(week)
    return out


def signal_coverage(
    covered: set[date],
    window_weeks: list[date],
) -> tuple[bool, list[str], list[str]]:
    in_window = covered.intersection(window_weeks)
    weekly_active = len(in_window) >= ACTIVE_MIN_WEEKS
    covered_sorted = sorted(in_window)
    missed = sorted(w for w in window_weeks if w not in covered) if weekly_active else []
    return (
        weekly_active,
        [d.isoformat() for d in covered_sorted],
        [d.isoformat() for d in missed],
    )


@dataclass(frozen=True)
class DsiCoverageFlag:
    distributor_id: int
    distributor_name: str
    signal: CoverageSignal
    week_start: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "distributor_id": self.distributor_id,
            "distributor_name": self.distributor_name,
            "signal": self.signal,
            "week_start": self.week_start,
            "message": self.message,
        }


def compute_dsi_coverage(
    session: Session,
    *,
    source_id: int | None = None,
    weeks: int = DEFAULT_WEEKS,
    as_of: date | None = None,
) -> dict[str, Any]:
    weeks = max(4, min(int(weeks), MAX_WEEKS))
    window_weeks = trailing_iso_weeks(end=as_of, count=weeks)
    window_start = window_weeks[0] if window_weeks else date.today()

    if not _table_exists(session, "fact_sales_sellout") and not _table_exists(
        session, "fact_inventory_distributor"
    ):
        return {
            "data_unavailable": True,
            "weeks": weeks,
            "week_starts": [w.isoformat() for w in window_weeks],
            "distributors": [],
            "flags": [],
        }

    scope_ids = _distributor_ids_for_source(session, source_id)
    sellout_map = _weeks_with_data(session, signal="sellout", window_start=window_start, distributor_ids=scope_ids)
    soh_map = _weeks_with_data(session, signal="soh", window_start=window_start, distributor_ids=scope_ids)

    all_dist_ids = set(sellout_map.keys()) | set(soh_map.keys())
    if scope_ids is not None:
        all_dist_ids &= scope_ids

    names: dict[int, str] = {}
    if all_dist_ids and _table_exists(session, "dim_distributor"):
        for row in session.scalars(
            select(DimDistributor).where(DimDistributor.id.in_(sorted(all_dist_ids)))
        ).all():
            names[int(row.id)] = str(row.name or row.distributor_code or f"Distributor #{row.id}")

    distributors: list[dict[str, Any]] = []
    flags: list[DsiCoverageFlag] = []

    for dist_id in sorted(all_dist_ids):
        name = names.get(dist_id, f"Distributor #{dist_id}")
        sell_active, sell_covered, sell_missed = signal_coverage(sellout_map.get(dist_id, set()), window_weeks)
        soh_active, soh_covered, soh_missed = signal_coverage(soh_map.get(dist_id, set()), window_weeks)
        distributors.append(
            {
                "distributor_id": dist_id,
                "distributor_name": name,
                "sellout": {
                    "weekly_active": sell_active,
                    "covered_weeks": sell_covered,
                    "missed_weeks": sell_missed,
                },
                "soh": {
                    "weekly_active": soh_active,
                    "covered_weeks": soh_covered,
                    "missed_weeks": soh_missed,
                },
            }
        )
        for week_iso in sell_missed:
            flags.append(
                DsiCoverageFlag(
                    distributor_id=dist_id,
                    distributor_name=name,
                    signal="sellout",
                    week_start=week_iso,
                    message=f"{name} has no sell-out for week of {week_iso}",
                )
            )
        for week_iso in soh_missed:
            flags.append(
                DsiCoverageFlag(
                    distributor_id=dist_id,
                    distributor_name=name,
                    signal="soh",
                    week_start=week_iso,
                    message=f"{name} has no distributor SOH snapshot for week of {week_iso}",
                )
            )

    return {
        "data_unavailable": False,
        "source_id": source_id,
        "weeks": weeks,
        "week_starts": [w.isoformat() for w in window_weeks],
        "distributors": distributors,
        "flags": [f.to_dict() for f in flags],
    }
