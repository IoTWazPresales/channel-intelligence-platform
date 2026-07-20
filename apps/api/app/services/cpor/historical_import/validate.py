"""Validate parsed historical CPOR rows — parity, grain, collisions (H1)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase
from app.services.cpor.waterfall import (
    compute_line_waterfall,
    compute_support_unit,
    quantize_money,
)

PARITY_TOLERANCE = Decimal("0.02")


def _d(val: float | int | str | Decimal | None) -> Decimal | None:
    if val is None:
        return None
    return Decimal(str(val))


def parity_check_row(row: dict[str, Any]) -> list[str]:
    """Recompute from inputs; FLAG variance vs stored sheet totals. Never overwrite."""
    flags: list[str] = []
    channel = str(row.get("channel") or "reseller")
    srp = _d(row.get("srp"))
    vat = _d(row.get("vat_rate"))
    margin = _d(row.get("dealer_margin_pct"))
    cost = _d(row.get("cost_basis"))
    estimate = _d(row.get("estimate_qty")) or Decimal("0")
    result = _d(row.get("result_qty"))
    roe = _d(row.get("roe_snapshot"))
    stored_support = _d(row.get("support_unit"))
    stored_ttl_result = _d(row.get("ttl_result"))

    if srp is None or vat is None or margin is None:
        flags.append("parity_skipped_missing_inputs")
        return flags

    if channel == "reseller":
        computed = compute_line_waterfall(
            srp=srp,
            vat_rate=vat,
            dealer_margin_pct=margin,
            cost_basis=cost,
            estimate_qty=estimate,
            result_qty=result,
            case_roe=roe,
            channel="reseller",
        )
        if stored_support is not None and computed.get("support_unit") is not None:
            diff = abs(quantize_money(computed["support_unit"]) - quantize_money(stored_support))
            if diff > PARITY_TOLERANCE:
                flags.append("waterfall_parity_variance")
        if stored_ttl_result is not None and computed.get("ttl_result") is not None:
            diff = abs(quantize_money(computed["ttl_result"]) - quantize_money(stored_ttl_result))
            if diff > PARITY_TOLERANCE:
                flags.append("ttl_result_mismatch")
        return flags

    # Disti: compare support using imported dealer/disti price vs cost (no live disti engine).
    dealer_price = _d(row.get("dealer_price"))
    if cost is None or dealer_price is None:
        flags.append("parity_skipped_disti_missing_cost_or_price")
        return flags
    expected = compute_support_unit(cost, dealer_price)
    if stored_support is not None:
        diff = abs(quantize_money(expected) - quantize_money(stored_support))
        if diff > PARITY_TOLERANCE:
            flags.append("waterfall_parity_variance")
    return flags


def validate_parsed_rows(
    rows: list[dict[str, Any]],
    *,
    session: Session | None = None,
) -> dict[str, Any]:
    """Annotate rows with validation flags; summarize case-level blockers.

    When session provided: FLAG case_code collisions with origin='native' live cases.
    """
    annotated: list[dict[str, Any]] = []
    grain_seen: dict[str, list[int]] = defaultdict(list)
    case_roe: dict[str, set[str]] = defaultdict(set)
    case_blockers: dict[str, list[str]] = defaultdict(list)

    native_codes: set[str] = set()
    if session is not None:
        native_codes = {
            str(c).upper()
            for c in session.scalars(
                select(CporCase.case_code).where(CporCase.origin == "native")
            ).all()
        }

    for row in rows:
        r = dict(row)
        flags = list((r.get("flags_json") or {}).get("flags") or [])
        flags.extend(parity_check_row(r))

        case_code = str(r.get("case_code") or "").strip()
        grain = "|".join(
            [
                case_code.upper(),
                str(r.get("sales_model_token") or "").upper(),
                str(r.get("distributor_token") or "").upper(),
                str(r.get("pod_quarter") or "").upper(),
                str(r.get("channel") or ""),
            ]
        )
        grain_seen[grain].append(int(r.get("source_row_number") or 0))

        roe = r.get("roe_snapshot")
        if roe is not None:
            case_roe[case_code].add(str(roe))

        if case_code.upper() in native_codes:
            flags.append("case_code_collision_native")
            case_blockers[case_code].append("case_code_collision_native")

        if not r.get("window_start") or not r.get("window_end"):
            flags.append("missing_window")
        if not r.get("customer_token"):
            flags.append("missing_customer_token")
        if not r.get("sales_model_token"):
            flags.append("missing_product_token")

        r["flags_json"] = {"flags": sorted(set(flags))}
        annotated.append(r)

    duplicate_grains = {k: v for k, v in grain_seen.items() if len(v) > 1}
    # Note: workbook intentionally has multiple POD layers — grain includes pod_quarter,
    # so true duplicates are same layer twice. Flag those only.
    for grain, row_nums in duplicate_grains.items():
        case_code = grain.split("|", 1)[0]
        for row in annotated:
            g = "|".join(
                [
                    str(row.get("case_code") or "").upper(),
                    str(row.get("sales_model_token") or "").upper(),
                    str(row.get("distributor_token") or "").upper(),
                    str(row.get("pod_quarter") or "").upper(),
                    str(row.get("channel") or ""),
                ]
            )
            if g == grain:
                fl = list((row.get("flags_json") or {}).get("flags") or [])
                fl.append("duplicate_line_grain")
                row["flags_json"] = {"flags": sorted(set(fl))}
                case_blockers[case_code].append("duplicate_line_grain")

    for case_code, roes in case_roe.items():
        if len(roes) > 1:
            for row in annotated:
                if str(row.get("case_code") or "") == case_code:
                    fl = list((row.get("flags_json") or {}).get("flags") or [])
                    fl.append("roe_inconsistent")
                    row["flags_json"] = {"flags": sorted(set(fl))}

    apply_candidates = [r for r in annotated if not r.get("skip_apply")]
    return {
        "rows": annotated,
        "apply_candidate_count": len(apply_candidates),
        "skipped_count": len(annotated) - len(apply_candidates),
        "case_blockers": {k: sorted(set(v)) for k, v in case_blockers.items()},
        "cases": sorted({str(r.get("case_code")) for r in apply_candidates if r.get("case_code")}),
        "parity_variance_count": sum(
            1
            for r in annotated
            if "waterfall_parity_variance" in ((r.get("flags_json") or {}).get("flags") or [])
        ),
    }


def parse_and_validate_historical_workbook(
    data: bytes,
    *,
    profile: dict[str, Any] | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    from app.services.cpor.historical_import.parser import parse_historical_workbook

    parsed = parse_historical_workbook(data, profile=profile)
    if parsed.get("blocking_errors"):
        return {
            **parsed,
            "validation": None,
            "ok": False,
        }
    validation = validate_parsed_rows(parsed["rows"], session=session)
    return {
        **parsed,
        "rows": validation["rows"],
        "validation": validation,
        "ok": True,
    }
