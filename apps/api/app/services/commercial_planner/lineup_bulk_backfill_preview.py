"""Bulk historical lineup backfill — file-grain preview engine (Spec C Step B).

Preview-only: no writes to ``commercial_lineup_case`` / lines. Produces steward review
payloads (period/BU/sheet fan-out, collisions, catalogue-miss worklist) for batch apply.
"""
from __future__ import annotations

import asyncio
import base64
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCustomer, DimProduct
from app.services.commercial_planner.lineup_half_year_quantity import (
    HALF_YEAR_ALLOCATION_FLAG,
    half_year_allocation_summary,
)
from app.services.commercial_planner.lineup_bulk_period_inference import (
    resolve_layered_period,
    scan_title_band_from_workbook_rows,
)
from app.services.commercial_planner.lineup_business_unit_resolution import (
    LineupRowProductTokens,
    load_business_unit_by_product_id,
    resolve_lineup_business_unit,
)
from app.services.imports.distributor_sales_inventory import ProductResolutionIndex
from app.services.imports.historical_lineup import parse_historical_workbook
from app.services.imports.product_resolution_index_cache import get_product_resolution_index

BULK_TEMPLATE_SLUG = "bulk_lineup_backfill"
BULK_SOURCE_CODE = "bulk_lineup_backfill_system"


@dataclass
class BulkFileInput:
    filename: str
    file_bytes: bytes
    folder_path: str | None = None
    source_absolute_path: str | None = None


@dataclass
class CaseProposal:
    proposal_key: str
    file_key: str
    filename: str
    folder_path: str | None
    sheet_name: str
    period_label: str | None
    period_start: str | None
    period_source_tier: str | None
    period_flags: list[str]
    business_unit: str | None
    bu_report: dict[str, Any]
    customer_token: str | None
    customer_id: int | None
    row_count: int
    resolved_product_count: int
    unresolved_product_count: int
    status: str  # ready | needs_attention | excluded
    attention_reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    supersession_group_key: str | None = None
    allocation_summary: dict[str, Any] | None = None
    slice_source_rows: list[int] | None = None

    def to_dict(self) -> dict[str, Any]:
        out = {
            "proposal_key": self.proposal_key,
            "file_key": self.file_key,
            "filename": self.filename,
            "folder_path": self.folder_path,
            "sheet_name": self.sheet_name,
            "period_label": self.period_label,
            "period_start": self.period_start,
            "period_source_tier": self.period_source_tier,
            "period_flags": self.period_flags,
            "business_unit": self.business_unit,
            "bu_report": self.bu_report,
            "customer_token": self.customer_token,
            "customer_id": self.customer_id,
            "row_count": self.row_count,
            "resolved_product_count": self.resolved_product_count,
            "unresolved_product_count": self.unresolved_product_count,
            "status": self.status,
            "attention_reasons": self.attention_reasons,
            "flags": self.flags,
            "supersession_group_key": self.supersession_group_key,
            "allocation_summary": self.allocation_summary,
        }
        if self.slice_source_rows is not None:
            out["slice_source_rows"] = list(self.slice_source_rows)
        return out


