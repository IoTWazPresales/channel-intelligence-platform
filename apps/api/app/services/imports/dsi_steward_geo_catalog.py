"""Steward mutations for DSI governed dim_channel / dim_region + source-token aliases (import workflow)."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimRegion
from app.models.import_distributor_si import ChannelSourceTokenAlias, RegionSourceTokenAlias
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import _norm_key
from app.services.imports.dsi_steward_candidate_ops import StewardOpError


def _assert_dsi_job(sess: Session, import_job_id: int) -> ImportJob:
    job = sess.get(ImportJob, int(import_job_id))
    if not job:
        raise StewardOpError("Import job not found", status_code=404)
    if (job.template_slug or "") != "distributor_inventory":
        raise StewardOpError("Job is not a distributor sales & inventory import", status_code=400)
    return job


def _source_definition_id_for_job(job: ImportJob) -> int | None:
    if job.source is None:
        return None
    return int(job.source.id)


def _channel_alias_exists(
    sess: Session,
    *,
    normalized_token: str,
    channel_id: int,
    source_definition_id: int | None,
) -> ChannelSourceTokenAlias | None:
    q = select(ChannelSourceTokenAlias).where(
        ChannelSourceTokenAlias.normalized_token == normalized_token,
        ChannelSourceTokenAlias.channel_id == int(channel_id),
        ChannelSourceTokenAlias.status == "approved",
    )
    if source_definition_id is not None:
        q = q.where(
            or_(
                ChannelSourceTokenAlias.source_definition_id.is_(None),
                ChannelSourceTokenAlias.source_definition_id == source_definition_id,
            )
        )
    else:
        q = q.where(ChannelSourceTokenAlias.source_definition_id.is_(None))
    return sess.scalar(q.limit(1))


def _region_alias_exists(
    sess: Session,
    *,
    normalized_token: str,
    region_id: int,
    source_definition_id: int | None,
) -> RegionSourceTokenAlias | None:
    q = select(RegionSourceTokenAlias).where(
        RegionSourceTokenAlias.normalized_token == normalized_token,
        RegionSourceTokenAlias.region_id == int(region_id),
        RegionSourceTokenAlias.status == "approved",
    )
    if source_definition_id is not None:
        q = q.where(
            or_(
                RegionSourceTokenAlias.source_definition_id.is_(None),
                RegionSourceTokenAlias.source_definition_id == source_definition_id,
            )
        )
    else:
        q = q.where(RegionSourceTokenAlias.source_definition_id.is_(None))
    return sess.scalar(q.limit(1))


def create_dim_channel_with_source_alias_sync(
    sess: Session,
    *,
    import_job_id: int,
    channel_code: str,
    channel_name: str,
    raw_token: str,
    notes: str | None,
) -> dict[str, object]:
    job = _assert_dsi_job(sess, import_job_id)
    rt = (raw_token or "").strip()
    if not rt:
        raise StewardOpError("raw_token is required (preserved as evidence)", status_code=400)
    code = (channel_code or "").strip().upper()
    name = (channel_name or "").strip()
    if not code or len(code) > 32:
        raise StewardOpError("channel_code is required (max 32 chars)", status_code=400)
    if not name or len(name) > 256:
        raise StewardOpError("channel_name is required (max 256 chars)", status_code=400)

    src_id = _source_definition_id_for_job(job)
    nt = _norm_key(rt)
    if not nt:
        raise StewardOpError("raw_token normalizes to empty", status_code=400)

    row_ch = sess.scalar(select(DimChannel).where(func.lower(DimChannel.code) == code.lower()))
    if row_ch is not None:
        raise StewardOpError(f"dim_channel code already exists: {row_ch.code}", status_code=409)

    ch = DimChannel(code=code, name=name)
    sess.add(ch)
    try:
        sess.flush()
    except IntegrityError as exc:
        sess.rollback()
        raise StewardOpError("dim_channel code or name violates uniqueness", status_code=409) from exc

    alias = ChannelSourceTokenAlias(
        channel_id=int(ch.id),
        source_definition_id=src_id,
        raw_token=rt[:512],
        normalized_token=nt[:512],
        status="approved",
        notes=(notes or "").strip() or None,
        created_from_import_job_id=int(import_job_id),
    )
    sess.add(alias)
    sess.flush()
    return {
        "ok": True,
        "channel_id": int(ch.id),
        "channel_code": ch.code,
        "channel_name": ch.name,
        "alias_id": int(alias.id),
        "normalized_token": nt,
        "raw_token": rt[:512],
    }


def create_channel_source_token_alias_sync(
    sess: Session,
    *,
    import_job_id: int,
    channel_id: int,
    raw_token: str,
    notes: str | None,
) -> dict[str, object]:
    job = _assert_dsi_job(sess, import_job_id)
    ch = sess.get(DimChannel, int(channel_id))
    if not ch:
        raise StewardOpError("dim_channel not found", status_code=404)
    rt = (raw_token or "").strip()
    if not rt:
        raise StewardOpError("raw_token is required", status_code=400)
    src_id = _source_definition_id_for_job(job)
    nt = _norm_key(rt)
    if not nt:
        raise StewardOpError("raw_token normalizes to empty", status_code=400)

    hit = _channel_alias_exists(sess, normalized_token=nt, channel_id=int(ch.id), source_definition_id=src_id)
    if hit is not None:
        return {
            "ok": True,
            "idempotent": True,
            "alias_id": int(hit.id),
            "channel_id": int(ch.id),
            "normalized_token": nt,
            "raw_token": hit.raw_token,
        }

    alias = ChannelSourceTokenAlias(
        channel_id=int(ch.id),
        source_definition_id=src_id,
        raw_token=rt[:512],
        normalized_token=nt[:512],
        status="approved",
        notes=(notes or "").strip() or None,
        created_from_import_job_id=int(import_job_id),
    )
    sess.add(alias)
    sess.flush()
    return {
        "ok": True,
        "idempotent": False,
        "alias_id": int(alias.id),
        "channel_id": int(ch.id),
        "normalized_token": nt,
        "raw_token": rt[:512],
    }


def create_dim_region_with_source_alias_sync(
    sess: Session,
    *,
    import_job_id: int,
    region_code: str,
    region_name: str,
    raw_token: str,
    notes: str | None,
) -> dict[str, object]:
    job = _assert_dsi_job(sess, import_job_id)
    rt = (raw_token or "").strip()
    if not rt:
        raise StewardOpError("raw_token is required (preserved as evidence)", status_code=400)
    code = (region_code or "").strip().upper()
    name = (region_name or "").strip()
    if not code or len(code) > 32:
        raise StewardOpError("region_code is required (max 32 chars)", status_code=400)
    if not name or len(name) > 256:
        raise StewardOpError("region_name is required (max 256 chars)", status_code=400)

    src_id = _source_definition_id_for_job(job)
    nt = _norm_key(rt)
    if not nt:
        raise StewardOpError("raw_token normalizes to empty", status_code=400)

    row_r = sess.scalar(select(DimRegion).where(func.lower(DimRegion.code) == code.lower()))
    if row_r is not None:
        raise StewardOpError(f"dim_region code already exists: {row_r.code}", status_code=409)

    reg = DimRegion(code=code, name=name)
    sess.add(reg)
    try:
        sess.flush()
    except IntegrityError as exc:
        sess.rollback()
        raise StewardOpError("dim_region code or name violates uniqueness", status_code=409) from exc

    alias = RegionSourceTokenAlias(
        region_id=int(reg.id),
        source_definition_id=src_id,
        raw_token=rt[:512],
        normalized_token=nt[:512],
        status="approved",
        notes=(notes or "").strip() or None,
        created_from_import_job_id=int(import_job_id),
    )
    sess.add(alias)
    sess.flush()
    return {
        "ok": True,
        "region_id": int(reg.id),
        "region_code": reg.code,
        "region_name": reg.name,
        "alias_id": int(alias.id),
        "normalized_token": nt,
        "raw_token": rt[:512],
    }


def create_region_source_token_alias_sync(
    sess: Session,
    *,
    import_job_id: int,
    region_id: int,
    raw_token: str,
    notes: str | None,
) -> dict[str, object]:
    job = _assert_dsi_job(sess, import_job_id)
    reg = sess.get(DimRegion, int(region_id))
    if not reg:
        raise StewardOpError("dim_region not found", status_code=404)
    rt = (raw_token or "").strip()
    if not rt:
        raise StewardOpError("raw_token is required", status_code=400)
    src_id = _source_definition_id_for_job(job)
    nt = _norm_key(rt)
    if not nt:
        raise StewardOpError("raw_token normalizes to empty", status_code=400)

    hit = _region_alias_exists(sess, normalized_token=nt, region_id=int(reg.id), source_definition_id=src_id)
    if hit is not None:
        return {
            "ok": True,
            "idempotent": True,
            "alias_id": int(hit.id),
            "region_id": int(reg.id),
            "normalized_token": nt,
            "raw_token": hit.raw_token,
        }

    alias = RegionSourceTokenAlias(
        region_id=int(reg.id),
        source_definition_id=src_id,
        raw_token=rt[:512],
        normalized_token=nt[:512],
        status="approved",
        notes=(notes or "").strip() or None,
        created_from_import_job_id=int(import_job_id),
    )
    sess.add(alias)
    sess.flush()
    return {
        "ok": True,
        "idempotent": False,
        "alias_id": int(alias.id),
        "region_id": int(reg.id),
        "normalized_token": nt,
        "raw_token": rt[:512],
    }
