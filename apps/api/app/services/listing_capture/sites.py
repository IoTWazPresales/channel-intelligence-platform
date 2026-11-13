"""Listing sites and each customer's seller identity per site (tenant data, edited in the app)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.dimensions import DimCustomer
from app.models.listing_site import ListingSite, ListingSiteSeller
from app.services.listing_capture.adapters import (
    SiteConfig,
    SiteSeller,
    adapter_keys,
    missing_fields,
)

SITE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
# ``listing_site_seller.updated_by`` when discovery took the seller identity from the customer's
# name. Any later save (steward, seed) replaces it, and the identity is then configured.
INFERRED_SELLER_ACTOR = "listing-autoconfigure:customer-name"
MAX_RATE_LIMIT_SECONDS = 3600.0
EDITABLE_FIELDS: tuple[str, ...] = (
    "display_name",
    "adapter_key",
    "product_url_pattern",
    "page_id_pattern",
    "search_url_pattern",
    "details_url_pattern",
    "first_party_seller",
    "rate_limit_seconds",
    "is_active",
)


def _clean_list(values: Iterable[Any] | None, *, max_len: int = 256) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = re.sub(r"\s+", " ", str(value or "")).strip()[:max_len]
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


def site_config_from_row(row: ListingSite) -> SiteConfig:
    sellers = tuple(
        SiteSeller(
            customer_id=int(s.customer_id),
            names=tuple(_clean_list(s.seller_names)),
            ids=tuple(_clean_list(s.seller_ids)),
            inferred=s.updated_by == INFERRED_SELLER_ACTOR,
        )
        for s in (row.sellers or [])
    )
    rate = row.rate_limit_seconds
    return SiteConfig(
        id=int(row.id) if row.id is not None else None,
        tenant_id=str(row.tenant_id or "default"),
        site_key=str(row.site_key),
        display_name=str(row.display_name or row.site_key),
        adapter_key=row.adapter_key or None,
        product_url_pattern=row.product_url_pattern or None,
        page_id_pattern=row.page_id_pattern or None,
        search_url_pattern=row.search_url_pattern or None,
        details_url_pattern=row.details_url_pattern or None,
        first_party_seller=row.first_party_seller or None,
        rate_limit_seconds=float(rate) if rate is not None else None,
        is_active=bool(row.is_active),
        sellers=sellers,
    )


def _site_rows(session: Session, stmt) -> list[ListingSite]:
    rows = list(session.scalars(stmt.options(selectinload(ListingSite.sellers))).all())
    # A mocked session returns mocks: no site is configured (the safe direction: nothing is fetched).
    return [r for r in rows if isinstance(r, ListingSite)]


def customer_tenant(session: Session, customer_id: int | None) -> str | None:
    if customer_id is None:
        return None
    tenant = session.scalar(select(DimCustomer.tenant_id).where(DimCustomer.id == int(customer_id)))
    return str(tenant) if isinstance(tenant, str) and tenant else None


def site_for_customer(session: Session, customer_id: int | None, site_key: str | None) -> SiteConfig | None:
    """The site ``site_key`` in the customer's tenant, or None when it is not a known site."""
    key = (site_key or "").strip().lower()
    tenant = customer_tenant(session, customer_id)
    if not key or tenant is None:
        return None
    rows = _site_rows(
        session,
        select(ListingSite).where(ListingSite.tenant_id == tenant, ListingSite.site_key == key),
    )
    return site_config_from_row(rows[0]) if rows else None


def site_for_listing(session: Session, listing: Any) -> SiteConfig | None:
    return site_for_customer(session, getattr(listing, "customer_id", None), getattr(listing, "marketplace", None))


class SiteResolver:
    """Sites for many listings in one read (poller, quality backfill)."""

    def __init__(self, sites: dict[tuple[str, str], SiteConfig], tenants: dict[int, str]) -> None:
        self._sites = sites
        self._tenants = tenants

    @classmethod
    def load(cls, session: Session, listings: Iterable[Any]) -> "SiteResolver":
        customer_ids = sorted({int(c) for c in (getattr(l, "customer_id", None) for l in listings) if c is not None})
        tenants: dict[int, str] = {}
        if customer_ids:
            for cid, tenant in session.execute(
                select(DimCustomer.id, DimCustomer.tenant_id).where(DimCustomer.id.in_(customer_ids))
            ).all():
                tenants[int(cid)] = str(tenant or "default")
        sites = {(s.tenant_id, s.site_key): s for s in (site_config_from_row(r) for r in _site_rows(session, select(ListingSite)))}
        return cls(sites, tenants)

    def tenant_for(self, listing: Any) -> str | None:
        cid = getattr(listing, "customer_id", None)
        return self._tenants.get(int(cid)) if cid is not None else None

    def site_for(self, listing: Any) -> SiteConfig | None:
        tenant = self.tenant_for(listing)
        key = (getattr(listing, "marketplace", None) or "").strip().lower()
        if tenant is None or not key:
            return None
        return self._sites.get((tenant, key))


# ---------------------------------------------------------------- validation


def _validate_pattern(name: str, value: str | None, *, placeholder: str) -> None:
    if not value:
        return
    if not re.match(r"^https?://[^/\s{}]+", value):
        raise ValueError(f"{name} must start with http:// or https:// and a host")
    if placeholder not in value:
        raise ValueError(f"{name} must contain {placeholder}")


def _validate_page_id_pattern(value: str | None) -> None:
    if not value:
        return
    try:
        compiled = re.compile(value)
    except re.error as exc:
        raise ValueError(f"page_id_pattern is not a valid pattern: {exc}") from exc
    if compiled.groups != 1:
        raise ValueError("page_id_pattern must have exactly one capture group (the page id)")


