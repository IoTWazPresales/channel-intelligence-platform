"""Derive a product-page URL pattern from confirmed listing URLs.

The inputs are URLs the caller already treats as confirmed. This module does not
read the database, does not fetch a page, and does not name a retailer. A pattern
is returned only when every URL is one scheme, one host, one path length, no
query, and exactly one page-id slot. Anything else is no pattern.

A page-id prefix is kept only when it is a shared run of letters and the rest of
that segment is digits on every URL, so a shared letter run in front of a numeric
id stays a prefix, and a coincidental prefix inside an alphanumeric id does not.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.listing_site import ListingSite
from app.services.listing_capture.sites import (
    _validate_page_id_pattern,
    _validate_pattern,
    update_site,
)

NO_PATTERN = "no pattern in the confirmed URLs"
PATTERN_ACTOR = "listing-discovery"
WRITE_DATABASE = "cip_test"

_SLASH = chr(47)
_COLON = chr(58)


@dataclass(frozen=True)
class ListingUrlPattern:
    product_url_pattern: str
    page_id_pattern: str
    page_ids: tuple[str, ...]
    has_slug: bool

    def page_id(self, url: str) -> str | None:
        match = re.fullmatch(self.page_id_pattern, url)
        if not match or match.lastindex != 1:
            return None
        return match.group(1)

    def reproduces(self, url: str) -> bool:
        page_id = self.page_id(url)
        if not page_id:
            return False
        slug = _slug_in_url(self.product_url_pattern, url) if self.has_slug else None
        return fill_product_url(self, page_id, slug) == url


def derive_listing_url_pattern(urls: list[str]) -> ListingUrlPattern | None:
    """One pattern that reproduces every URL, or None when the URLs do not share one."""
    rows: list[tuple[str, str, tuple[str, ...]]] = []
    for raw in urls:
        text_url = (raw or "").strip()
        if not text_url:
            return None
        parts = urlsplit(text_url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return None
        if parts.query or parts.fragment:
            return None
        segments = tuple(segment for segment in parts.path.split(_SLASH) if segment != "")
        if not segments:
            return None
        rows.append((parts.scheme, parts.netloc, segments))
    if not rows:
        return None
    if len({row[0] for row in rows}) != 1 or len({row[1] for row in rows}) != 1:
        return None
    if len({len(row[2]) for row in rows}) != 1:
        return None

    width = len(rows[0][2])
    columns = [[row[2][index] for row in rows] for index in range(width)]
    roles: list[tuple[str, str, tuple[str, ...]]] = []
    for column in columns:
        if len(set(column)) == 1:
            roles.append(("literal", column[0], ()))
            continue
        prefix = _letter_prefix_before_digits(column)
        if prefix:
            roles.append(("page_id", prefix, tuple(value[len(prefix) :] for value in column)))
            continue
        roles.append(("vary", "", tuple(column)))

    page_at = [index for index, role in enumerate(roles) if role[0] == "page_id"]
    vary_at = [index for index, role in enumerate(roles) if role[0] == "vary"]
    if len(page_at) >= 2:
        return None
    if not page_at:
        if len(vary_at) != 1:
            return None
        only = vary_at[0]
        roles[only] = ("page_id", "", roles[only][2])
        vary_at = []
    elif len(vary_at) >= 2:
        return None

    origin = rows[0][0] + _COLON + _SLASH + _SLASH + rows[0][1]
    product_parts = [origin]
    regex_parts = [re.escape(origin)]
    page_ids: tuple[str, ...] = ()
    has_slug = False
    for role, prefix, values in roles:
        if role == "literal":
            product_parts.append(prefix)
            regex_parts.append(re.escape(prefix))
        elif role == "page_id":
            page_ids = values
            token = _token_class(values)
            product_parts.append(prefix + "{page_id}")
            regex_parts.append(re.escape(prefix) + "(" + token + ")")
        else:
            has_slug = True
            product_parts.append("{slug}")
            regex_parts.append("[^" + _SLASH + "]+")

    product = _SLASH.join(product_parts)
    page_id_pattern = "^" + _SLASH.join(regex_parts) + "$"
    try:
        compiled = re.compile(page_id_pattern)
    except re.error:
        return None
    if compiled.groups != 1:
        return None
    derived = ListingUrlPattern(
        product_url_pattern=product,
        page_id_pattern=page_id_pattern,
        page_ids=page_ids,
        has_slug=has_slug,
    )
    try:
        _validate_pattern("product_url_pattern", derived.product_url_pattern, placeholder="{page_id}")
        _validate_page_id_pattern(derived.page_id_pattern)
    except ValueError:
        return None
    if not page_ids or any(not derived.reproduces(row_url) for row_url in _stripped(urls)):
        return None
    return derived


def page_for_external_id(pattern: ListingUrlPattern | None, external_id: str | None) -> str:
    """A product URL filled from a confirmed pattern, or the honest no-pattern phrase.

    A slug cannot be invented from an external id. When every confirmed page id is
    digits, only a digit external id is the same token. Otherwise the external id
    must be one of the confirmed page ids. A wider token class is not a page we found.
    """
    if pattern is None or pattern.has_slug:
        return NO_PATTERN
    token = (external_id or "").strip()
    if not token or not pattern.page_ids:
        return NO_PATTERN
    if all(page_id.isdigit() for page_id in pattern.page_ids):
        if not token.isdigit():
            return NO_PATTERN
    elif token not in pattern.page_ids:
        return NO_PATTERN
    filled = fill_product_url(pattern, token, None)
    if not filled or pattern.page_id(filled) != token:
        return NO_PATTERN
    return filled


def fill_product_url(pattern: ListingUrlPattern, page_id: str, slug: str | None) -> str | None:
    product = pattern.product_url_pattern
    if pattern.has_slug:
        if not slug:
            return None
        product = product.replace("{slug}", slug)
    if "{page_id}" not in product:
        return None
    return product.replace("{page_id}", page_id)


def write_listing_url_pattern(
    session: Session,
    row: ListingSite,
    urls: list[str],
) -> dict[str, Any]:
    """Write the derived pattern onto a site row. Refuses every database except cip_test.

    On cip this returns without calling the site update. A URL set with no single
    pattern also leaves the row unchanged.
    """
    database = session.execute(text("SELECT current_database()")).scalar()
    database_name = str(database or "")
    if database_name != WRITE_DATABASE:
        return {"written": False, "reason": "refusing write on " + database_name, "database": database_name}
    derived = derive_listing_url_pattern(urls)
    if derived is None:
        return {"written": False, "reason": NO_PATTERN, "database": database_name}
    update_site(
        session,
        row,
        fields={
            "product_url_pattern": derived.product_url_pattern,
            "page_id_pattern": derived.page_id_pattern,
        },
        actor=PATTERN_ACTOR,
    )
    return {
        "written": True,
        "database": database_name,
        "product_url_pattern": derived.product_url_pattern,
        "page_id_pattern": derived.page_id_pattern,
        "actor": PATTERN_ACTOR,
    }


def _letter_prefix_before_digits(values: list[str]) -> str | None:
    shared = os.path.commonprefix(values)
    letters: list[str] = []
    for character in shared:
        if character.isalpha():
            letters.append(character)
        else:
            break
    prefix = "".join(letters)
    if not prefix:
        return None
    rests = [value[len(prefix) :] for value in values]
    if all(rest.isdigit() and rest for rest in rests):
        return prefix
    return None


def _token_class(values: tuple[str, ...]) -> str:
    if all(value.isdigit() for value in values):
        return r"\d+"
    if all(re.fullmatch(r"[A-Za-z0-9]+", value) for value in values):
        return r"[A-Za-z0-9]+"
    if all(re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in values):
        return r"[A-Za-z0-9_-]+"
    return "[^" + _SLASH + "]+"


def _slug_in_url(product_url_pattern: str, url: str) -> str | None:
    parts = urlsplit(url)
    segments = [segment for segment in parts.path.split(_SLASH) if segment != ""]
    pattern_segments = [segment for segment in urlsplit(product_url_pattern).path.split(_SLASH) if segment != ""]
    if len(segments) != len(pattern_segments):
        return None
    slugs = [live for live, slot in zip(segments, pattern_segments) if slot == "{slug}"]
    if len(slugs) != 1:
        return None
    return slugs[0]


def _stripped(urls: list[str]) -> list[str]:
    return [(url or "").strip() for url in urls]