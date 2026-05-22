"""In-memory geo catalog + alias cache for DSI unresolved-geo collection and bulk provisional."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.dimensions import DimChannel, DimRegion
from app.models.import_distributor_si import ChannelSourceTokenAlias, RegionSourceTokenAlias
from app.models.ingestion import ImportJob
from app.services.imports.distributor_sales_inventory import _norm_key


def _pick_raw_for_norm(samples: list[Any], norm: str) -> str | None:
    for item in samples:
        if isinstance(item, str) and _norm_key(item) == norm:
            return item.strip()
    return norm


def _alias_channel_id_from_rows(
    rows: list[tuple[int | None, int]],
) -> tuple[int | None, str | None]:
    ids = list(dict.fromkeys(r[1] for r in rows))
    if len(ids) == 1:
        return int(ids[0]), "source_channel_token_alias"
    if len(ids) > 1:
        return None, "conflicting_channel_token_aliases"
    return None, None


def _alias_region_id_from_rows(
    rows: list[tuple[int | None, int]],
) -> tuple[int | None, str | None]:
    ids = list(dict.fromkeys(r[1] for r in rows))
    if len(ids) == 1:
        return int(ids[0]), "source_region_token_alias"
    if len(ids) > 1:
        return None, "conflicting_region_token_aliases"
    return None, None


class DSIGeoResolutionCache:
    """Preload dim channel/region catalogs and batch-load source-token aliases by normalized token."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._channels_by_code: dict[str, int] = {}
        self._channels_by_name_norm: dict[str, int] = {}
        self._regions_by_code: dict[str, int] = {}
        self._regions_by_name_norm: dict[str, int] = {}
        self._channel_alias_rows: dict[str, list[tuple[int | None, int]]] = {}
        self._region_alias_rows: dict[str, list[tuple[int | None, int]]] = {}

    @classmethod
    def build(cls, session: Session) -> DSIGeoResolutionCache:
        cache = cls(session)
        cache._load_dim_catalogs()
        return cache

    def _load_dim_catalogs(self) -> None:
        for ch in self._session.scalars(select(DimChannel)):
            if ch.code:
                self._channels_by_code[str(ch.code).lower()] = int(ch.id)
            if ch.name:
                self._channels_by_name_norm[_norm_key(ch.name)] = int(ch.id)
        for reg in self._session.scalars(select(DimRegion)):
            if reg.code:
                self._regions_by_code[str(reg.code).lower()] = int(reg.id)
            if reg.name:
                self._regions_by_name_norm[_norm_key(reg.name)] = int(reg.id)

    def preload_aliases(self, normalized_tokens: set[str]) -> None:
        tokens = {t for t in normalized_tokens if t}
        if not tokens:
            return
        ch_rows = self._session.execute(
            select(
                ChannelSourceTokenAlias.normalized_token,
                ChannelSourceTokenAlias.source_definition_id,
                ChannelSourceTokenAlias.channel_id,
            ).where(
                ChannelSourceTokenAlias.normalized_token.in_(tokens),
                ChannelSourceTokenAlias.status == "approved",
            )
        ).all()
        for nt, sid, cid in ch_rows:
            self._channel_alias_rows.setdefault(str(nt), []).append(
                (int(sid) if sid is not None else None, int(cid))
            )
        reg_rows = self._session.execute(
            select(
                RegionSourceTokenAlias.normalized_token,
                RegionSourceTokenAlias.source_definition_id,
                RegionSourceTokenAlias.region_id,
            ).where(
                RegionSourceTokenAlias.normalized_token.in_(tokens),
                RegionSourceTokenAlias.status == "approved",
            )
        ).all()
        for nt, sid, rid in reg_rows:
            self._region_alias_rows.setdefault(str(nt), []).append(
                (int(sid) if sid is not None else None, int(rid))
            )

    def resolve_channel_from_source(
        self,
        raw: str | None,
        *,
        source_definition_id: int | None = None,
    ) -> tuple[int | None, str | None]:
        s = (raw or "").strip()
        if not s:
            return None, "blank"
        hit = self._channels_by_code.get(s.lower())
        if hit is not None:
            return hit, "catalog_match"
        nk = _norm_key(s)
        hit = self._channels_by_name_norm.get(nk)
        if hit is not None:
            return hit, "catalog_match"
        rows = self._channel_alias_rows.get(nk, [])
        if source_definition_id is not None:
            scoped = [r for r in rows if r[0] is None or r[0] == source_definition_id]
        else:
            scoped = rows
        cid, reason = _alias_channel_id_from_rows(scoped)
        if cid is not None:
            return cid, reason or "source_channel_token_alias"
        if reason == "conflicting_channel_token_aliases":
            return None, reason
        return None, "no_catalog_match"

    def resolve_region_from_source(
        self,
        raw: str | None,
        *,
        source_definition_id: int | None = None,
    ) -> tuple[int | None, str | None]:
        s = (raw or "").strip()
        if not s:
            return None, "blank"
        hit = self._regions_by_code.get(s.lower())
        if hit is not None:
            return hit, None
        nk = _norm_key(s)
        hit = self._regions_by_name_norm.get(nk)
        if hit is not None:
            return hit, None
        rows = self._region_alias_rows.get(nk, [])
        if source_definition_id is not None:
            scoped = [r for r in rows if r[0] is None or r[0] == source_definition_id]
        else:
            scoped = rows
        rid, reason = _alias_region_id_from_rows(scoped)
        if rid is not None:
            return rid, reason or "source_region_token_alias"
        if reason == "conflicting_region_token_aliases":
            return None, reason
        return None, "no_catalog_match"