def _normalized_fields(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in EDITABLE_FIELDS:
        if key not in raw:
            continue
        value = raw[key]
        if key == "is_active":
            out[key] = bool(value)
        elif key == "rate_limit_seconds":
            if value is None or str(value).strip() == "":
                out[key] = None
            else:
                try:
                    seconds = Decimal(str(value))
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError("rate_limit_seconds must be a number") from exc
                if seconds < 0 or seconds > Decimal(str(MAX_RATE_LIMIT_SECONDS)):
                    raise ValueError(f"rate_limit_seconds must be between 0 and {MAX_RATE_LIMIT_SECONDS:g}")
                out[key] = seconds
        else:
            text = str(value).strip() if value is not None else ""
            out[key] = text or None
    if "display_name" in out and not out["display_name"]:
        raise ValueError("display_name required")
    if out.get("adapter_key") and out["adapter_key"] not in adapter_keys():
        raise ValueError(f"unknown adapter_key: {out['adapter_key']} (known: {', '.join(adapter_keys())})")
    if "product_url_pattern" in out:
        _validate_pattern("product_url_pattern", out["product_url_pattern"], placeholder="{page_id}")
    if "details_url_pattern" in out:
        _validate_pattern("details_url_pattern", out["details_url_pattern"], placeholder="{page_id}")
    if "search_url_pattern" in out:
        _validate_pattern("search_url_pattern", out["search_url_pattern"], placeholder="{query}")
    if "page_id_pattern" in out:
        _validate_page_id_pattern(out["page_id_pattern"])
    return out


# ---------------------------------------------------------------- reads / writes


def list_sites(session: Session) -> list[ListingSite]:
    return _site_rows(session, select(ListingSite).order_by(ListingSite.site_key))


def get_site(session: Session, site_id: int) -> ListingSite | None:
    rows = _site_rows(session, select(ListingSite).where(ListingSite.id == int(site_id)))
    return rows[0] if rows else None


def create_site(session: Session, *, tenant_id: str, site_key: str, fields: dict[str, Any], actor: str | None) -> ListingSite:
    key = (site_key or "").strip().lower()
    if not SITE_KEY_RE.match(key):
        raise ValueError("site_key must be 1-32 lowercase letters, digits, '-' or '_'")
    exists = session.scalar(
        select(ListingSite.id).where(ListingSite.tenant_id == tenant_id, ListingSite.site_key == key)
    )
    if exists is not None:
        raise ValueError(f"site {key} already exists")
    values = _normalized_fields({"display_name": key, **fields})
    row = ListingSite(tenant_id=tenant_id, site_key=key, updated_by=actor, **values)
    session.add(row)
    session.flush()
    return row


def update_site(session: Session, row: ListingSite, *, fields: dict[str, Any], actor: str | None) -> ListingSite:
    for key, value in _normalized_fields(fields).items():
        setattr(row, key, value)
    row.updated_by = actor
    session.add(row)
    session.flush()
    return row


def set_site_seller(
    session: Session,
    row: ListingSite,
    *,
    customer_id: int,
    seller_names: Iterable[Any] | None,
    seller_ids: Iterable[Any] | None,
    actor: str | None,
) -> ListingSiteSeller:
    tenant = customer_tenant(session, customer_id)
    if tenant is None:
        raise ValueError(f"customer {customer_id} not found")
    if tenant != row.tenant_id:
        raise ValueError("customer and site belong to different tenants")
    names = _clean_list(seller_names)
    ids = _clean_list(seller_ids, max_len=128)
    if not names and not ids:
        raise ValueError("give at least one seller name or seller id")
    seller = next((s for s in row.sellers if int(s.customer_id) == int(customer_id)), None)
    if seller is None:
        seller = ListingSiteSeller(site_id=row.id, tenant_id=row.tenant_id, customer_id=int(customer_id))
        row.sellers.append(seller)
    seller.seller_names = names
    seller.seller_ids = ids
    seller.updated_by = actor
    session.add(seller)
    session.flush()
    return seller


def delete_site_seller(session: Session, row: ListingSite, *, customer_id: int) -> bool:
    seller = next((s for s in row.sellers if int(s.customer_id) == int(customer_id)), None)
    if seller is None:
        return False
    row.sellers.remove(seller)
    session.delete(seller)
    session.flush()
    return True


def site_to_dict(row: ListingSite, *, customers: dict[int, tuple[str, str]] | None = None) -> dict[str, Any]:
    config = site_config_from_row(row)
    missing = missing_fields(config)
    sellers = []
    for s in sorted(row.sellers or [], key=lambda x: int(x.customer_id)):
        label = (customers or {}).get(int(s.customer_id))
        sellers.append(
            {
                "customer_id": int(s.customer_id),
                "customer_code": label[0] if label else None,
                "customer_name": label[1] if label else None,
                "seller_names": _clean_list(s.seller_names),
                "seller_ids": _clean_list(s.seller_ids),
                "updated_by": s.updated_by,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
        )
    return {
        "id": int(row.id),
        "site_key": row.site_key,
        "display_name": row.display_name,
        "adapter_key": row.adapter_key,
        "product_url_pattern": row.product_url_pattern,
        "page_id_pattern": row.page_id_pattern,
        "search_url_pattern": row.search_url_pattern,
        "details_url_pattern": row.details_url_pattern,
        "first_party_seller": row.first_party_seller,
        "rate_limit_seconds": float(row.rate_limit_seconds) if row.rate_limit_seconds is not None else None,
        "is_active": bool(row.is_active),
        "configured": bool(row.is_active) and not missing,
        "missing_fields": missing,
        "sellers": sellers,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
