"""Case-scoped manual customer/distributor resolution for current lineup rows.

Updates CommercialLineupLine.customer_id / distributor_id only.
Never touches cost fields, DAP evidence, or SKU assumptions.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.services.commercial_planner.lineup_open_channel import (
    CHANNEL_ROUTE_UPLOADED_CELL_KEY,
    extract_distributor_name_from_channel_customer_cell,
    lineup_line_is_open_channel_staging,
    managed_customer_token_unresolved,
)


from app.services.commercial_planner.lineup_case_status import RESOLUTION_ALLOWED_CASE_STATUSES


def normalize_entity_token(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def distributor_token_from_line(ln: CommercialLineupLine) -> str | None:
    payload = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else {}
    raw = payload.get("distributor_token")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def open_channel_distributor_hint_from_line(ln: CommercialLineupLine) -> str | None:
    """Distributor name parsed from an Open Channel route cell when distributor_token is absent."""
    if not lineup_line_is_open_channel_staging(ln):
        return None
    payload = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else {}
    for raw in (payload.get(CHANNEL_ROUTE_UPLOADED_CELL_KEY), payload.get("customer_token")):
        if raw is None:
            continue
        hint = extract_distributor_name_from_channel_customer_cell(str(raw))
        if hint:
            return hint
    return None


def distributor_resolution_token_from_line(ln: CommercialLineupLine) -> str | None:
    """Token used for steward distributor mapping (column token or open-channel route hint)."""
    return distributor_token_from_line(ln) or open_channel_distributor_hint_from_line(ln)


def _line_matches_distributor_token(ln: CommercialLineupLine, norm: str) -> bool:
    candidate = distributor_resolution_token_from_line(ln)
    return bool(candidate) and normalize_entity_token(candidate) == norm


def _dedupe_preserve_order(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def refresh_diagnostics_after_entity_update(ln: CommercialLineupLine) -> None:
    """Recompute parser-aligned diagnostic_codes; preserve prior manual resolution audit tags."""
    prev = list(ln.diagnostic_codes) if isinstance(ln.diagnostic_codes, list) else []
    manual = [x for x in prev if isinstance(x, str) and x.startswith("manual_case_resolution_")]
    codes: list[str] = []
    if ln.product_id is None:
        codes.append("unresolved_product")
    if managed_customer_token_unresolved(ln):
        codes.append("unknown_customer")
    dt = distributor_resolution_token_from_line(ln)
    if dt and ln.distributor_id is None:
        codes.append("unknown_distributor")
    codes.extend(manual)
    ln.diagnostic_codes = _dedupe_preserve_order(codes) if codes else None


def append_manual_resolution_tag(ln: CommercialLineupLine, tag: str) -> None:
    prev = list(ln.diagnostic_codes) if isinstance(ln.diagnostic_codes, list) else []
    if tag not in prev:
        prev.append(tag)
    ln.diagnostic_codes = _dedupe_preserve_order(prev) if prev else None


def _accumulate_line_entity_tokens(
    ln: CommercialLineupLine,
    case_id: int,
    *,
    customer_map: dict[str, dict[str, Any]],
    distributor_map: dict[str, dict[str, Any]],
    sample_ids_per_token: int,
) -> None:
    if ln.customer_id is None:
        if not lineup_line_is_open_channel_staging(ln):
            tok = normalize_entity_token(ln.customer_token)
            if tok:
                entry = customer_map.setdefault(
                    tok,
                    {
                        "token_display": (ln.customer_token or "").strip(),
                        "line_count": 0,
                        "case_ids": set(),
                        "sample_line_ids": [],
                    },
                )
                entry["line_count"] += 1
                entry["case_ids"].add(case_id)
                if len(entry["sample_line_ids"]) < sample_ids_per_token:
                    entry["sample_line_ids"].append(ln.id)
    if ln.distributor_id is None:
        raw_t = distributor_resolution_token_from_line(ln)
        tok = normalize_entity_token(raw_t)
        if tok:
            source = "open_channel_route" if open_channel_distributor_hint_from_line(ln) else "distributor_column"
            entry = distributor_map.setdefault(
                tok,
                {
                    "token_display": raw_t or "",
                    "line_count": 0,
                    "case_ids": set(),
                    "sample_line_ids": [],
                    "token_source": source,
                },
            )
            if source == "open_channel_route":
                entry["token_source"] = "open_channel_route"
            entry["line_count"] += 1
            entry["case_ids"].add(case_id)
            if len(entry["sample_line_ids"]) < sample_ids_per_token:
                entry["sample_line_ids"].append(ln.id)


def _serialize_token_map(token_map: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for k, v in sorted(token_map.items(), key=lambda x: (-x[1]["line_count"], x[0])):
        row: dict[str, Any] = {
            "token_norm": k,
            "token_display": v["token_display"],
            "line_count": v["line_count"],
            "case_ids": sorted(v.get("case_ids") or []),
            "case_count": len(v.get("case_ids") or []),
            "sample_line_ids": v["sample_line_ids"],
        }
        if v.get("token_source"):
            row["token_source"] = v["token_source"]
        out.append(row)
    return out


async def _eligible_case_ids(
    db: AsyncSession,
    *,
    plan_id: int | None = None,
    case_ids: list[int] | None = None,
) -> list[int]:
    stmt = select(CommercialLineupCase.id).where(
        CommercialLineupCase.commercial_status.in_(RESOLUTION_ALLOWED_CASE_STATUSES)
    )
    if plan_id is not None:
        stmt = stmt.where(CommercialLineupCase.commercial_plan_id == plan_id)
    if case_ids:
        stmt = stmt.where(CommercialLineupCase.id.in_(case_ids))
    rows = (await db.execute(stmt.order_by(CommercialLineupCase.id))).scalars().all()
    return [int(x) for x in rows]


async def collect_entity_resolution_candidates(
    db: AsyncSession,
    case_id: int,
    *,
    sample_ids_per_token: int = 5,
) -> dict[str, Any]:
    """Distinct unresolved customer/distributor tokens with counts and sample line ids."""
    result = await db.execute(select(CommercialLineupLine).where(CommercialLineupLine.case_id == case_id))
    lines = list(result.scalars().all())

    customer_map: dict[str, dict[str, Any]] = {}
    distributor_map: dict[str, dict[str, Any]] = {}

    for ln in lines:
        _accumulate_line_entity_tokens(
            ln,
            case_id,
            customer_map=customer_map,
            distributor_map=distributor_map,
            sample_ids_per_token=sample_ids_per_token,
        )

    return {
        "case_id": case_id,
        "customer_tokens": _serialize_token_map(customer_map),
        "distributor_tokens": _serialize_token_map(distributor_map),
    }


async def collect_plan_entity_resolution_candidates(
    db: AsyncSession,
    *,
    plan_id: int | None = None,
    case_ids: list[int] | None = None,
    sample_ids_per_token: int = 5,
) -> dict[str, Any]:
    """Aggregate unresolved entity tokens across all eligible lineup cases on a plan (or case id list)."""
    eligible_ids = await _eligible_case_ids(db, plan_id=plan_id, case_ids=case_ids)
    customer_map: dict[str, dict[str, Any]] = {}
    distributor_map: dict[str, dict[str, Any]] = {}

    if eligible_ids:
        lines = (
            await db.execute(
                select(CommercialLineupLine).where(CommercialLineupLine.case_id.in_(eligible_ids))
            )
        ).scalars().all()
        for ln in lines:
            _accumulate_line_entity_tokens(
                ln,
                int(ln.case_id),
                customer_map=customer_map,
                distributor_map=distributor_map,
                sample_ids_per_token=sample_ids_per_token,
            )

    customer_tokens = _serialize_token_map(customer_map)
    distributor_tokens = _serialize_token_map(distributor_map)
    token_count = len(customer_tokens) + len(distributor_tokens)

    return {
        "plan_id": plan_id,
        "eligible_case_ids": eligible_ids,
        "eligible_case_count": len(eligible_ids),
        "customer_tokens": customer_tokens,
        "distributor_tokens": distributor_tokens,
        "token_count": token_count,
    }


def _mark_open_channel_staging_for_token(lines: list[CommercialLineupLine], norm: str) -> int:
    updated = 0
    for ln in lines:
        if normalize_entity_token(ln.customer_token) != norm:
            continue
        if lineup_line_is_open_channel_staging(ln):
            continue
        p = dict(ln.raw_row_payload) if isinstance(ln.raw_row_payload, dict) else {}
        prior = (ln.customer_token or "").strip()
        if prior:
            aud = p.get("resolution_audit_customer_tokens_prior")
            if not isinstance(aud, list):
                aud = []
            aud.append(prior)
            p["resolution_audit_customer_tokens_prior"] = aud
        p["staging_open_channel"] = True
        ln.raw_row_payload = p
        ln.customer_token = None
        ln.customer_id = None
        refresh_diagnostics_after_entity_update(ln)
        append_manual_resolution_tag(ln, "manual_case_resolution_open_channel_staging")
        updated += 1
    return updated


def _map_customer_token_lines(lines: list[CommercialLineupLine], norm: str, dim_id: int) -> int:
    updated = 0
    for ln in lines:
        if normalize_entity_token(ln.customer_token) != norm:
            continue
        ln.customer_id = dim_id
        refresh_diagnostics_after_entity_update(ln)
        append_manual_resolution_tag(ln, "manual_case_resolution_customer")
        updated += 1
    return updated


def _map_distributor_token_lines(lines: list[CommercialLineupLine], norm: str, dim_id: int) -> int:
    updated = 0
    for ln in lines:
        if not _line_matches_distributor_token(ln, norm):
            continue
        ln.distributor_id = dim_id
        refresh_diagnostics_after_entity_update(ln)
        append_manual_resolution_tag(ln, "manual_case_resolution_distributor")
        updated += 1
    return updated


def _redirect_customer_token_to_distributor(lines: list[CommercialLineupLine], norm: str, dim_id: int) -> int:
    """Customer-column token actually names a distributor (explicit user action)."""
    updated = 0
    for ln in lines:
        if lineup_line_is_open_channel_staging(ln):
            continue
        if normalize_entity_token(ln.customer_token) != norm:
            continue
        ln.distributor_id = dim_id
        ln.customer_token = None
        ln.customer_id = None
        refresh_diagnostics_after_entity_update(ln)
        append_manual_resolution_tag(ln, "manual_case_resolution_customer_token_as_distributor")
        updated += 1
    return updated


def _redirect_distributor_token_to_customer(lines: list[CommercialLineupLine], norm: str, dim_id: int) -> int:
    """Distributor-column token actually names a customer (explicit user action)."""
    updated = 0
    for ln in lines:
        if not _line_matches_distributor_token(ln, norm):
            continue
        ln.customer_id = dim_id
        p = dict(ln.raw_row_payload) if isinstance(ln.raw_row_payload, dict) else {}
        prior = distributor_token_from_line(ln)
        if prior:
            aud = p.get("resolution_audit_distributor_tokens_prior")
            if not isinstance(aud, list):
                aud = []
            aud.append(prior)
            p["resolution_audit_distributor_tokens_prior"] = aud
        if "distributor_token" in p:
            p["distributor_token"] = None
        ln.raw_row_payload = p
        refresh_diagnostics_after_entity_update(ln)
        append_manual_resolution_tag(ln, "manual_case_resolution_distributor_token_as_customer")
        updated += 1
    return updated


async def apply_entity_resolutions(
    db: AsyncSession,
    case_id: int,
    resolutions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply token → dim mappings and explicit resolution actions. Idempotent per token batch."""
    result = await db.execute(select(CommercialLineupLine).where(CommercialLineupLine.case_id == case_id))
    lines = list(result.scalars().all())
    per: list[dict[str, Any]] = []
    total_updated = 0

    for item in resolutions:
        kind = item.get("kind")
        token = item.get("token")
        action = item.get("action") or "map_existing"
        if not isinstance(token, str) or not token.strip():
            continue
        norm = normalize_entity_token(token)
        if not norm:
            continue

        updated = 0
        dim_id = item.get("dim_id")

        if action == "mark_open_channel_staging":
            if kind != "customer":
                continue
            updated = _mark_open_channel_staging_for_token(lines, norm)
        elif action == "create_dim":
            if kind == "customer":
                code = str(item.get("new_code") or "").strip()[:64]
                name = str(item.get("new_name") or "").strip()[:256]
                if not code or not name:
                    continue
                row = DimCustomer(code=code, name=name, customer_status="active")
                db.add(row)
                await db.flush()
                dim_id = int(row.id)
                updated = _map_customer_token_lines(lines, norm, dim_id)
            elif kind == "distributor":
                code = str(item.get("new_code") or "").strip()[:32]
                name = str(item.get("new_name") or "").strip()[:256]
                if not code or not name:
                    continue
                row = DimDistributor(code=code, name=name)
                db.add(row)
                await db.flush()
                dim_id = int(row.id)
                updated = _map_distributor_token_lines(lines, norm, dim_id)
            else:
                continue
        else:
            if not isinstance(dim_id, int):
                continue
            if kind == "customer":
                updated = _map_customer_token_lines(lines, norm, dim_id)
            elif kind == "distributor":
                updated = _map_distributor_token_lines(lines, norm, dim_id)
            elif kind == "customer_token_as_distributor":
                updated = _redirect_customer_token_to_distributor(lines, norm, dim_id)
            elif kind == "distributor_token_as_customer":
                updated = _redirect_distributor_token_to_customer(lines, norm, dim_id)
            else:
                continue

        total_updated += updated
        entry: dict[str, Any] = {
            "kind": kind,
            "token": token.strip(),
            "action": action,
            "updated_lines": updated,
        }
        if dim_id is not None:
            entry["dim_id"] = dim_id
        per.append(entry)

    return {"case_id": case_id, "updated_lines": total_updated, "per_resolution": per}


async def apply_plan_entity_resolutions(
    db: AsyncSession,
    resolutions: list[dict[str, Any]],
    *,
    plan_id: int | None = None,
    case_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Apply the same resolution batch to every eligible case on a plan (or explicit case list)."""
    eligible_ids = await _eligible_case_ids(db, plan_id=plan_id, case_ids=case_ids)
    per_case: list[dict[str, Any]] = []
    total_updated = 0
    for case_id in eligible_ids:
        out = await apply_entity_resolutions(db, case_id, resolutions)
        if int(out.get("updated_lines") or 0) > 0:
            per_case.append(out)
        total_updated += int(out.get("updated_lines") or 0)
    return {
        "plan_id": plan_id,
        "eligible_case_ids": eligible_ids,
        "updated_lines": total_updated,
        "cases_updated": len(per_case),
        "per_case": per_case,
    }
