"""BACKLOG-097 weeks-of-cover observation helpers (no cip writes)."""

from __future__ import annotations

from datetime import date

from app.models.derived import WeeksOfCoverObservation
from app.services.imports.woc_observation import (
    align_spine_start,
    cadence_interval_sql,
    woc_observation_source_key_asof,
    woc_observation_source_key_job,
)


def test_observation_model_source_key_unique() -> None:
    cols = {c.name for c in WeeksOfCoverObservation.__table__.columns}
    assert "source_key" in cols
    assert "cover_as_of_date" in cols
    assert "weeks_of_cover" in cols
    uniques = {c.name for c in WeeksOfCoverObservation.__table__.constraints if getattr(c, "name", None)}
    assert "uq_weeks_of_cover_observation_source_key" in uniques
    assert WeeksOfCoverObservation.__table__.c.weeks_of_cover.nullable is True


def test_source_key_job_vs_asof_do_not_collide() -> None:
    job_key = woc_observation_source_key_job(distributor_id=7, product_id=99, import_job_id=12)
    asof_key = woc_observation_source_key_asof(
        distributor_id=7, product_id=99, cover_as_of=date(2026, 8, 17)
    )
    assert job_key == "woc:7:99:job:12"
    assert asof_key == "woc:7:99:asof:2026-08-17"
    assert job_key != asof_key


def test_align_spine_start_weekly_monday() -> None:
    # Wednesday 2026-08-12 → next Monday 2026-08-17
    assert align_spine_start(date(2026, 8, 12), "weekly_monday") == date(2026, 8, 17)
    assert align_spine_start(date(2026, 8, 17), "weekly_monday") == date(2026, 8, 17)
    assert align_spine_start(date(2026, 8, 12), "daily") == date(2026, 8, 12)
    assert cadence_interval_sql("weekly_monday") == "7 days"
    assert cadence_interval_sql("daily") == "1 day"
