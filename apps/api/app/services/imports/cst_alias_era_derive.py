"""Derive effective-dated customer_article_alias eras from inbound shipping POD.

For each (customer, article) with multiple product candidates (SCM multi-model),
compute valid_from via:
  1. MIN(pod_date) where product_id=M AND resolved_customer_id=C
  2. else MIN(pod_date) for product_id=M globally
  3. else MIN(ship_confirm_date) on the same scope ladder
  4. else steward_manual (no auto date)

Orders eras by first arrival; sets A.valid_to = B.valid_from.
Writes proposed rows (never confirms). Idempotent re-run replaces prior
scm_upload/shipping_derive proposed eras for that (customer, article) set.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.customer_article_alias import CustomerArticleAlias
from app.services.imports.cst_d1 import normalize_article_token
from app.services.imports.distributor_sales_inventory import _load_product_resolution_index
from app.services.imports.product_resolution_standard import resolve_product_id_single_match
from app.utils.json_safe import to_jsonable


@dataclass
class EraDeriveSummary:
    groups: int = 0
    eras_proposed: int = 0
    steward_manual: int = 0
    equal_pod_blocked: int = 0
    model_unresolved: int = 0
    samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _first_pod(
    session: Session,
    *,
    product_id: int,
    customer_id: int | None,
) -> tuple[date | None, str]:
    """Return (first_date, clock_source)."""
    if customer_id is not None:
        d = session.execute(
            text(
                """
                select min(pod_date)
                from fact_inbound_shipment
                where product_id = :p
                  and resolved_customer_id = :c
                  and pod_date is not null
                """
            ),
            {"p": product_id, "c": customer_id},
        ).scalar()
        if d is not None:
            return d, "pod_customer_scoped"
        d = session.execute(
            text(
                """
                select min(ship_confirm_date)
                from fact_inbound_shipment
                where product_id = :p
                  and resolved_customer_id = :c
                  and ship_confirm_date is not null
                """
            ),
            {"p": product_id, "c": customer_id},
        ).scalar()
        if d is not None:
            return d, "ship_confirm_customer_scoped"

    d = session.execute(
        text(
            """
            select min(pod_date)
            from fact_inbound_shipment
            where product_id = :p and pod_date is not null
            """
        ),
        {"p": product_id},
    ).scalar()
    if d is not None:
        return d, "pod_global"

    d = session.execute(
        text(
            """
            select min(ship_confirm_date)
            from fact_inbound_shipment
            where product_id = :p and ship_confirm_date is not null
            """
        ),
        {"p": product_id},
    ).scalar()
    if d is not None:
        return d, "ship_confirm"
    return None, "steward_manual"


def derive_alias_eras_from_shipping(
    session: Session,
    *,
    multi_model_groups: list[dict[str, Any]],
    actor: str | None = None,
) -> EraDeriveSummary:
    """Propose dated eras for multi-model SCM groups.

    Each group: {customer_id, article, sales_models: [str, ...]}
    """
    summary = EraDeriveSummary(groups=len(multi_model_groups))
    idx = _load_product_resolution_index(session)
    now = datetime.now(timezone.utc).isoformat()

    for group in multi_model_groups:
        cid = int(group["customer_id"])
        art = normalize_article_token(str(group.get("article") or ""))
        models = [str(m).strip() for m in (group.get("sales_models") or []) if str(m).strip()]
        if not art or len(models) < 2:
            continue

        # Clear prior proposed shipping/scm multi-era stubs for this article
        # (keep confirmed).
        existing_proposed = list(
            session.scalars(
                select(CustomerArticleAlias).where(
                    CustomerArticleAlias.customer_id == cid,
                    CustomerArticleAlias.article_no_normalized == art,
                    CustomerArticleAlias.status == "proposed",
                )
            ).all()
        )
        for row in existing_proposed:
            session.delete(row)
        session.flush()

        candidates: list[dict[str, Any]] = []
        for model in models:
            pid = resolve_product_id_single_match(idx, model)
            if pid is None:
                summary.model_unresolved += 1
                continue
            first, clock = _first_pod(session, product_id=int(pid), customer_id=cid)
            candidates.append(
                {
                    "product_id": int(pid),
                    "sales_model": model,
                    "valid_from": first,
                    "clock_source": clock,
                }
            )

        dated = [c for c in candidates if c["valid_from"] is not None]
        undated = [c for c in candidates if c["valid_from"] is None]
        summary.steward_manual += len(undated)

        # Equal first-POD across different products → FLAG block (do not auto-order)
        by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
        for c in dated:
            by_date[c["valid_from"]].append(c)
        if any(len(v) > 1 for v in by_date.values()):
            summary.equal_pod_blocked += 1
            if len(summary.samples) < 20:
                summary.samples.append(
                    {
                        "customer_id": cid,
                        "article": art,
                        "flag": "equal_pod",
                        "candidates": candidates,
                    }
                )
            # Still propose undated steward rows only — no overlapping auto eras
            for c in undated:
                session.add(
                    CustomerArticleAlias(
                        customer_id=cid,
                        article_no_normalized=art,
                        product_id=c["product_id"],
                        status="proposed",
                        valid_from=None,
                        valid_to=None,
                        evidence_json=to_jsonable(
                            {
                                "source": "shipping_derive",
                                "sales_model_name": c["sales_model"],
                                "clock_source": "steward_manual",
                                "flag": "equal_pod_sibling",
                                "imported_at": now,
                                "actor": actor,
                            }
                        ),
                    )
                )
                summary.eras_proposed += 1
            continue

        dated_sorted = sorted(dated, key=lambda c: c["valid_from"])
        for i, c in enumerate(dated_sorted):
            vf = None if i == 0 else c["valid_from"]
            vt = dated_sorted[i + 1]["valid_from"] if i + 1 < len(dated_sorted) else None
            session.add(
                CustomerArticleAlias(
                    customer_id=cid,
                    article_no_normalized=art,
                    product_id=c["product_id"],
                    status="proposed",
                    valid_from=vf,
                    valid_to=vt,
                    evidence_json=to_jsonable(
                        {
                            "source": "shipping_derive",
                            "sales_model_name": c["sales_model"],
                            "clock_source": c["clock_source"],
                            "first_pod_or_ship": c["valid_from"].isoformat()
                            if c["valid_from"]
                            else None,
                            "imported_at": now,
                            "actor": actor,
                        }
                    ),
                )
            )
            summary.eras_proposed += 1

        for c in undated:
            session.add(
                CustomerArticleAlias(
                    customer_id=cid,
                    article_no_normalized=art,
                    product_id=c["product_id"],
                    status="proposed",
                    valid_from=None,
                    valid_to=None,
                    evidence_json=to_jsonable(
                        {
                            "source": "shipping_derive",
                            "sales_model_name": c["sales_model"],
                            "clock_source": "steward_manual",
                            "imported_at": now,
                            "actor": actor,
                        }
                    ),
                )
            )
            summary.eras_proposed += 1

        if len(summary.samples) < 15:
            summary.samples.append(
                {
                    "customer_id": cid,
                    "article": art,
                    "eras": [
                        {
                            "product_id": c["product_id"],
                            "model": c["sales_model"],
                            "clock": c["clock_source"],
                            "pod": c["valid_from"].isoformat() if c["valid_from"] else None,
                        }
                        for c in dated_sorted + undated
                    ],
                }
            )

    return summary


def collect_scm_multi_model_groups_from_rows(
    session: Session,
    rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """Rebuild multi-model groups from SCM parse rows (same canon as import)."""
    from app.services.imports.cst_article_alias_import import _resolve_customer_id

    grouped: dict[tuple[int, str], set[str]] = defaultdict(set)
    for r in rows:
        cust_raw = (r.get("customer") or "").strip()
        art_raw = (r.get("article") or "").strip()
        model_raw = (r.get("sales_model") or "").strip()
        if not cust_raw or not art_raw or not model_raw:
            continue
        cid = _resolve_customer_id(session, cust_raw)
        if cid is None:
            continue
        art = normalize_article_token(art_raw)
        if not art:
            continue
        grouped[(cid, art)].add(model_raw)
    return [
        {"customer_id": cid, "article": art, "sales_models": sorted(models)}
        for (cid, art), models in grouped.items()
        if len(models) > 1
    ]