def resolve_source_geo_from_ctx_cached(
    cache: DSIGeoResolutionCache,
    ctx: dict[str, Any],
    *,
    source_definition_id: int | None = None,
) -> dict[str, Any]:
    """Same contract as ``_resolve_source_geo_from_ctx`` but uses a preloaded cache."""
    reg_conflict = bool(ctx.get("provisional_region_conflict"))
    ch_conflict = bool(ctx.get("provisional_channel_conflict"))
    out: dict[str, Any] = {
        "source_region_resolved_id": None,
        "source_channel_resolved_id": None,
        "provisional_region_conflict": reg_conflict,
        "provisional_channel_conflict": ch_conflict,
        "source_region_resolution_detail": None,
        "source_channel_resolution_detail": None,
        "source_region_raw_token": None,
        "source_channel_raw_token": None,
    }
    reg_norms = [n for n in (ctx.get("source_region_evidence_norms") or []) if isinstance(n, str) and n.strip()]
    ch_norms = [n for n in (ctx.get("source_channel_evidence_norms") or []) if isinstance(n, str) and n.strip()]
    reg_samples = ctx.get("source_region_raw_samples") or []
    ch_samples = ctx.get("source_channel_raw_samples") or []

    if reg_conflict:
        out["source_region_resolution_detail"] = "conflicting_source_evidence"
    else:
        uniq_r = sorted(set(reg_norms))
        if len(uniq_r) == 1:
            raw_pick = _pick_raw_for_norm(reg_samples if isinstance(reg_samples, list) else [], uniq_r[0])
            if raw_pick:
                out["source_region_raw_token"] = str(raw_pick).strip()[:512]
            rid, reason = cache.resolve_region_from_source(raw_pick, source_definition_id=source_definition_id)
            out["source_region_resolved_id"] = rid
            if rid is None:
                out["source_region_resolution_detail"] = reason or "unresolved"
            else:
                out["source_region_resolution_detail"] = "catalog_match" if reason is None else reason
        elif len(uniq_r) == 0:
            out["source_region_resolution_detail"] = "missing_source_evidence"

    if ch_conflict:
        out["source_channel_resolution_detail"] = "conflicting_source_evidence"
    else:
        uniq_c = sorted(set(ch_norms))
        if len(uniq_c) == 1:
            raw_pick_c = _pick_raw_for_norm(ch_samples if isinstance(ch_samples, list) else [], uniq_c[0])
            if raw_pick_c:
                out["source_channel_raw_token"] = str(raw_pick_c).strip()[:512]
            cid, reason_c = cache.resolve_channel_from_source(raw_pick_c, source_definition_id=source_definition_id)
            out["source_channel_resolved_id"] = cid
            if cid is None:
                out["source_channel_resolution_detail"] = reason_c or "unresolved"
            else:
                out["source_channel_resolution_detail"] = reason_c or "catalog_match"
        elif len(uniq_c) == 0:
            out["source_channel_resolution_detail"] = "missing_source_evidence"

    return out


def collect_geo_tokens_from_candidates(
    candidates: list[Any],
    job: ImportJob,
) -> set[str]:
    """Gather normalized channel/region evidence tokens for alias preload."""
    tokens: set[str] = set()
    for cand in candidates:
        ctx = cand.context if isinstance(cand.context, dict) else {}
        for n in ctx.get("source_region_evidence_norms") or []:
            if isinstance(n, str) and n.strip():
                tokens.add(_norm_key(n))
        for n in ctx.get("source_channel_evidence_norms") or []:
            if isinstance(n, str) and n.strip():
                tokens.add(_norm_key(n))
    return tokens
