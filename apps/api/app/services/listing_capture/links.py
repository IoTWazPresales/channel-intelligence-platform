"""Learn a product page link, then remember the decision.

Order: the stored confirmed link, then the registered URL when the page's barcode or model
matches the product, then a barcode search, then a model search. A single corroborated match
is stored confirmed. Anything else waits for a steward. A reject and "not on this site" are
remembered. A report stock code is never the link and never the match.

A confirmed link whose page later shows a different product is marked stale and learned again.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dimensions import DimProduct
from app.models.listing_capture import CustomerListing
from app.models.listing_link import (
    LINK_CONFIRMED,
    LINK_REJECTED,
    LINK_STALE,
    QUEUE_CONFIRMED,
    QUEUE_NOT_ON_SITE,
    QUEUE_OPEN,
    QUEUE_REJECTED,
    ListingLink,
    ListingLinkQueue,
)
from app.services.listing_capture.adapters import SiteConfig, adapter_module
from app.services.listing_capture.adapters.rest_buybox import fetch as rest_fetch
from app.services.listing_capture.adapters.rest_buybox import parse_body, product_url
from app.services.listing_capture.identity import corroboration, page_facts_from_html, page_facts_from_json, product_models


def confirmed_link(session: Session, site_id: int, product_id: int) -> ListingLink | None:
    row = session.scalars(
        select(ListingLink).where(
            ListingLink.site_id == int(site_id),
            ListingLink.product_id == int(product_id),
            ListingLink.status == LINK_CONFIRMED,
        )
    ).first()
    return row if isinstance(row, ListingLink) else None


def _rejected_urls(session: Session, site_id: int, product_id: int) -> set[str]:
    rows = session.scalars(
        select(ListingLink.url).where(
            ListingLink.site_id == int(site_id),
            ListingLink.product_id == int(product_id),
            ListingLink.status == LINK_REJECTED,
        )
    ).all()
    return {str(u) for u in rows if isinstance(u, str)}


def _not_on_site(session: Session, site_id: int, product_id: int) -> bool:
    row = session.scalars(
        select(ListingLinkQueue.id).where(
            ListingLinkQueue.site_id == int(site_id),
            ListingLinkQueue.product_id == int(product_id),
            ListingLinkQueue.status == QUEUE_NOT_ON_SITE,
        )
    ).first()
    return row is not None


def _open_queue(session: Session, site_id: int, product_id: int) -> ListingLinkQueue | None:
    row = session.scalars(
        select(ListingLinkQueue).where(
            ListingLinkQueue.site_id == int(site_id),
            ListingLinkQueue.product_id == int(product_id),
            ListingLinkQueue.status == QUEUE_OPEN,
        )
    ).first()
    return row if isinstance(row, ListingLinkQueue) else None


def queue_case(
    session: Session,
    *,
    site: SiteConfig,
    product_id: int,
    customer_id: int | None,
    listing_id: int | None,
    reason: str,
    candidates: list[dict[str, Any]],
    evidence: dict[str, Any],
) -> None:
    if site.id is None:
        return
    row = _open_queue(session, site.id, product_id)
    if row is None:
        row = ListingLinkQueue(
            tenant_id=site.tenant_id,
            site_id=int(site.id),
            product_id=int(product_id),
            customer_id=int(customer_id) if customer_id is not None else None,
            listing_id=int(listing_id) if listing_id is not None else None,
            reason=reason,
            candidates=candidates,
            status=QUEUE_OPEN,
            evidence=evidence,
        )
        session.add(row)
    else:
        row.reason = reason
        row.candidates = candidates
        row.evidence = evidence
        if listing_id is not None:
            row.listing_id = int(listing_id)
        session.add(row)
    session.flush()


def remember_link(
    session: Session,
    *,
    site: SiteConfig,
    product_id: int,
    url: str,
    status: str,
    evidence: dict[str, Any],
    actor: str | None,
) -> ListingLink | None:
    """Store a confirm, reject, or stale decision. One confirmed link per site and product."""
    if site.id is None or not url:
        return None
    if status == LINK_REJECTED and url in _rejected_urls(session, site.id, product_id):
        return None
    if status == LINK_CONFIRMED:
        current = confirmed_link(session, site.id, product_id)
        if current is not None and current.url != url:
            current.status = LINK_STALE
            session.add(current)
        elif current is not None:
            current.evidence = evidence
            current.decided_by = actor
            session.add(current)
            session.flush()
            return current
    row = session.scalars(
        select(ListingLink).where(
            ListingLink.site_id == int(site.id),
            ListingLink.product_id == int(product_id),
            ListingLink.url == url,
        )
    ).first()
    if isinstance(row, ListingLink):
        row.status = status
        row.evidence = evidence
        row.decided_by = actor
    else:
        row = ListingLink(
            tenant_id=site.tenant_id,
            site_id=int(site.id),
            product_id=int(product_id),
            url=url,
            status=status,
            evidence=evidence,
            decided_by=actor,
        )
        session.add(row)
    session.flush()
    return row


def apply_url_to_listing(session: Session, listing: CustomerListing, url: str) -> str | None:
    """Point the listing at a confirmed product page. A URL another listing already holds is left."""
    new_url = url.strip()[:1024]
    if not new_url or new_url == listing.url:
        return None
    other = session.scalar(
        select(CustomerListing.id).where(
            CustomerListing.customer_id == listing.customer_id,
            CustomerListing.url == new_url,
            CustomerListing.id != listing.id,
        )
    )
    if other is not None:
        return "url_conflict"
    listing.url = new_url
    session.add(listing)
    return None


def learn_link(
    session: Session,
    listing: CustomerListing,
    site: SiteConfig,
    *,
    http_get,
    actor: str | None = None,
) -> dict[str, Any]:
    """Find or reuse the product page. Does not build a URL from the report stock code."""
    product_id = getattr(listing, "product_id", None)
    if product_id is None or site.id is None:
        return {"status": "skipped", "reason": "no_product" if product_id is None else "site_not_stored"}
    product = session.get(DimProduct, int(product_id))
    if not isinstance(product, DimProduct):
        return {"status": "skipped", "reason": "no_product"}
    if _not_on_site(session, site.id, product.id):
        return {"status": "not_on_site"}
    current = confirmed_link(session, site.id, product.id)
    if current is not None:
        return {"status": "confirmed", "url": current.url, "source": "remembered"}

    rejected = _rejected_urls(session, site.id, product.id)
    module = adapter_module(site.adapter_key)
    if module is not None and module.READS_STORED_URL:
        status, body = http_get(listing.url)
        facts = page_facts_from_html(body)
        how = corroboration(facts, product)
        if how and listing.url not in rejected:
            remember_link(
                session,
                site=site,
                product_id=int(product.id),
                url=listing.url,
                status=LINK_CONFIRMED,
                evidence={"corroboration": how, "stock_code": listing.external_id},
                actor=actor or "learned",
            )
            _close_open(session, site.id, product.id, QUEUE_CONFIRMED, actor)
            return {"status": "confirmed", "url": listing.url, "corroboration": how}
        queue_case(
            session,
            site=site,
            product_id=int(product.id),
            customer_id=listing.customer_id,
            listing_id=listing.id,
            reason="not_corroborated" if (facts["barcodes"] or facts["models"]) else "no_match",
            candidates=[],
            evidence={"http_status": status, "stock_code": listing.external_id},
        )
        return {"status": "queued", "reason": "not_corroborated" if facts["barcodes"] or facts["models"] else "no_match"}

    status, body, flags = rest_fetch(
        site,
        url=listing.url,
        http_get=http_get,
        external_id=None,
        ean=product.ean or product.upc,
        known_page_id=None,
        models=product_models(product),
    )
    data = parse_body(body)
    page_url = None
    if flags.get("resolved_page_id"):
        canon = (data or {}).get("desktop_href") if isinstance(data, dict) else None
        page_url = product_url(site, str(flags["resolved_page_id"]), canonical_url=str(canon) if canon else None)
    how = flags.get("corroboration")
    if how and page_url and page_url not in rejected and isinstance(data, dict):
        facts = page_facts_from_json(data)
        if corroboration(facts, product) == how or how in {"barcode", "model"}:
            remember_link(
                session,
                site=site,
                product_id=int(product.id),
                url=page_url,
                status=LINK_CONFIRMED,
                evidence={"corroboration": how, "stock_code": listing.external_id, "page_facts": facts},
                actor=actor or "learned",
            )
            conflict = apply_url_to_listing(session, listing, page_url)
            _close_open(session, site.id, product.id, QUEUE_CONFIRMED, actor)
            return {"status": "confirmed", "url": page_url, "corroboration": how, "conflict": conflict}

    reason = "not_corroborated" if flags.get("reason") == "barcode_hit_not_corroborated" else (
        "ambiguous" if int(flags.get("barcode_result_count") or 0) > 1 else "no_match"
    )
    candidates = []
    for hit in flags.get("candidates") or []:
        if isinstance(hit, dict) and hit.get("page_id"):
            built = product_url(site, str(hit["page_id"]), slug=hit.get("slug"))
            if built and built not in rejected:
                candidates.append({"url": built, "title": hit.get("title"), "page_id": hit["page_id"]})
    queue_case(
        session,
        site=site,
        product_id=int(product.id),
        customer_id=listing.customer_id,
        listing_id=listing.id,
        reason=reason,
        candidates=candidates,
        evidence={"fetch_reason": flags.get("reason"), "http_status": status, "stock_code": listing.external_id},
    )
    return {"status": "queued", "reason": reason, "candidates": candidates}


def note_fetch(
    session: Session,
    listing: Any,
    site: SiteConfig | None,
    *,
    fetch_flags: dict[str, Any],
    body: str,
) -> None:
    """Remember a corroborated page from a fetch that already happened, or queue the miss.

    No extra request. A report stock code is stored on the evidence and is not the link.
    """
    if not isinstance(listing, CustomerListing) or site is None or site.id is None or not listing.product_id:
        return
    product = session.get(DimProduct, int(listing.product_id))
    if not isinstance(product, DimProduct):
        return
    mark_stale_if_page_disagrees(session, listing, site, body)
    how = fetch_flags.get("corroboration")
    page_id = fetch_flags.get("resolved_page_id")
    if how in {"barcode", "model"} and page_id:
        data = parse_body(body) or {}
        canon = data.get("desktop_href") if isinstance(data, dict) else None
        url = product_url(site, str(page_id), canonical_url=str(canon) if canon else None)
        if url and url not in _rejected_urls(session, site.id, product.id):
            remember_link(
                session,
                site=site,
                product_id=int(product.id),
                url=url,
                status=LINK_CONFIRMED,
                evidence={"corroboration": how, "stock_code": listing.external_id},
                actor="learned",
            )
            apply_url_to_listing(session, listing, url)
            _close_open(session, site.id, product.id, QUEUE_CONFIRMED, "learned")
        return
    reason_flag = fetch_flags.get("reason")
    if reason_flag == "barcode_hit_not_corroborated":
        reason = "not_corroborated"
    elif reason_flag == "barcode_not_unique_or_missing" and int(fetch_flags.get("barcode_result_count") or 0) > 1:
        reason = "ambiguous"
    elif reason_flag == "barcode_not_unique_or_missing":
        reason = "no_match"
    else:
        return
    candidates = []
    for hit in fetch_flags.get("candidates") or []:
        if isinstance(hit, dict) and hit.get("page_id"):
            built = product_url(site, str(hit["page_id"]), slug=hit.get("slug"))
            if built:
                candidates.append({"url": built, "title": hit.get("title"), "page_id": hit["page_id"]})
    queue_case(
        session,
        site=site,
        product_id=int(product.id),
        customer_id=listing.customer_id,
        listing_id=listing.id,
        reason=reason,
        candidates=candidates,
        evidence={"fetch_reason": reason_flag, "stock_code": listing.external_id},
    )


def mark_stale_if_page_disagrees(
    session: Session,
    listing: CustomerListing,
    site: SiteConfig | None,
    body: str,
) -> None:
    """A confirmed link whose page is a different product is stale, and goes back to the queue."""
    if site is None or site.id is None or not getattr(listing, "product_id", None):
        return
    if not isinstance(listing, CustomerListing):
        return
    product = session.get(DimProduct, int(listing.product_id))
    if not isinstance(product, DimProduct):
        return
    current = confirmed_link(session, site.id, product.id)
    if current is None:
        return
    data = parse_body(body)
    facts = page_facts_from_json(data) if isinstance(data, dict) else page_facts_from_html(body)
    if not facts["barcodes"] and not facts["models"]:
        return
    if corroboration(facts, product):
        return
    current.status = LINK_STALE
    session.add(current)
    queue_case(
        session,
        site=site,
        product_id=int(product.id),
        customer_id=listing.customer_id,
        listing_id=listing.id,
        reason="stale",
        candidates=[{"url": current.url}],
        evidence={"page_facts": facts},
    )


def _close_open(session: Session, site_id: int, product_id: int, status: str, actor: str | None) -> None:
    row = _open_queue(session, site_id, product_id)
    if row is None:
        return
    row.status = status
    row.updated_by = actor
    session.add(row)


def decide_queue(
    session: Session,
    row: ListingLinkQueue,
    *,
    action: str,
    url: str | None,
    actor: str | None,
) -> ListingLinkQueue:
    if row.status != QUEUE_OPEN:
        raise ValueError(f"queue item is {row.status}")
    site_row_id = int(row.site_id)
    from app.services.listing_capture.sites import get_site, site_config_from_row

    site_row = get_site(session, site_row_id)
    if site_row is None:
        raise ValueError("site not found")
    site = site_config_from_row(site_row)
    if action == "not_on_site":
        row.status = QUEUE_NOT_ON_SITE
        row.updated_by = actor
        session.add(row)
        session.flush()
        return row
    chosen = (url or "").strip()
    if not chosen:
        raise ValueError("url required")
    if action == "reject":
        remember_link(
            session,
            site=site,
            product_id=int(row.product_id),
            url=chosen,
            status=LINK_REJECTED,
            evidence={"queue_id": row.id},
            actor=actor,
        )
        row.status = QUEUE_REJECTED
    elif action == "confirm":
        remember_link(
            session,
            site=site,
            product_id=int(row.product_id),
            url=chosen,
            status=LINK_CONFIRMED,
            evidence={"queue_id": row.id, "steward": True},
            actor=actor,
        )
        if row.listing_id is not None:
            listing = session.get(CustomerListing, int(row.listing_id))
            if isinstance(listing, CustomerListing):
                apply_url_to_listing(session, listing, chosen)
        row.status = QUEUE_CONFIRMED
    else:
        raise ValueError(f"unknown action: {action}")
    row.updated_by = actor
    session.add(row)
    session.flush()
    return row


def list_open_queue(session: Session) -> list[ListingLinkQueue]:
    rows = list(
        session.scalars(
            select(ListingLinkQueue).where(ListingLinkQueue.status == QUEUE_OPEN).order_by(ListingLinkQueue.id)
        ).all()
    )
    return [r for r in rows if isinstance(r, ListingLinkQueue)]
