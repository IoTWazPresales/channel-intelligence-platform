"""Distributor sales & inventory import: staging, resolution, aggregated mapping candidates, fact apply."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactInventoryDistributor, FactSalesSellout
from app.models.import_distributor_si import (
    CustomerSourceTokenAlias,
    DistributorSourceTokenAlias,
    ImportDistributorSiStagingLine,
    ImportEntityMappingCandidate,
)
from app.models.ingestion import ImportJob, ImportRowResult
from app.models.mapping import ProductAlias
from app.services.commercial_planner.open_channel_customer import OPEN_CHANNEL_CUSTOMER_CODE
from app.utils.json_safe import to_jsonable, verify_json_serializable

CANONICAL = (
    "distributor_token",
    "product_identifier",
    "transaction_date",
    "snapshot_date",
    "quantity_sold",
    "stock_on_hand",
    "customer_dealer_token",
    "dealer_group_token",
    "unit_sellout_price_ex_tax_amount",
    "reported_revenue_amount",
    "currency_code",
    "channel_key_token",
    "region_or_province_token",
    "open_channel_evidence",
    "ignored_shipping_evidence",
)

CHANNEL_OPEN_SUBSTRINGS = ("open channel", "open_channel", "open-channel")

SENTINEL_CUSTOMER_TOKENS = frozenset(
    {
        "cash sale",
        "walk-in",
        "walk in",
        "unknown",
        "dealer",
        "misc",
        "n/a",
        "na",
        "tbd",
    }
)

DEALER_GROUP_PLACEHOLDER_SUBSTRINGS = ("to be mapped", "tbd", "unknown", "pending mapping")

# Channel / marketplace hints for steward review (generic; not region-specific).
STRATEGIC_CHANNEL_HINT_SUBSTRINGS = (
    "amazon",
    "takealot",
    "makro",
    "massmart",
    "game ",
    " game",
    "incredible connection",
    "walmart",
    "ebay",
    "alibaba",
    "shopify",
    "marketplace",
    "etail",
    "e-tail",
)


def _norm_key(s: str | None) -> str:
    if s is None:
        return ""
    t = str(s).strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _col(mapping: dict[str, str], key: str) -> str | None:
    for src, tgt in mapping.items():
        if tgt == key:
            return src
    return None


def _channel_raw_for_dsi(row: pd.Series, mapping: dict[str, str]) -> str | None:
    """Prefer channel_key_token; fall back to channel_code-mapped column (alias collision with other templates)."""
    c = _col(mapping, "channel_key_token")
    if c:
        v = _clean_str(row.get(c))
        if v:
            return v
    c2 = _col(mapping, "channel_code")
    if c2:
        return _clean_str(row.get(c2))
    return None


def _clean_str(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    t = str(v).strip()
    if not t or t.lower() == "nan":
        return None
    return t


def _parse_date(v: Any) -> date | None:
    s = _clean_str(v)
    if not s:
        return None
    try:
        ts = pd.to_datetime(s, errors="coerce")
        if pd.isna(ts):
            return None
        if isinstance(ts, pd.Timestamp):
            return ts.date()
    except (ValueError, TypeError):
        return None
    return None


def _parse_decimal(v: Any) -> Decimal | None:
    s = _clean_str(v)
    if not s:
        return None
    try:
        return Decimal(s.replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _load_products(db: Session) -> tuple[dict[str, DimProduct], dict[str, int]]:
    """sku_lower -> product, alias_lower -> product_id."""
    products = {p.sku.strip().lower(): p for p in db.scalars(select(DimProduct)).all()}
    alias_to_pid: dict[str, int] = {}
    for a in db.scalars(select(ProductAlias)).all():
        alias_to_pid[a.alias_value.strip().lower()] = a.product_id
    return products, alias_to_pid


def _resolve_product(
    raw: str | None, products: dict[str, DimProduct], alias_to_pid: dict[str, int]
) -> tuple[int | None, str | None]:
    if not raw:
        return None, "missing_product_token"
    key = raw.strip().lower()
    p = products.get(key)
    if p:
        return p.id, None
    pid = alias_to_pid.get(key)
    if pid:
        return pid, None
    return None, "unresolved_product"


def _alias_distributor_id(db: Session, source_id: int | None, normalized_token: str) -> int | None:
    if not normalized_token:
        return None
    q = select(DistributorSourceTokenAlias.distributor_id).where(
        DistributorSourceTokenAlias.normalized_token == normalized_token,
        DistributorSourceTokenAlias.status == "approved",
    )
    if source_id is not None:
        q = q.where(
            or_(
                DistributorSourceTokenAlias.source_definition_id.is_(None),
                DistributorSourceTokenAlias.source_definition_id == source_id,
            )
        )
    rows = list(dict.fromkeys(db.scalars(q).all()))
    if len(rows) == 1:
        return int(rows[0])
    return None


def _resolve_distributor(db: Session, raw: str | None, source_id: int | None = None) -> tuple[int | None, str | None]:
    if not raw or not str(raw).strip():
        return None, "missing_distributor_cell_value"
    token = raw.strip().lower()
    nt = _norm_key(raw)
    alias_id = _alias_distributor_id(db, source_id, nt)
    if alias_id is not None:
        return alias_id, None
    for d in db.scalars(select(DimDistributor)).all():
        if d.code.strip().lower() == token or d.name.strip().lower() == token:
            return d.id, None
        if token in d.name.strip().lower() or d.name.strip().lower() in token:
            # avoid loose substring false positives for very short tokens
            if len(token) >= 4:
                return d.id, None
    return None, "unresolved_distributor_token"


def _open_channel_customer_id(db: Session) -> int | None:
    return db.scalar(select(DimCustomer.id).where(DimCustomer.code == OPEN_CHANNEL_CUSTOMER_CODE))


def _alias_customer_id(
    db: Session,
    source_id: int | None,
    distributor_id: int | None,
    normalized_customer: str,
    dealer_group: str | None,
) -> int | None:
    if not normalized_customer:
        return None
    q = select(CustomerSourceTokenAlias.customer_id).where(
        CustomerSourceTokenAlias.normalized_token == normalized_customer,
        CustomerSourceTokenAlias.status == "approved",
    )
    if source_id is not None:
        q = q.where(
            or_(
                CustomerSourceTokenAlias.source_definition_id.is_(None),
                CustomerSourceTokenAlias.source_definition_id == source_id,
            )
        )
    if distributor_id is not None:
        q = q.where(
            or_(
                CustomerSourceTokenAlias.distributor_id.is_(None),
                CustomerSourceTokenAlias.distributor_id == distributor_id,
            )
        )
    rows = list(dict.fromkeys(db.scalars(q).all()))
    if len(rows) == 1:
        return int(rows[0])
    return None


def _resolve_customer(
    db: Session,
    *,
    source_id: int | None,
    distributor_id: int | None,
    customer_raw: str | None,
    dealer_group_raw: str | None,
    channel_raw: str | None,
    open_flag_raw: Any,
) -> tuple[int | None, list[str]]:
    """Returns (customer_id, diagnostic_codes)."""
    diagnostics: list[str] = []
    nt = _norm_key(customer_raw)
    dg = _clean_str(dealer_group_raw)

    if dg and any(x in dg.lower() for x in DEALER_GROUP_PLACEHOLDER_SUBSTRINGS):
        diagnostics.append("dealer_group_placeholder")

    alias_id = _alias_customer_id(db, source_id, distributor_id, nt, dg)
    if alias_id is not None:
        diagnostics.append("customer_resolved_alias")
        return alias_id, diagnostics

    open_from_col = False
    if open_flag_raw is not None:
        s = str(open_flag_raw).strip().lower()
        open_from_col = s in ("1", "true", "yes", "y", "x")

    ch = (channel_raw or "").strip().lower()
    open_from_channel = any(h in ch for h in CHANNEL_OPEN_SUBSTRINGS)

    if (not nt) and (open_from_col or open_from_channel):
        oc = _open_channel_customer_id(db)
        if oc:
            diagnostics.append("customer_open_channel")
            return oc, diagnostics
        diagnostics.append("open_channel_missing_dim")
        return None, diagnostics

    if not nt:
        diagnostics.append("missing_customer_token")
        return None, diagnostics

    if nt in SENTINEL_CUSTOMER_TOKENS:
        diagnostics.append("customer_sentinel_unresolved")
        return None, diagnostics

    oc_id = _open_channel_customer_id(db)
    if open_from_col or open_from_channel:
        if oc_id:
            diagnostics.append("customer_open_channel")
            return oc_id, diagnostics

    stmt = select(DimCustomer.id).where(func.lower(DimCustomer.code) == nt)
    cid = db.scalar(stmt)
    if cid:
        diagnostics.append("customer_resolved_code")
        return int(cid), diagnostics

    stmt2 = select(DimCustomer.id).where(func.lower(DimCustomer.name) == nt)
    ids = list(db.scalars(stmt2).all())
    if len(ids) == 1:
        diagnostics.append("customer_resolved_exact_name")
        return int(ids[0]), diagnostics
    if len(ids) > 1:
        diagnostics.append("ambiguous_customer_name")
        return None, diagnostics

    diagnostics.append("customer_unresolved")
    return None, diagnostics


def _build_mapped_canonical(
    row: pd.Series,
    mapping: dict[str, str],
    ignored_cols: list[str],
) -> dict[str, Any]:
    """Build JSON-serializable canonical snapshot (Excel/pandas cells may be Timestamp, numpy, Decimal)."""
    out: dict[str, Any] = {}
    for src, tgt in mapping.items():
        if tgt in CANONICAL and tgt != "ignored_shipping_evidence":
            v = row.get(src)
            if v is not None and not (isinstance(v, float) and pd.isna(v)):
                out[tgt] = to_jsonable(v)
    if ignored_cols:
        ship: dict[str, Any] = {}
        for c in ignored_cols:
            if c in row.index:
                v = row.get(c)
                if v is not None and not (isinstance(v, float) and pd.isna(v)):
                    ship[str(c)] = to_jsonable(v)
        if ship:
            out["ignored_shipping_evidence"] = ship
    return out


def process_distributor_sales_inventory(db: Session, job: ImportJob, df: pd.DataFrame, mapping: dict[str, str]) -> int:
    """Validate + stage (+ apply if job.import_mode == 'apply'). Returns blocking error count."""
    if "distributor_token" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_distributor_token_mapping",
                message="Required column mapping missing: Distributor.",
            )
        )
        return 1
    if "product_identifier" not in mapping.values():
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="missing_product_identifier_mapping",
                message="Required column mapping missing: product identifier (SKU / part number / model / product code).",
            )
        )
        return 1

    db.execute(delete(ImportDistributorSiStagingLine).where(ImportDistributorSiStagingLine.import_job_id == job.id))
    db.execute(delete(ImportEntityMappingCandidate).where(ImportEntityMappingCandidate.import_job_id == job.id))
    db.flush()

    ignored_src_cols = [k for k, v in mapping.items() if v == "ignored_shipping_evidence"]

    products, alias_map = _load_products(db)
    source = job.source
    source_def_id = source.id if source else None

    agg: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "row_count": 0,
            "total_units": Decimal(0),
            "total_value": Decimal(0),
            "samples": [],
            "strategic_channel_hint": False,
        }
    )

    blocking = 0
    warnings = 0
    first_unresolved_dist_raw: str | None = None

    for idx, row in df.iterrows():
        rn = int(idx) + 1
        raw_payload = {str(k): to_jsonable(row[k]) for k in row.index}
        mapped = _build_mapped_canonical(row, mapping, ignored_src_cols)
        verify_json_serializable("raw_row_payload", raw_payload)
        verify_json_serializable("mapped_canonical", mapped)

        dist_raw = _clean_str(row.get(_col(mapping, "distributor_token"))) if _col(mapping, "distributor_token") else None
        prod_raw = _clean_str(row.get(_col(mapping, "product_identifier"))) if _col(mapping, "product_identifier") else None
        cust_raw = _clean_str(row.get(_col(mapping, "customer_dealer_token"))) if _col(mapping, "customer_dealer_token") else None
        dg_raw = _clean_str(row.get(_col(mapping, "dealer_group_token"))) if _col(mapping, "dealer_group_token") else None
        ch_raw = _channel_raw_for_dsi(row, mapping)
        open_raw = row.get(_col(mapping, "open_channel_evidence")) if _col(mapping, "open_channel_evidence") else None

        tx_date = _parse_date(row.get(_col(mapping, "transaction_date"))) if _col(mapping, "transaction_date") else None
        snap_date = _parse_date(row.get(_col(mapping, "snapshot_date"))) if _col(mapping, "snapshot_date") else None
        if tx_date is None and snap_date is not None:
            tx_date = snap_date
        if snap_date is None and tx_date is not None:
            snap_date = tx_date

        qty_sold = _parse_decimal(row.get(_col(mapping, "quantity_sold"))) if _col(mapping, "quantity_sold") else None
        soh = _parse_decimal(row.get(_col(mapping, "stock_on_hand"))) if _col(mapping, "stock_on_hand") else None
        unit_price = (
            _parse_decimal(row.get(_col(mapping, "unit_sellout_price_ex_tax_amount")))
            if _col(mapping, "unit_sellout_price_ex_tax_amount")
            else None
        )
        reported_rev = (
            _parse_decimal(row.get(_col(mapping, "reported_revenue_amount")))
            if _col(mapping, "reported_revenue_amount")
            else None
        )
        cur = _clean_str(row.get(_col(mapping, "currency_code"))) if _col(mapping, "currency_code") else None

        computed_rev: Decimal | None = None
        if qty_sold is not None and unit_price is not None:
            computed_rev = qty_sold * unit_price

        diag: list[str] = []
        sev = "info"

        rdid, derr = _resolve_distributor(db, dist_raw, source_def_id)
        if derr:
            diag.append(derr)
            sev = "error"

        rpid, perr = _resolve_product(prod_raw, products, alias_map)
        if perr:
            diag.append(perr)
            sev = "error"

        rdistributor_id = rdid
        rcustomer_id: int | None = None
        sellout_attempt = qty_sold is not None and tx_date is not None
        inv_attempt = soh is not None and snap_date is not None

        if sellout_attempt:
            rcustomer_id, cd = _resolve_customer(
                db,
                source_id=source_def_id,
                distributor_id=rdistributor_id,
                customer_raw=cust_raw,
                dealer_group_raw=dg_raw,
                channel_raw=ch_raw,
                open_flag_raw=open_raw,
            )
            diag.extend(cd)
            if rcustomer_id is None:
                sev = "error"
                diag.append("sellout_blocked_missing_customer")

        mismatch = False
        if reported_rev is not None and computed_rev is not None:
            if abs(reported_rev - computed_rev) > Decimal("0.01") * max(Decimal(1), abs(reported_rev)):
                mismatch = True
                diag.append("reported_vs_computed_revenue_mismatch")
                if sev != "error":
                    sev = "warning"

        if qty_sold is not None and qty_sold < 0:
            diag.append("return_or_credit_suspected_qty")
            if sev == "info":
                sev = "warning"
        if reported_rev is not None and reported_rev < 0:
            diag.append("return_or_credit_suspected_revenue")
            if sev == "info":
                sev = "warning"

        if sellout_attempt and tx_date is None:
            diag.append("missing_transaction_date")
            sev = "error"
        if inv_attempt and snap_date is None:
            diag.append("missing_snapshot_date")
            sev = "error"

        can_sellout = (
            sev != "error"
            and bool(rdistributor_id)
            and bool(rpid)
            and bool(rcustomer_id)
            and tx_date is not None
            and qty_sold is not None
        )
        can_inv = (
            sev != "error"
            and bool(rdistributor_id)
            and bool(rpid)
            and snap_date is not None
            and soh is not None
        )
        if sev == "error":
            res_status = "blocked"
        elif can_sellout and can_inv:
            res_status = "ready_both"
        elif can_sellout:
            res_status = "ready_sellout"
        elif can_inv:
            res_status = "ready_inventory"
        else:
            res_status = "staged_only"

        line = ImportDistributorSiStagingLine(
            import_job_id=job.id,
            source_row_number=rn,
            raw_row_payload=raw_payload,
            mapped_canonical=mapped,
            raw_distributor_token=dist_raw,
            raw_customer_dealer_token=cust_raw,
            raw_dealer_group_token=dg_raw,
            raw_product_token=prod_raw,
            resolved_distributor_id=rdistributor_id,
            resolved_customer_id=rcustomer_id,
            resolved_product_id=rpid,
            transaction_date=tx_date,
            snapshot_date=snap_date,
            quantity_sold=float(qty_sold) if qty_sold is not None else None,
            stock_on_hand=float(soh) if soh is not None else None,
            unit_sellout_price_ex_tax_amount=float(unit_price) if unit_price is not None else None,
            reported_revenue_amount=float(reported_rev) if reported_rev is not None else None,
            computed_revenue_amount=float(computed_rev) if computed_rev is not None else None,
            currency_code=(cur[:8] if cur else None),
            resolution_status=res_status,
            diagnostic_codes=diag,
            severity=sev,
            apply_status="pending",
        )
        db.add(line)

        if sev == "error":
            blocking += 1
        elif sev == "warning":
            warnings += 1

        if rdistributor_id is None and dist_raw:
            k = ("distributor_token", _norm_key(dist_raw))
            a = agg[k]
            a["row_count"] += 1
            if len(a["samples"]) < 5:
                a["samples"].append(dist_raw)
        if rpid is None and prod_raw:
            k = ("product_identifier", _norm_key(prod_raw))
            a = agg[k]
            a["row_count"] += 1
            if qty_sold is not None:
                a["total_units"] += abs(qty_sold)
            if reported_rev is not None:
                a["total_value"] += abs(reported_rev)
            if len(a["samples"]) < 5:
                a["samples"].append(prod_raw)
        if sellout_attempt and rcustomer_id is None:
            nk = f"{_norm_key(cust_raw) or '__blank__'}||{_norm_key(dg_raw)}"
            k = ("customer_dealer_token", nk)
            a = agg[k]
            a["row_count"] += 1
            if qty_sold is not None:
                a["total_units"] += abs(qty_sold)
            if reported_rev is not None:
                a["total_value"] += abs(reported_rev)
            if len(a["samples"]) < 5:
                a["samples"].append(cust_raw or "")
            chv = (ch_raw or "").strip().lower()
            if chv and any(h in chv for h in STRATEGIC_CHANNEL_HINT_SUBSTRINGS):
                a["strategic_channel_hint"] = True

    for (etype, nkey), data in agg.items():
        dg = None
        if etype == "customer_dealer_token" and "||" in nkey:
            parts = nkey.split("||", 1)
            nkey_clean, dg = parts[0], parts[1] or None
        else:
            nkey_clean = nkey
        cand = ImportEntityMappingCandidate(
            import_job_id=job.id,
            source_definition_id=source_def_id,
            entity_type=etype,
            normalized_key=nkey_clean[:512],
            dealer_group_token=(dg[:512] if dg else None),
            row_count=int(data["row_count"]),
            total_units=float(data["total_units"]) if data["total_units"] else None,
            total_reported_value=float(data["total_value"]) if data["total_value"] else None,
            sample_raw_values=to_jsonable(data["samples"][:5]),
            status="needs_review",
            context=to_jsonable(
                {
                    "aggregated": True,
                    **({"strategic_channel_hint": True} if data.get("strategic_channel_hint") else {}),
                }
            ),
        )
        db.add(cand)

    if first_unresolved_dist_raw:
        db.add(
            ImportRowResult(
                job_id=job.id,
                row_number=0,
                severity="error",
                code="unresolved_distributor_token",
                message=(
                    f"Distributor token '{first_unresolved_dist_raw}' could not be matched to an existing distributor."
                ),
            )
        )

    eff_rev_note = ""
    if job.import_mode == "apply":
        db.flush()
        sell_tbl = FactSalesSellout.__table__
        inv_tbl = FactInventoryDistributor.__table__
        lines = db.scalars(
            select(ImportDistributorSiStagingLine)
            .where(ImportDistributorSiStagingLine.import_job_id == job.id)
            .order_by(ImportDistributorSiStagingLine.source_row_number)
        ).all()
        applied_sell = 0
        applied_inv = 0
        for line in lines:
            if line.severity == "error":
                continue
            parts: list[str] = []
            if (
                line.resolved_distributor_id
                and line.resolved_product_id
                and line.transaction_date is not None
                and line.quantity_sold is not None
                and line.resolved_customer_id
            ):
                eff = line.computed_revenue_amount
                if eff is None and line.reported_revenue_amount is not None:
                    eff = line.reported_revenue_amount
                if eff is None:
                    eff = 0.0
                stmt = (
                    pg_insert(sell_tbl)
                    .values(
                        product_id=line.resolved_product_id,
                        customer_id=line.resolved_customer_id,
                        distributor_id=line.resolved_distributor_id,
                        channel_id=None,
                        period_start=line.transaction_date,
                        units=line.quantity_sold,
                        revenue=float(eff),
                        unit_sellout_price_ex_tax_amount=line.unit_sellout_price_ex_tax_amount,
                        reported_revenue_amount=line.reported_revenue_amount,
                        computed_revenue_amount=line.computed_revenue_amount,
                        currency_code=line.currency_code,
                        source_import_job_id=job.id,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fact_sales_sellout_dsi_v1",
                        set_={
                            "units": text("EXCLUDED.units"),
                            "revenue": text("EXCLUDED.revenue"),
                            "unit_sellout_price_ex_tax_amount": text("EXCLUDED.unit_sellout_price_ex_tax_amount"),
                            "reported_revenue_amount": text("EXCLUDED.reported_revenue_amount"),
                            "computed_revenue_amount": text("EXCLUDED.computed_revenue_amount"),
                            "currency_code": text("EXCLUDED.currency_code"),
                            "source_import_job_id": text("EXCLUDED.source_import_job_id"),
                        },
                    )
                    .returning(sell_tbl.c.id)
                )
                rid = db.execute(stmt).scalar_one()
                line.fact_sellout_row_id = int(rid) if rid is not None else None
                applied_sell += 1
                parts.append("sellout")
            if (
                line.resolved_distributor_id
                and line.resolved_product_id
                and line.snapshot_date is not None
                and line.stock_on_hand is not None
            ):
                inv_stmt = (
                    pg_insert(inv_tbl)
                    .values(
                        product_id=line.resolved_product_id,
                        distributor_id=line.resolved_distributor_id,
                        as_of_date=line.snapshot_date,
                        on_hand_units=float(line.stock_on_hand),
                        source_import_job_id=job.id,
                    )
                    .on_conflict_do_update(
                        constraint="uq_fact_inventory_distributor_dsi_v1",
                        set_={
                            "on_hand_units": text("EXCLUDED.on_hand_units"),
                            "source_import_job_id": text("EXCLUDED.source_import_job_id"),
                        },
                    )
                    .returning(inv_tbl.c.id)
                )
                iid = db.execute(inv_stmt).scalar_one()
                line.fact_inventory_row_id = int(iid) if iid is not None else None
                applied_inv += 1
                parts.append("inventory")
            if parts:
                line.apply_status = "+".join(parts)
        meta = dict(job.staged_metadata or {})
        meta["distributor_si"] = to_jsonable(
            {
                "applied": True,
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "sellout_rows": applied_sell,
                "inventory_rows": applied_inv,
            }
        )
        job.staged_metadata = to_jsonable(meta)
        eff_rev_note = f" Applied sell-out facts={applied_sell}, inventory facts={applied_inv} (upsert by natural key)."

    summary = {
        "staging_rows": int(len(df)),
        "blocking_rows": blocking,
        "warning_rows": warnings,
        "aggregated_candidates": len(agg),
        "import_mode": job.import_mode,
    }
    db.add(
        ImportRowResult(
            job_id=job.id,
            row_number=0,
            severity="info" if blocking == 0 else "warning",
            code="distributor_si_summary",
            message=json.dumps(summary) + eff_rev_note,
        )
    )
    return 1 if blocking else 0

