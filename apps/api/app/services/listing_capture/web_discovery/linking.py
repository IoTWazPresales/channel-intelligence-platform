"""Exact catalogue-wide identity decisions and write-free unlinked-listing previews.

Stock codes, titles and brands are evidence only. Identity keys come from the
existing listing-capture normalisers; no fuzzy matching is used.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cst_listing_seed import CstListingSeed
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing
from app.models.listing_link import (
    LINK_REJECTED,
    QUEUE_NOT_ON_SITE,
    QUEUE_REJECTED,
    ListingLink,
    ListingLinkQueue,
)
from app.models.listing_site import ListingSite
from app.services.listing_capture.identity import (
    _MIN_MODEL,
    barcode_key,
    model_key,
    page_facts_from_html,
    product_barcodes,
    product_models,
)
from app.services.listing_capture.links import listing_link_state
from app.services.listing_capture.web_discovery.homepage import parse_home
from app.services.listing_capture.web_discovery.polite import DEFAULT_SPACING_SECONDS

AUTO_LINK = "auto_link"
QUEUE = "steward_queue"
NONE = "none"


@dataclass
class CatalogueIndex:
    tenant_id: str
    products: dict[int, Any] = field(default_factory=dict)
    barcodes: dict[str, set[int]] = field(default_factory=dict)
    models: dict[str, set[int]] = field(default_factory=dict)

    @classmethod
    def from_products(cls, products: Iterable[Any], tenant_id: str) -> CatalogueIndex:
        index = cls(tenant_id=tenant_id)
        for product in products:
            if str(getattr(product, "tenant_id", tenant_id)) != tenant_id:
                continue
            pid = int(product.id)
            index.products[pid] = product
            for value in product_barcodes(product):
                key = barcode_key(value)
                if key:
                    index.barcodes.setdefault(key, set()).add(pid)
            for value in product_models(product):
                key = model_key(value)
                if len(key) >= _MIN_MODEL:
                    index.models.setdefault(key, set()).add(pid)
        return index

    @classmethod
    def load(cls, session: Session, tenant_id: str) -> CatalogueIndex:
        products = session.scalars(
            select(DimProduct)
            .where(DimProduct.tenant_id == tenant_id)
            .order_by(DimProduct.id)
        ).all()
        return cls.from_products(products, tenant_id)

    def label(self, product_id: int) -> str:
        product = self.products.get(int(product_id))
        if product is None:
            return ""
        return str(
            getattr(product, "name", None)
            or getattr(product, "sales_model_name", None)
            or getattr(product, "sku", None)
            or product_id
        )

    def candidate_labels(self, ids: Iterable[int]) -> list[dict[str, Any]]:
        return [
            {"product_id": pid, "label": self.label(pid)}
            for pid in sorted(set(ids))
            if pid in self.products
        ]


@dataclass(frozen=True)
class LinkDecision:
    outcome: str
    product_id: int | None = None
    how: str | None = None
    candidates: list[int] = field(default_factory=list)
    reason: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, index: CatalogueIndex) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "product_id": self.product_id,
            "how": self.how,
            "reason": self.reason,
            "candidates": index.candidate_labels(self.candidates),
            "facts": deepcopy(self.evidence.get("facts") or {}),
            "evidence": deepcopy(self.evidence),
        }


def decide(
    facts: dict[str, Any] | None,
    index: CatalogueIndex,
    expected_product_id: int | None = None,
) -> LinkDecision:
    """Decide from exact keys across the tenant's entire catalogue.

    Conflicting keys at the same tier are ambiguous even if each key individually
    identifies one product. An ambiguous barcode never falls through to a model.
    """
    facts = deepcopy(facts or {})
    evidence: dict[str, Any] = {
        "facts": facts,
        "expected_product_id": expected_product_id,
        "matched_keys": {},
    }
    if expected_product_id is not None and expected_product_id not in index.products:
        return LinkDecision(NONE, reason="product_not_found", evidence=evidence)

    for how, values, normalise, lookup in (
        ("gtin", facts.get("barcodes") or [], barcode_key, index.barcodes),
        ("model", facts.get("models") or [], model_key, index.models),
    ):
        matches: dict[str, list[int]] = {}
        for value in values:
            key = normalise(value)
            if not key or (how == "model" and len(key) < _MIN_MODEL):
                continue
            ids = lookup.get(key, set())
            if ids:
                matches[key] = sorted(ids)
        if not matches:
            continue
        evidence["matched_keys"] = matches
        candidates = sorted({pid for ids in matches.values() for pid in ids})
        if len(candidates) != 1:
            return LinkDecision(
                QUEUE,
                candidates=candidates,
                reason="ambiguous_identity",
                evidence=evidence,
            )
        product_id = candidates[0]
        if expected_product_id is not None and product_id != expected_product_id:
            return LinkDecision(
                QUEUE,
                candidates=candidates,
                reason="identity_mismatch",
                evidence=evidence,
            )
        return LinkDecision(
            AUTO_LINK,
            product_id=product_id,
            how=how,
            evidence=evidence,
        )
    return LinkDecision(QUEUE, reason="no_identity_on_page", evidence=evidence)


def feed_seed_decision(
    session: Session, listing: CustomerListing, index: CatalogueIndex
) -> LinkDecision | None:
    """A feed mapping is exact only at the full customer/site/external-id key."""
    if not listing.external_id:
        return None
    seed = session.scalar(
        select(CstListingSeed).where(
            CstListingSeed.customer_id == listing.customer_id,
            CstListingSeed.marketplace == listing.marketplace,
            CstListingSeed.external_id == listing.external_id,
            CstListingSeed.product_id.is_not(None),
            CstListingSeed.status != "rejected",
        )
    )
    if seed is None or seed.product_id not in index.products:
        return None
    evidence = {
        "facts": {},
        "feed_seed": {
            "seed_id": int(seed.id),
            "customer_id": int(seed.customer_id),
            "marketplace": seed.marketplace,
            "external_id": seed.external_id,
            "product_id": int(seed.product_id),
        },
    }
    return LinkDecision(
        AUTO_LINK,
        product_id=int(seed.product_id),
        how="feed_seed",
        evidence=evidence,
    )


def _previously_decided(
    session: Session, listing: CustomerListing, site_id: int | None
) -> bool:
    marker = (listing.meta_json or {}).get("discovery_link_undo") or {}
    if marker.get("url") == listing.url:
        return True
    if site_id is None:
        return False
    return session.scalar(
        select(ListingLinkQueue.id)
        .where(
            ListingLinkQueue.listing_id == listing.id,
            ListingLinkQueue.product_id.is_(None),
            ListingLinkQueue.site_id == site_id,
            ListingLinkQueue.status.in_((QUEUE_NOT_ON_SITE, QUEUE_REJECTED)),
        )
        .limit(1)
    ) is not None


def link_unlinked_listings(
    session: Session,
    tenant_id: str,
    customer_id: int | None,
    getter: Any,
    index: CatalogueIndex | None = None,
) -> list[dict[str, Any]]:
    """Read-only callback for S1's ``link_listings`` preview seam."""
    index = index or CatalogueIndex.load(session, tenant_id)
    if index.tenant_id != tenant_id:
        raise ValueError("catalogue tenant mismatch")
    statement = (
        select(CustomerListing, DimCustomer.name)
        .join(DimCustomer, DimCustomer.id == CustomerListing.customer_id)
        .where(
            DimCustomer.tenant_id == tenant_id,
            DimCustomer.merged_into_customer_id.is_(None),
            CustomerListing.product_id.is_(None),
        )
        .order_by(CustomerListing.id)
    )
    if customer_id is not None:
        statement = statement.where(CustomerListing.customer_id == customer_id)
    sites = {
        row.site_key: row
        for row in session.scalars(
            select(ListingSite).where(ListingSite.tenant_id == tenant_id)
        ).all()
    }
    result = []
    for listing, customer_name in session.execute(statement).all():
        site = sites.get(str(listing.marketplace).strip().lower())
        site_id = int(site.id) if site is not None else None
        if _previously_decided(session, listing, site_id):
            decision = LinkDecision(NONE, reason="rejected_before")
        else:
            decision = feed_seed_decision(session, listing, index)
            if decision is None:
                evidence: dict[str, Any] = {
                    "facts": {},
                    "http_status": None,
                    "title": None,
                    "refused": "site_not_stored",
                }
                if site is not None:
                    fetched = getter.get(
                        listing.url,
                        gate_key=site.site_key,
                        spacing=float(
                            site.rate_limit_seconds
                            if site.rate_limit_seconds is not None
                            else DEFAULT_SPACING_SECONDS
                        ),
                    )
                    evidence.update(
                        http_status=fetched.status,
                        title=parse_home(fetched.body or "").title,
                        refused=fetched.refused,
                        final_url=fetched.final_url,
                    )
                    if fetched.status == 200 and fetched.body and not fetched.refused:
                        facts = page_facts_from_html(fetched.body)
                        exact = decide(facts, index)
                        decision = LinkDecision(
                            exact.outcome,
                            product_id=exact.product_id,
                            how=exact.how,
                            candidates=exact.candidates,
                            reason=exact.reason,
                            evidence={**exact.evidence, **evidence, "facts": facts},
                        )
                if decision is None:
                    decision = LinkDecision(
                        QUEUE, reason="page_unreadable", evidence=evidence
                    )
            if decision.product_id is not None and site is not None:
                rejected = session.scalar(
                    select(ListingLink.id).where(
                        ListingLink.tenant_id == tenant_id,
                        ListingLink.site_id == site.id,
                        ListingLink.product_id == decision.product_id,
                        ListingLink.url == listing.url,
                        ListingLink.status == LINK_REJECTED,
                    )
                )
                if rejected is not None:
                    decision = LinkDecision(
                        NONE, reason="rejected_before", evidence=decision.evidence
                    )
        result.append(
            {
                "item_id": f"l-{listing.id}",
                "listing_id": int(listing.id),
                "customer_id": int(listing.customer_id),
                "customer_name": str(customer_name or ""),
                "site_id": site_id,
                "marketplace": listing.marketplace,
                "external_id": listing.external_id,
                "url": listing.url,
                "listing_state": listing_link_state(listing),
                **decision.to_dict(index),
            }
        )
    return result
