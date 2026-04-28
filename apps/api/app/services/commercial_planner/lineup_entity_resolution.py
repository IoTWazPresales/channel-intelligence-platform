"""Case-scoped manual customer/distributor resolution for current lineup rows.

Updates CommercialLineupLine.customer_id / distributor_id only.
Never touches cost fields, DAP evidence, or SKU assumptions.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_lineup import CommercialLineupLine


RESOLUTION_ALLOWED_CASE_STATUSES: frozenset[str] = frozenset(
    {"draft_imported", "validated", "pending_review"}
)


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
    if (ln.customer_token or "").strip() and ln.customer_id is None:
        codes.append("unknown_customer")
    dt = distributor_token_from_line(ln)
    if dt and ln.distributor_id is None:
        codes.append("unknown_distributor")
    codes.extend(manual)
    ln.diagnostic_codes = _dedupe_preserve_order(codes) if codes else None


def append_manual_resolution_tag(ln: CommercialLineupLine, tag: str) -> None:
    prev = list(ln.diagnostic_codes) if isinstance(ln.diagnostic_codes, list) else []
    if tag not in prev:
        prev.append(tag)
    ln.diagnostic_codes = _dedupe_preserve_order(prev) if prev else None


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
        if ln.customer_id is None:
            tok = normalize_entity_token(ln.customer_token)
            if tok:
                entry = customer_map.setdefault(
                    tok,
                    {"token_display": (ln.customer_token or "").strip(), "line_count": 0, "sample_line_ids": []},
                )
                entry["line_count"] += 1
                if len(entry["sample_line_ids"]) < sample_ids_per_token:
                    entry["sample_line_ids"].append(ln.id)
        if ln.distributor_id is None:
            raw_t = distributor_token_from_line(ln)
            tok = normalize_entity_token(raw_t)
            if tok:
                entry = distributor_map.setdefault(
                    tok,
                    {"token_display": raw_t or "", "line_count": 0, "sample_line_ids": []},
                )
                entry["line_count"] += 1
                if len(entry["sample_line_ids"]) < sample_ids_per_token:
                    entry["sample_line_ids"].append(ln.id)

    return {
        "case_id": case_id,
        "customer_tokens": [
            {"token_norm": k, "token_display": v["token_display"], "line_count": v["line_count"], "sample_line_ids": v["sample_line_ids"]}
            for k, v in sorted(customer_map.items(), key=lambda x: (-x[1]["line_count"], x[0]))
        ],
        "distributor_tokens": [
            {"token_norm": k, "token_display": v["token_display"], "line_count": v["line_count"], "sample_line_ids": v["sample_line_ids"]}
            for k, v in sorted(distributor_map.items(), key=lambda x: (-x[1]["line_count"], x[0]))
        ],
    }


async def apply_entity_resolutions(
    db: AsyncSession,
    case_id: int,
    resolutions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply token → dim_id mappings for all matching lines in the case. Idempotent."""
    result = await db.execute(select(CommercialLineupLine).where(CommercialLineupLine.case_id == case_id))
    lines = list(result.scalars().all())
    per: list[dict[str, Any]] = []
    total_updated = 0

    for item in resolutions:
        kind = item.get("kind")
        token = item.get("token")
        dim_id = item.get("dim_id")
        if kind not in ("customer", "distributor"):
            continue
        if not isinstance(token, str) or not token.strip():
            continue
        if not isinstance(dim_id, int):
            continue
        norm = normalize_entity_token(token)
        if not norm:
            continue

        updated = 0
        if kind == "customer":
            for ln in lines:
                if normalize_entity_token(ln.customer_token) != norm:
                    continue
                ln.customer_id = dim_id
                refresh_diagnostics_after_entity_update(ln)
                append_manual_resolution_tag(ln, "manual_case_resolution_customer")
                updated += 1
        else:
            for ln in lines:
                if normalize_entity_token(distributor_token_from_line(ln)) != norm:
                    continue
                ln.distributor_id = dim_id
                refresh_diagnostics_after_entity_update(ln)
                append_manual_resolution_tag(ln, "manual_case_resolution_distributor")
                updated += 1

        total_updated += updated
        per.append({"kind": kind, "token": token.strip(), "dim_id": dim_id, "updated_lines": updated})

    return {"case_id": case_id, "updated_lines": total_updated, "per_resolution": per}
