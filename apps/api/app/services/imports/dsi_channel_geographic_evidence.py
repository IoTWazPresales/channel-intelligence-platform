"""Aggregate channel file tokens that look like geographic hints (evidence visibility for stewards)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.import_distributor_si import ImportEntityMappingCandidate
from app.models.ingestion import ImportJob
from app.reference.iso3166_countries import resolve_alpha2_from_token
from app.services.imports.distributor_sales_inventory import _norm_key


def collect_dsi_channel_geographic_evidence_sync(session: Session, job_id: int) -> dict[str, Any]:
    """Channel tokens on this DSI job that triggered geographic-hint detection (not RTM mapping)."""
    job = session.get(ImportJob, int(job_id))
    if not job:
        raise ValueError("Import job not found")
    if (job.template_slug or "") != "distributor_inventory":
        raise ValueError("Job is not a distributor sales & inventory import")

    cands = list(
        session.scalars(
            select(ImportEntityMappingCandidate).where(
                ImportEntityMappingCandidate.import_job_id == int(job_id),
                ImportEntityMappingCandidate.entity_type == "customer_dealer_token",
            )
        ).all()
    )

    acc: dict[str, dict[str, Any]] = {}
    for cand in cands:
        ctx = cand.context if isinstance(cand.context, dict) else {}
        samples = ctx.get("source_channel_raw_samples") or []
        if not isinstance(samples, list):
            continue
        rc = int(cand.row_count or 0)
        cid = int(cand.id)
        seen_norm: set[str] = set()
        for raw in samples:
            if not isinstance(raw, str):
                continue
            rt = raw.strip()
            if not rt:
                continue
            iso = resolve_alpha2_from_token(rt)
            if not iso:
                continue
            nk = _norm_key(rt)
            if nk in seen_norm:
                continue
            seen_norm.add(nk)
            ent = acc.setdefault(
                nk,
                {
                    "normalized_token": nk,
                    "raw_token": rt[:512],
                    "guessed_region_code": iso,
                    "row_count": 0,
                    "customer_candidate_ids": [],
                },
            )
            ent["row_count"] += rc
            if cid not in ent["customer_candidate_ids"]:
                ent["customer_candidate_ids"].append(cid)

    channels = []
    for ent in acc.values():
        cids = sorted(set(ent["customer_candidate_ids"]))
        channels.append(
            {
                "normalized_token": ent["normalized_token"],
                "raw_token": ent["raw_token"],
                "guessed_region_code": ent["guessed_region_code"],
                "row_count": int(ent["row_count"]),
                "customer_candidate_count": len(cids),
                "customer_candidate_ids": cids,
            }
        )
    channels.sort(key=lambda x: (-int(x["row_count"]), x["normalized_token"]))

    return {"import_job_id": int(job_id), "channels": channels}