def _sum_row_quantities(rows: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in rows:
        q = row.get("quantity_units")
        if q is not None:
            try:
                total += float(q)
            except (TypeError, ValueError):
                pass
    return total


def _half_year_split_half(period_flags: list[str]) -> str | None:
    if "period_half_split_q1" in period_flags:
        return "q1"
    if "period_half_split_q2" in period_flags:
        return "q2"
    return None


def _norm_customer_token(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def _majority_customer(
    rows: list[dict[str, Any]],
    customer_map: dict[str, DimCustomer],
) -> tuple[str | None, int | None]:
    counts: dict[str, int] = {}
    for row in rows:
        tok = _clean_token(row.get("customer_token"))
        if tok:
            counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        return None, None
    winner = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0]
    cust = customer_map.get(winner.lower()) or customer_map.get(_norm_customer_token(winner))
    return winner, int(cust.id) if cust else None


def _clean_token(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s and s.lower() not in ("nan", "none") else None


def _rows_to_product_tokens(rows: list[dict[str, Any]]) -> list[LineupRowProductTokens]:
    out: list[LineupRowProductTokens] = []
    for row in rows:
        out.append(
            LineupRowProductTokens(
                sku_raw=_clean_token(row.get("sku_raw")),
                part_number_raw=_clean_token(row.get("part_number_raw")),
                model_raw=_clean_token(row.get("model_raw")),
            )
        )
    return out


def _load_product_index_sync() -> ProductResolutionIndex:
    from app.db.session_sync import SessionLocal
    from app.services.imports.product_resolution_index_cache import get_product_resolution_index

    with SessionLocal() as session:
        return get_product_resolution_index(session)


def _resolve_rows_products(
    rows: list[dict[str, Any]],
    index: ProductResolutionIndex,
) -> tuple[int, int, list[dict[str, Any]]]:
    from app.services.commercial_planner.lineup_business_unit_resolution import resolve_row_product_id

    resolved = 0
    unresolved = 0
    catalogue_misses: list[dict[str, Any]] = []
    for row in rows:
        tokens = LineupRowProductTokens(
            sku_raw=_clean_token(row.get("sku_raw")),
            part_number_raw=_clean_token(row.get("part_number_raw")),
            model_raw=_clean_token(row.get("model_raw")),
        )
        pid = resolve_row_product_id(index, tokens)
        if pid is not None:
            resolved += 1
        else:
            unresolved += 1
            for field_name, raw in (
                ("sku_raw", tokens.sku_raw),
                ("part_number_raw", tokens.part_number_raw),
                ("model_raw", tokens.model_raw),
            ):
                if raw:
                    catalogue_misses.append(
                        {
                            "token": raw,
                            "field": field_name,
                            "sales_model_name": tokens.model_raw,
                        }
                    )
    return resolved, unresolved, catalogue_misses


def _split_rows_by_bu(
    rows: list[dict[str, Any]],
    index: ProductResolutionIndex,
    bu_by_pid: dict[int, str],
) -> dict[str, list[dict[str, Any]]]:
    from app.services.commercial_planner.lineup_business_unit_resolution import resolve_row_product_id

    buckets: dict[str, list[dict[str, Any]]] = {}
    unassigned: list[dict[str, Any]] = []
    for row in rows:
        tokens = LineupRowProductTokens(
            sku_raw=_clean_token(row.get("sku_raw")),
            part_number_raw=_clean_token(row.get("part_number_raw")),
            model_raw=_clean_token(row.get("model_raw")),
        )
        pid = resolve_row_product_id(index, tokens)
        bu = bu_by_pid.get(int(pid)) if pid is not None else None
        if bu:
            buckets.setdefault(bu, []).append(row)
        else:
            unassigned.append(row)
    if unassigned:
        buckets.setdefault("_unresolved", unassigned)
    return buckets


def _workbook_title_rows(file_bytes: bytes, sheet_name: str) -> list[list[Any]]:
    try:
        frame = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=None, nrows=8)
        return [list(frame.iloc[i].values) for i in range(min(8, len(frame)))]
    except Exception:
        return []


from app.services.commercial_planner.lineup_period_canonical import supersession_group_key_from_period_start
from app.services.commercial_planner.lineup_bulk_slice_rows import (
    load_lineup_parser_context_sync,
    parser_row_dicts_for_sheet,
    row_match_key,
)


def _content_identity_key(row: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """Product+qty identity for cross-sheet subset checks (customer omitted — open-channel nulling)."""
    sku, part, model, _cust, qty = row_match_key(row)
    return (sku, part, model, qty)


def _sheet_content_keys(rows: list[dict[str, Any]]) -> set[tuple[str | None, str | None, str | None, str | None]]:
    return {_content_identity_key(r) for r in rows}


def _subset_sheet_targets(
    sheet_keys: dict[str, set[tuple[str | None, str | None, str | None, str | None]]],
) -> dict[str, str]:
    """Map sheet_name → covering sheet when content is a non-empty proper/equal subset of another."""
    ignored: dict[str, str] = {}
    names = list(sheet_keys.keys())
    for name in names:
        keys = sheet_keys[name]
        if not keys:
            continue
        for other in names:
            if other == name:
                continue
            other_keys = sheet_keys[other]
            if not other_keys:
                continue
            # Prefer ignoring the smaller / secondary sheet when it is ⊆ a larger sibling.
            if keys <= other_keys and (
                len(keys) < len(other_keys)
                or (len(keys) == len(other_keys) and name.lower() == "sheet1")
            ):
                ignored[name] = other
                break
    return ignored


def build_case_proposals_for_file(
    file_key: str,
    spec: BulkFileInput,
    *,
    product_index: ProductResolutionIndex,
    business_unit_by_product_id: dict[int, str],
    customer_map: dict[str, DimCustomer],
    manual_period_label: str | None = None,
    manual_business_unit: str | None = None,
    tenant_bu_codes: frozenset[str] | None = None,
    manual_overrides: dict[str, Any] | None = None,
    parser_ctx: dict[str, Any] | None = None,
) -> tuple[list[CaseProposal], list[dict[str, Any]], dict[str, Any]]:
    """Parse one workbook into case proposals + per-file catalogue misses."""
    parsed_sheets, schema = parse_historical_workbook(spec.filename, spec.file_bytes)
    file_report: dict[str, Any] = {
        "file_key": file_key,
        "filename": spec.filename,
        "folder_path": spec.folder_path,
        "source_absolute_path": spec.source_absolute_path,
        "schema": schema,
    }
    proposals: list[CaseProposal] = []
    catalogue_misses: list[dict[str, Any]] = []
    parser_rows_by_sheet: dict[str, list[dict[str, Any]]] = {}

    def _parser_rows(sheet_name: str) -> list[dict[str, Any]]:
        if sheet_name not in parser_rows_by_sheet:
            if not parser_ctx:
                parser_rows_by_sheet[sheet_name] = []
            else:
                parser_rows_by_sheet[sheet_name] = parser_row_dicts_for_sheet(
                    spec.filename,
                    spec.file_bytes,
                    sheet_name=sheet_name,
                    parser_ctx=parser_ctx,
                )
        return parser_rows_by_sheet[sheet_name]

    if not parsed_sheets:
        proposals.append(
            CaseProposal(
                proposal_key=f"{file_key}:none",
                file_key=file_key,
                filename=spec.filename,
                folder_path=spec.folder_path,
                sheet_name="",
                period_label=None,
                period_start=None,
                period_source_tier=None,
                period_flags=["no_parseable_sheet"],
                business_unit=None,
                bu_report={},
                customer_token=None,
                customer_id=None,
                row_count=0,
                resolved_product_count=0,
                unresolved_product_count=0,
                status="needs_attention",
                attention_reasons=["no_parseable_sheet"],
                flags=["header_not_located"],
            )
        )
        return proposals, catalogue_misses, file_report

    # D-034: identity rows come from the apply parser (#2). Preload once for subset detection.
    for sheet in parsed_sheets:
        if parser_ctx:
            _parser_rows(sheet.sheet_name)

    subset_of = _subset_sheet_targets(
        {
            sheet.sheet_name: _sheet_content_keys(parser_rows_by_sheet.get(sheet.sheet_name) or [])
            for sheet in parsed_sheets
        }
    )

    for sheet in parsed_sheets:
        covering = subset_of.get(sheet.sheet_name)
        if covering:
            # Warren 2026-08-05 Unit3: ignore Sheet1 when content ⊆ primary sheet (no double-count).
            proposals.append(
                CaseProposal(
                    proposal_key=f"{file_key}:{sheet.sheet_name}:ignored:subset",
                    file_key=file_key,
                    filename=spec.filename,
                    folder_path=spec.folder_path,
                    sheet_name=sheet.sheet_name,
                    period_label=None,
                    period_start=None,
                    period_source_tier=None,
                    period_flags=[],
                    business_unit=None,
                    bu_report={},
                    customer_token=None,
                    customer_id=None,
                    row_count=0,
                    resolved_product_count=0,
                    unresolved_product_count=0,
                    status="excluded",
                    attention_reasons=[f"sheet_content_subset_of:{covering}"],
                    flags=["sheet_content_subset_ignored"],
                )
            )
            file_report.setdefault("sheets", []).append(
                {
                    "sheet_name": sheet.sheet_name,
                    "ignored_subset_of": covering,
                    "status": "excluded",
                }
            )
            continue

        accepted = [r for r in sheet.rows if r.status != "dropped"]
        # Parser #1 payloads remain for period/title/schema context only when #2 is absent.
        parser2 = _parser_rows(sheet.sheet_name) if parser_ctx else []
        identity_rows: list[dict[str, Any]] = parser2 if parser2 else [r.payload for r in accepted]
        title_band = scan_title_band_from_workbook_rows(_workbook_title_rows(spec.file_bytes, sheet.sheet_name))
        period_assignments, period_report = resolve_layered_period(
            folder_path=spec.folder_path,
            filename=spec.filename,
            title_band=title_band,
            manual_period_label=manual_period_label,
        )

        resolved_n, unresolved_n, misses = _resolve_rows_products(identity_rows, product_index)
        for m in misses:
            catalogue_misses.append(
                {
                    **m,
                    "filename": spec.filename,
                    "folder_path": spec.folder_path,
                    "sheet_name": sheet.sheet_name,
                }
            )

        bu_report = resolve_lineup_business_unit(
            rows=_rows_to_product_tokens(identity_rows),
            product_index=product_index,
            business_unit_by_product_id=business_unit_by_product_id,
            sheet_name=sheet.sheet_name,
            folder_path=spec.folder_path,
            manual_business_unit=manual_business_unit,
            tenant_bu_codes=tenant_bu_codes,
        )
        bu_dict = bu_report.to_dict()
        sheet_bu_flags = list(bu_dict.get("flags") or [])

        attention: list[str] = []
        status = "ready"
        if "bu_likely_not_lineup" in bu_report.flags:
            status = "needs_attention"
            attention.append("bu_likely_not_lineup")
        if sheet.header_row_number is None:
            attention.append("header_not_located")
        if "period_signal_conflict" in (period_assignments[0].flags if period_assignments else []):
            status = "needs_attention"
            attention.append("period_signal_conflict")
        if not identity_rows:
            status = "needs_attention"
            attention.append("empty_sheet")

        cust_token, cust_id = _majority_customer(identity_rows, customer_map)

        row_groups: list[tuple[str, list[dict[str, Any]]]] = []
        if "bu_multi_bu_in_sheet" in bu_report.flags and not manual_business_unit:
            buckets = _split_rows_by_bu(identity_rows, product_index, business_unit_by_product_id)
            for bu_key, group_rows in buckets.items():
                if bu_key == "_unresolved":
                    row_groups.append(("_unresolved", group_rows))
                else:
                    row_groups.append((bu_key, group_rows))
        else:
            row_groups.append((bu_report.business_unit or sheet.sheet_name, identity_rows))

        for bu_slice, slice_rows in row_groups:
            slice_resolved, slice_unresolved, _ = _resolve_rows_products(slice_rows, product_index)
            slice_bu_report = resolve_lineup_business_unit(
                rows=_rows_to_product_tokens(slice_rows),
                product_index=product_index,
                business_unit_by_product_id=business_unit_by_product_id,
                sheet_name=sheet.sheet_name,
                folder_path=spec.folder_path,
                manual_business_unit=manual_business_unit or (
                    bu_slice if bu_slice not in ("_unresolved", sheet.sheet_name) else None
                ),
                tenant_bu_codes=tenant_bu_codes,
            )
            half_split_active = any(
                "period_scope=1h_split" in (p.flags or []) for p in period_assignments
            )
            source_total_units = _sum_row_quantities(slice_rows) if half_split_active else 0.0
            file_allocation_summary = (
                half_year_allocation_summary(source_total_units) if half_split_active else None
            )

            for period in period_assignments:
                pk = f"{file_key}:{sheet.sheet_name}:{bu_slice}:{period.period_label or 'unknown'}"
                pk_over = (manual_overrides or {}).get(pk) or {}
                effective_period = period
                if pk_over.get("period_label"):
                    ov_assignments, _ = resolve_layered_period(
                        folder_path=spec.folder_path,
                        filename=spec.filename,
                        title_band=title_band,
                        manual_period_label=str(pk_over["period_label"]),
                    )
                    if ov_assignments:
                        effective_period = ov_assignments[0]

                effective_bu_report = slice_bu_report
                manual_bu = pk_over.get("business_unit") or manual_business_unit
                if manual_bu or pk_over.get("business_unit"):
                    effective_bu_report = resolve_lineup_business_unit(
                        rows=_rows_to_product_tokens(slice_rows),
                        product_index=product_index,
                        business_unit_by_product_id=business_unit_by_product_id,
                        sheet_name=sheet.sheet_name,
                        folder_path=spec.folder_path,
                        manual_business_unit=str(manual_bu) if manual_bu else None,
                        tenant_bu_codes=tenant_bu_codes,
                    )

                flags = list(effective_bu_report.flags) + list(effective_period.flags) + [
                    f for f in sheet_bu_flags if f not in effective_bu_report.flags
                ]
                if pk_over:
                    flags.append("steward_manual_override")
                alloc_summary = None
                if _half_year_split_half(list(effective_period.flags)) and file_allocation_summary:
                    alloc_summary = dict(file_allocation_summary)
                    if HALF_YEAR_ALLOCATION_FLAG not in flags:
                        flags.append(HALF_YEAR_ALLOCATION_FLAG)
                prop_status = status
                prop_attention = list(attention)
                if prop_status == "ready" and "period_unknown" in effective_period.flags:
                    prop_status = "needs_attention"
                    prop_attention.append("period_unknown")

                # D-034: native source_row_number from apply-parser rows — never cross-parser align.
                slice_source_rows: list[int] | None = None
                if len(row_groups) > 1 and parser2:
                    missing_nums = [r for r in slice_rows if r.get("source_row_number") is None]
                    if missing_nums:
                        prop_status = "needs_attention"
                        prop_attention.append("slice_row_missing_source_row_number")
                    else:
                        slice_source_rows = sorted(int(r["source_row_number"]) for r in slice_rows)
                if bu_slice == "_unresolved":
                    prop_status = "needs_attention"
                    if "slice_row_unclassified_bu" not in prop_attention:
                        prop_attention.append("slice_row_unclassified_bu")

                sgk = supersession_group_key_from_period_start(
                    effective_period.period_start.isoformat() if effective_period.period_start else None,
                    customer_id=cust_id,
                    customer_token=cust_token,
                    business_unit=effective_bu_report.business_unit,
                    normalize_customer_token=_norm_customer_token,
                )
                proposals.append(
                    CaseProposal(
                        proposal_key=pk,
                        file_key=file_key,
                        filename=spec.filename,
                        folder_path=spec.folder_path,
                        sheet_name=sheet.sheet_name,
                        period_label=effective_period.period_label,
                        period_start=effective_period.period_start.isoformat() if effective_period.period_start else None,
                        period_source_tier=effective_period.source_tier if not pk_over.get("period_label") else "manual",
                        period_flags=list(effective_period.flags),
                        business_unit=effective_bu_report.business_unit if bu_slice != "_unresolved" else None,
                        bu_report=effective_bu_report.to_dict(),
                        customer_token=cust_token,
                        customer_id=cust_id,
                        row_count=len(slice_rows),
                        resolved_product_count=slice_resolved,
                        unresolved_product_count=slice_unresolved,
                        status=prop_status,
                        attention_reasons=prop_attention,
                        flags=flags,
                        supersession_group_key=sgk,
                        allocation_summary=alloc_summary,
                        slice_source_rows=slice_source_rows,
                    )
                )

        file_report.setdefault("sheets", []).append(
            {
                "sheet_name": sheet.sheet_name,
                "title_band": title_band,
                "period_report": period_report,
                "bu_report": bu_dict,
                "header_row_number": sheet.header_row_number,
                "identity_row_count": len(identity_rows),
                "identity_source": "parser2" if parser2 else "parser1",
            }
        )

    return proposals, catalogue_misses, file_report


def detect_supersession_collisions(proposals: list[CaseProposal]) -> list[dict[str, Any]]:
    """Group ready proposals that share (period, customer, BU). Latest file wins on apply order."""
    groups: dict[str, list[CaseProposal]] = {}
    for p in proposals:
        if p.status != "ready" or not p.supersession_group_key:
            continue
        groups.setdefault(p.supersession_group_key, []).append(p)

    collisions: list[dict[str, Any]] = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda m: (m.filename, m.sheet_name))
        winner = ordered[-1]
        collisions.append(
            {
                "supersession_group_key": key,
                "period_label": winner.period_label,
                "customer_token": winner.customer_token,
                "customer_id": winner.customer_id,
                "business_unit": winner.business_unit,
                "member_count": len(members),
                "winner_proposal_key": winner.proposal_key,
                "members": [
                    {
                        "proposal_key": m.proposal_key,
                        "filename": m.filename,
                        "sheet_name": m.sheet_name,
                        "row_count": m.row_count,
                        "is_winner": m.proposal_key == winner.proposal_key,
                    }
                    for m in ordered
                ],
            }
        )
    return collisions


def _sheet_from_case_notes(notes: str | None) -> str | None:
    if not notes:
        return None
    m = re.match(r"sheet=([^;]+);", str(notes))
    return m.group(1).strip() if m else None


def existing_case_sheet_matches_proposal(notes: str | None, proposal_sheet: str | None) -> bool:
    """True when notes encode the same sheet, or notes have no sheet (wildcard).

    BACKLOG-104: ``notes`` NULL / missing ``sheet=`` must still collide with
    ready proposals that use ``Sheet1`` / ``NB`` so po_issued survivors surface.
    """
    sheet = _sheet_from_case_notes(notes)
    if sheet is None:
        return True
    return sheet == proposal_sheet


async def detect_existing_case_collisions(
    db: AsyncSession,
    proposals: list[CaseProposal],
) -> list[dict[str, Any]]:
    """Surface active DB cases that match a ready proposal's (file, sheet, BU, period)."""
    from datetime import date as date_cls

    from app.models.commercial_lineup import CommercialLineupCase
    from app.services.commercial_planner.lineup_period_canonical import active_lineup_case_filters

    collisions: list[dict[str, Any]] = []
    seen_group_keys: set[str] = set()

    for prop in proposals:
        if prop.status != "ready" or not prop.period_start or not prop.business_unit:
            continue
        try:
            ps = date_cls.fromisoformat(str(prop.period_start)[:10])
        except ValueError:
            continue

        stmt = (
            select(CommercialLineupCase)
            .where(
                *active_lineup_case_filters(),
                CommercialLineupCase.file_name == prop.filename,
                CommercialLineupCase.business_unit == prop.business_unit,
                CommercialLineupCase.inferred_period_start == ps,
            )
            .order_by(CommercialLineupCase.id)
        )
        existing_cases = (await db.execute(stmt)).scalars().all()
        for existing in existing_cases:
            if not existing_case_sheet_matches_proposal(existing.notes, prop.sheet_name):
                continue
            gkey = f"existing_case:{existing.id}:{prop.proposal_key}"
            if gkey in seen_group_keys:
                continue
            seen_group_keys.add(gkey)
            winner_key = f"existing:{existing.id}"
            existing_sheet = _sheet_from_case_notes(existing.notes)
            collisions.append(
                {
                    "collision_group_key": gkey,
                    "file_name": prop.filename,
                    "sheet_name": prop.sheet_name,
                    "business_unit": prop.business_unit,
                    "period_start": prop.period_start,
                    "period_label": prop.period_label,
                    "winner_member_key": winner_key,
                    "members": [
                        {
                            "kind": "existing_case",
                            "member_key": winner_key,
                            "case_id": int(existing.id),
                            "file_name": existing.file_name,
                            "sheet_name": existing_sheet,
                            "business_unit": existing.business_unit,
                            "period_label": existing.period_label,
                            "is_winner": True,
                        },
                        {
                            "kind": "proposed_case",
                            "member_key": prop.proposal_key,
                            "proposal_key": prop.proposal_key,
                            "file_name": prop.filename,
                            "sheet_name": prop.sheet_name,
                            "row_count": prop.row_count,
                            "is_winner": False,
                        },
                    ],
                }
            )
    return collisions


def aggregate_catalogue_miss_worklist(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """De-dupe catalogue-miss tokens with referencing evidence (advisory)."""
    by_token: dict[str, dict[str, Any]] = {}
    for e in entries:
        tok = str(e.get("token") or "").strip().lower()
        if not tok:
            continue
        item = by_token.setdefault(
            tok,
            {
                "token": e.get("token"),
                "field": e.get("field"),
                "reference_count": 0,
                "references": [],
            },
        )
        item["reference_count"] += 1
        item["references"].append(
            {
                "filename": e.get("filename"),
                "folder_path": e.get("folder_path"),
                "sheet_name": e.get("sheet_name"),
                "field": e.get("field"),
            }
        )
    return sorted(by_token.values(), key=lambda x: (-int(x["reference_count"]), str(x["token"])))


async def build_bulk_lineup_preview(
    db: AsyncSession,
    files: list[BulkFileInput],
    *,
    manual_overrides: dict[str, Any] | None = None,
    tenant_bu_codes: frozenset[str] | None = None,
    include_file_manifest_b64: bool = True,
) -> dict[str, Any]:
    """Build full file-grain preview (no lineup table writes)."""
    product_index = await asyncio.to_thread(_load_product_index_sync)
    bu_by_pid = await load_business_unit_by_product_id(db)
    parser_ctx = await asyncio.to_thread(load_lineup_parser_context_sync)

    customers = (await db.execute(select(DimCustomer))).scalars().all()
    from app.services.merge_redirect import index_by_code_and_name

    customer_map = index_by_code_and_name(list(customers), merged_into_attr="merged_into_customer_id")

    overrides = manual_overrides or {}
    all_proposals: list[CaseProposal] = []
    all_misses: list[dict[str, Any]] = []
    file_reports: list[dict[str, Any]] = []
    file_manifest: list[dict[str, Any]] = []

    for idx, spec in enumerate(files):
        file_key = f"f{idx}"
        file_manifest.append(
            {
                "file_key": file_key,
                "filename": spec.filename,
                "folder_path": spec.folder_path,
                "source_absolute_path": spec.source_absolute_path,
                "size_bytes": len(spec.file_bytes),
                **(
                    {"b64": base64.standard_b64encode(spec.file_bytes).decode("ascii")}
                    if include_file_manifest_b64
                    else {}
                ),
            }
        )
        fo = overrides.get(file_key) or overrides.get(spec.filename) or {}
        proposals, misses, frep = build_case_proposals_for_file(
            file_key,
            spec,
            product_index=product_index,
            business_unit_by_product_id=bu_by_pid,
            customer_map=customer_map,
            manual_period_label=fo.get("period_label"),
            manual_business_unit=fo.get("business_unit"),
            tenant_bu_codes=tenant_bu_codes,
            manual_overrides=overrides,
            parser_ctx=parser_ctx,
        )
        all_proposals.extend(proposals)
        all_misses.extend(misses)
        file_reports.append(frep)

    collisions = detect_supersession_collisions(all_proposals)
    existing_collisions = await detect_existing_case_collisions(db, all_proposals)
    worklist = aggregate_catalogue_miss_worklist(all_misses)

    ready = [p for p in all_proposals if p.status == "ready"]
    attention = [p for p in all_proposals if p.status == "needs_attention"]

    preview_id = str(uuid.uuid4())
    return {
        "preview_id": preview_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(files),
        "case_proposal_count": len(all_proposals),
        "ready_count": len(ready),
        "needs_attention_count": len(attention),
        "line_count_total": sum(p.row_count for p in ready),
        "files": file_reports,
        "case_proposals": [p.to_dict() for p in all_proposals],
        "supersession_collisions": collisions,
        "existing_case_collisions": existing_collisions,
        "catalogue_miss_worklist": worklist,
        "file_manifest": file_manifest,
        "totals": {
            "files": len(files),
            "period_assignments": len(all_proposals),
            "cases_ready": len(ready),
            "cases_needs_attention": len(attention),
            "lines_ready": sum(p.row_count for p in ready),
            "catalogue_miss_tokens": len(worklist),
            "collision_groups": len(collisions),
            "existing_case_collision_groups": len(existing_collisions),
        },
    }
