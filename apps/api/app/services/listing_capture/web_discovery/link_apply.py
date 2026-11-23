"""S4 writes behind S1's Apply transaction. No network and no independent commit."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cst_listing_seed import CstListingSeed
from app.models.customer_web_site import (
    WEB_SITE_CONFIRMED,
    WEB_SITE_REJECTED,
    CustomerWebSite,
)
from app.models.dimensions import DimCustomer
from app.models.listing_capture import CustomerListing
from app.models.listing_link import (
    LINK_CONFIRMED,
    LINK_REJECTED,
    QUEUE_NOT_ON_SITE,
    QUEUE_OPEN,
    QUEUE_REJECTED,
    ListingLink,
    ListingLinkQueue,
)
from app.models.listing_site import ListingSite
from app.services.listing_capture import discovery
from app.services.listing_capture.links import (
    listing_link_state,
    proposal_link_state,
    queue_case,
    queue_listing_case,
    remember_link,
)
from app.services.listing_capture.sites import get_site, site_config_from_row, update_site
from app.services.listing_capture.web_discovery.linking import (
    AUTO_LINK,
    QUEUE,
    CatalogueIndex,
    LinkDecision,
    decide,
    feed_seed_decision,
)
from app.services.listing_capture.web_discovery.scoring import normalize_host


class ChangedSincePreview(ValueError):
    pass


def _skip(counts: dict[str, Any], entry: dict[str, Any]) -> None:
    counts["skipped"].append(
        {
            "item_id": str(entry.get("item_id") or ""),
            "reason": "changed_since_preview",
        }
    )


def _candidate_ids(values: list[Any]) -> list[int]:
    return sorted(
        {
            int(value["product_id"]) if isinstance(value, dict) else int(value)
            for value in values
            if not isinstance(value, dict) or value.get("product_id") is not None
        }
    )


def _matches(entry: dict[str, Any], decision: LinkDecision) -> bool:
    return (
        entry.get("outcome") == decision.outcome
        and entry.get("product_id") == decision.product_id
        and entry.get("how") == decision.how
        and entry.get("reason") == decision.reason
        and _candidate_ids(entry.get("candidates") or []) == sorted(decision.candidates)
    )


def _available(
    session: Session,
    site: ListingSite,
    product_id: int,
    url: str,
    *,
    preview_id: str,
    listing: bool,
) -> bool:
    links = session.scalars(
        select(ListingLink).where(
            ListingLink.tenant_id == site.tenant_id,
            ListingLink.site_id == site.id,
            ListingLink.product_id == product_id,
        )
    ).all()
    for link in links:
        if link.status == LINK_REJECTED and link.url == url:
            return False
        if link.status == LINK_CONFIRMED:
            if link.url != url:
                return False
            undo = (link.evidence or {}).get("undo") or {}
            if not listing and undo.get("preview_id") != preview_id:
                return False
    return session.scalar(
        select(ListingLinkQueue.id)
        .where(
            ListingLinkQueue.tenant_id == site.tenant_id,
            ListingLinkQueue.site_id == site.id,
            ListingLinkQueue.product_id == product_id,
            ListingLinkQueue.status.in_((QUEUE_OPEN, QUEUE_NOT_ON_SITE, QUEUE_REJECTED)),
        )
        .limit(1)
    ) is None


def _save_auto(
    session: Session,
    *,
    site: ListingSite,
    decision: LinkDecision,
    url: str,
    preview_id: str,
    item_id: str,
    actor: str,
    listing: CustomerListing | None = None,
    customer: DimCustomer | None = None,
    capture: dict[str, Any] | None = None,
    index: CatalogueIndex,
) -> tuple[ListingLink, bool]:
    product_id = int(decision.product_id)
    old = session.scalar(
        select(ListingLink)
        .where(
            ListingLink.tenant_id == site.tenant_id,
            ListingLink.site_id == site.id,
            ListingLink.product_id == product_id,
            ListingLink.url == url,
        )
        .with_for_update()
    )
    previous = None
    if old is not None:
        previous = {
            "status": old.status,
            "evidence": deepcopy(old.evidence),
            "decided_by": old.decided_by,
        }
    existing_undo = deepcopy((old.evidence or {}).get("undo")) if old is not None else None
    if (
        existing_undo
        and existing_undo.get("preview_id") == preview_id
        and not existing_undo.get("undone_at")
    ):
        undo = existing_undo
    else:
        undo = {
            "preview_id": preview_id,
            "previous_link": previous,
            "listings": [],
            "proposals": [],
            "items": [],
        }
    undo["items"].append(
        {"item_id": item_id, "how": decision.how, "evidence": deepcopy(decision.evidence)}
    )

    if listing is not None:
        before = listing_link_state(listing)
        listing.product_id = product_id
        session.add(listing)
        session.flush()
        undo["listings"].append({"before": before, "after": listing_link_state(listing)})

    created = False
    captured = {**(capture or {}), "url": url}
    captured["corroboration"] = "barcode" if decision.how == "gtin" else decision.how
    if customer is not None and discovery._complete_capture(captured):  # noqa: SLF001
        external_id = f"discovery:{product_id}:{sha256(url.encode('utf-8')).hexdigest()}"
        exact_seed = session.scalar(
            select(CstListingSeed).where(
                CstListingSeed.customer_id == customer.id,
                CstListingSeed.marketplace == site.site_key,
                CstListingSeed.external_id == external_id,
            )
        )
        proposal = exact_seed or discovery._proposed_seed(  # noqa: SLF001
            session,
            customer_id=int(customer.id),
            site_key=site.site_key,
            product_id=product_id,
        )
        before = proposal_link_state(proposal) if proposal is not None else None
        created = discovery._store_proposal(  # noqa: SLF001
            session,
            customer=customer,
            product=index.products[product_id],
            row=site,
            captured=captured,
            apply=True,
        )
        proposal = proposal or discovery._proposed_seed(  # noqa: SLF001
            session,
            customer_id=int(customer.id),
            site_key=site.site_key,
            product_id=product_id,
        )
        if proposal is not None:
            after = proposal_link_state(proposal)
            if after != before:
                undo["proposals"].append({"before": before, "after": after})

    # _store_proposal also remembers the link. Write the complete S4 evidence last.
    link = remember_link(
        session,
        site=site_config_from_row(site),
        product_id=product_id,
        url=url,
        status=LINK_CONFIRMED,
        evidence={
            "source": "discovery_v2",
            "how": decision.how,
            "facts": deepcopy(decision.evidence.get("facts") or {}),
            "evidence": deepcopy(decision.evidence),
            "undo": undo,
        },
        actor=actor,
    )
    if link is None:
        raise ChangedSincePreview()
    return link, created


def _receipt(counts: dict[str, Any], link: ListingLink, entry: dict[str, Any]) -> None:
    counts.setdefault("auto_links", []).append(
        {
            "item_id": str(entry.get("item_id") or ""),
            "link_id": int(link.id),
            "product_id": int(link.product_id),
            "undo_url": f"/api/v1/listing-capture/links/{link.id}/undo",
        }
    )


def _eligible_site(
    session: Session,
    tenant_id: str,
    customer: DimCustomer,
    block: dict[str, Any],
) -> ListingSite | None:
    domain = normalize_host(str(block.get("domain") or ""))
    site = session.scalar(
        select(ListingSite)
        .where(
            ListingSite.tenant_id == tenant_id,
            ListingSite.site_key == block.get("site_key"),
        )
        .with_for_update()
    )
    if site is None or not domain:
        return None
    association = session.scalar(
        select(CustomerWebSite).where(
            CustomerWebSite.tenant_id == tenant_id,
            CustomerWebSite.customer_id == customer.id,
            CustomerWebSite.domain == domain,
        )
    )
    if association is not None:
        if association.status == WEB_SITE_REJECTED:
            return None
        if association.status == WEB_SITE_CONFIRMED and association.site_id == site.id:
            return get_site(session, int(site.id))
    urls = session.scalars(
        select(CustomerListing.url).where(
            CustomerListing.customer_id == customer.id,
            CustomerListing.marketplace == site.site_key,
        )
    ).all()
    if any(normalize_host(urlsplit(url).hostname or "") == domain for url in urls):
        return get_site(session, int(site.id))
    return None


def _apply_page(
    session: Session,
    *,
    site: ListingSite,
    customer: DimCustomer,
    entry: dict[str, Any],
    domain: str,
    index: CatalogueIndex,
    preview_id: str,
    actor: str,
    counts: dict[str, Any],
) -> None:
    expected = entry.get("product_id")
    if expected not in index.products:
        raise ChangedSincePreview()
    url = str(entry.get("url") or "")
    if (
        urlsplit(url).scheme not in ("http", "https")
        or normalize_host(urlsplit(url).hostname or "") != domain
    ):
        raise ChangedSincePreview()
    decision = decide(entry.get("facts") or {}, index, expected_product_id=int(expected))
    # Page product_id denotes the searched-for product even on a queued mismatch.
    compared = {**entry, "product_id": decision.product_id}
    if not _matches(compared, decision):
        raise ChangedSincePreview()
    if not _available(
        session,
        site,
        int(expected),
        url,
        preview_id=preview_id,
        listing=False,
    ):
        raise ChangedSincePreview()
    if decision.outcome == AUTO_LINK:
        link, created = _save_auto(
            session,
            site=site,
            decision=decision,
            url=url,
            preview_id=preview_id,
            item_id=str(entry.get("item_id") or ""),
            actor=actor,
            customer=customer,
            capture=entry.get("capture") or {},
            index=index,
        )
        counts["pages_linked"] += 1
        counts["proposals_created"] += int(created)
        _receipt(counts, link, entry)
    elif decision.outcome == QUEUE:
        queue_case(
            session,
            site=site_config_from_row(site),
            product_id=int(expected),
            customer_id=int(customer.id),
            listing_id=None,
            reason=str(decision.reason),
            candidates=[
                {"url": url, **candidate}
                for candidate in index.candidate_labels(decision.candidates)
            ] or [{"url": url}],
            evidence={"source": "discovery_v2", **decision.evidence},
        )
        counts["pages_queued"] += 1


def _learn_patterns(
    session: Session, site: ListingSite, block: dict[str, Any], actor: str
) -> None:
    learned = dict(block.get("learned") or {})
    search = block.get("search_pattern") or {}
    if search.get("value") and search.get("how") != "stored":
        learned.setdefault("search_url_pattern", search["value"])
    fields = {}
    domain = normalize_host(str(block.get("domain") or ""))
    for name in ("search_url_pattern", "product_url_pattern", "page_id_pattern"):
        value = learned.get(name)
        if not value or getattr(site, name, None):
            continue
        if name != "page_id_pattern":
            if normalize_host(urlsplit(str(value)).hostname or "") != domain:
                continue
        fields[name] = value
    if fields:
        try:
            with session.begin_nested():
                update_site(session, site, fields=fields, actor=actor)
        except ValueError:
            # Invalid learned configuration cannot change the reviewed links.
            return


def _listing_decision(
    session: Session,
    listing: CustomerListing,
    entry: dict[str, Any],
    index: CatalogueIndex,
) -> LinkDecision:
    evidence = deepcopy(entry.get("evidence") or {})
    if entry.get("how") == "feed_seed":
        decision = feed_seed_decision(session, listing, index)
        if (
            decision is None
            or decision.evidence.get("feed_seed") != evidence.get("feed_seed")
        ):
            raise ChangedSincePreview()
        return decision
    if entry.get("reason") == "page_unreadable":
        if evidence.get("http_status") == 200 and not evidence.get("refused"):
            raise ChangedSincePreview()
        return LinkDecision(QUEUE, reason="page_unreadable", evidence=evidence)
    if evidence.get("http_status") != 200 or evidence.get("refused"):
        raise ChangedSincePreview()
    facts = entry.get("facts") or {}
    if facts != evidence.get("facts"):
        raise ChangedSincePreview()
    exact = decide(facts, index)
    return LinkDecision(
        exact.outcome,
        product_id=exact.product_id,
        how=exact.how,
        candidates=exact.candidates,
        reason=exact.reason,
        evidence={**evidence, **exact.evidence},
    )


def _apply_listing(
    session: Session,
    *,
    tenant_id: str,
    entry: dict[str, Any],
    index: CatalogueIndex,
    preview_id: str,
    actor: str,
    counts: dict[str, Any],
) -> None:
    listing = session.scalar(
        select(CustomerListing)
        .join(DimCustomer, DimCustomer.id == CustomerListing.customer_id)
        .where(
            CustomerListing.id == int(entry["listing_id"]),
            DimCustomer.tenant_id == tenant_id,
            DimCustomer.merged_into_customer_id.is_(None),
        )
        .with_for_update(of=CustomerListing)
        .execution_options(populate_existing=True)
    )
    if (
        listing is None
        or listing.product_id is not None
        or listing_link_state(listing) != entry.get("listing_state")
        or listing.url != entry.get("url")
        or listing.customer_id != entry.get("customer_id")
    ):
        raise ChangedSincePreview()
    site = session.scalar(
        select(ListingSite)
        .where(
            ListingSite.tenant_id == tenant_id,
            ListingSite.id == entry.get("site_id"),
            ListingSite.site_key == str(listing.marketplace).strip().lower(),
        )
        .with_for_update()
    )
    if site is None:
        raise ChangedSincePreview()
    existing = session.scalar(
        select(ListingLinkQueue.id)
        .where(
            ListingLinkQueue.tenant_id == tenant_id,
            ListingLinkQueue.listing_id == listing.id,
            ListingLinkQueue.product_id.is_(None),
            ListingLinkQueue.status.in_((QUEUE_OPEN, QUEUE_NOT_ON_SITE, QUEUE_REJECTED)),
        )
        .limit(1)
    )
    if existing is not None:
        raise ChangedSincePreview()
    decision = _listing_decision(session, listing, entry, index)
    if not _matches(entry, decision):
        raise ChangedSincePreview()
    site = get_site(session, int(site.id))
    if site is None:
        raise ChangedSincePreview()
    if decision.outcome == AUTO_LINK:
        if not _available(
            session,
            site,
            int(decision.product_id),
            listing.url,
            preview_id=preview_id,
            listing=True,
        ):
            raise ChangedSincePreview()
        link, _created = _save_auto(
            session,
            site=site,
            decision=decision,
            url=listing.url,
            preview_id=preview_id,
            item_id=str(entry.get("item_id") or ""),
            actor=actor,
            listing=listing,
            index=index,
        )
        counts["listings_linked"] += 1
        _receipt(counts, link, entry)
    elif decision.outcome == QUEUE:
        queue_listing_case(
            session,
            site=site_config_from_row(site),
            listing=listing,
            reason=str(decision.reason),
            candidates=index.candidate_labels(decision.candidates),
            evidence={
                **decision.evidence,
                "source": "discovery_v2",
                "listing_url": listing.url,
            },
        )
        counts["listings_queued"] += 1


def apply_link_items(
    session: Session,
    *,
    tenant_id: str,
    preview_id: str,
    result: dict[str, Any],
    actor: str,
    counts: dict[str, Any],
) -> None:
    """Called once inside S1's locked Apply transaction, after the site writes."""
    from sqlalchemy.exc import IntegrityError

    index = CatalogueIndex.load(session, tenant_id)
    for block in result.get("customers") or []:
        customer = session.scalar(
            select(DimCustomer).where(
                DimCustomer.id == int(block["customer_id"]),
                DimCustomer.tenant_id == tenant_id,
                DimCustomer.merged_into_customer_id.is_(None),
            )
        )
        for site_block in block.get("sites") or []:
            site = (
                _eligible_site(session, tenant_id, customer, site_block)
                if customer is not None
                else None
            )
            saved = False
            for entry in site_block.get("pages") or []:
                if entry.get("outcome") not in (AUTO_LINK, QUEUE):
                    continue
                if site is None:
                    _skip(counts, entry)
                    continue
                before = deepcopy(counts)
                try:
                    with session.begin_nested():
                        _apply_page(
                            session,
                            site=site,
                            customer=customer,
                            entry=entry,
                            domain=normalize_host(str(site_block.get("domain") or "")),
                            index=index,
                            preview_id=preview_id,
                            actor=actor,
                            counts=counts,
                        )
                    saved = True
                except (ChangedSincePreview, IntegrityError):
                    counts.clear()
                    counts.update(before)
                    _skip(counts, entry)
            if saved and site is not None:
                _learn_patterns(session, site, site_block, actor)

    for entry in result.get("listings") or []:
        if entry.get("outcome") not in (AUTO_LINK, QUEUE):
            continue
        before = deepcopy(counts)
        try:
            with session.begin_nested():
                _apply_listing(
                    session,
                    tenant_id=tenant_id,
                    entry=entry,
                    index=index,
                    preview_id=preview_id,
                    actor=actor,
                    counts=counts,
                )
        except (ChangedSincePreview, IntegrityError):
            counts.clear()
            counts.update(before)
            _skip(counts, entry)
