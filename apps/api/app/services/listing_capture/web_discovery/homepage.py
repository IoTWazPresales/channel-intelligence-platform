"""Read the signals a home page gives about who runs it. Pure; stdlib ``html.parser`` only."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

_ORG_TYPES = frozenset(
    {"organization", "corporation", "localbusiness", "onlinestore", "store", "onlinebusiness"}
)


@dataclass
class HomeSignals:
    title: str | None = None
    og_site_name: str | None = None
    og_locale: str | None = None
    html_lang: str | None = None
    org_names: list[str] = field(default_factory=list)
    address_countries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "og_site_name": self.og_site_name,
            "og_locale": self.og_locale,
            "html_lang": self.html_lang,
            "org_names": list(self.org_names),
            "address_countries": list(self.address_countries),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HomeSignals:
        data = data or {}
        return cls(
            title=data.get("title"),
            og_site_name=data.get("og_site_name"),
            og_locale=data.get("og_locale"),
            html_lang=data.get("html_lang"),
            org_names=[str(x) for x in data.get("org_names") or []],
            address_countries=[str(x) for x in data.get("address_countries") or []],
        )


class _HomeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.signals = HomeSignals()
        self._in_title = False
        self._title: list[str] = []
        self._in_ld = False
        self._ld: list[str] = []
        self.ld_blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html" and data.get("lang") and not self.signals.html_lang:
            self.signals.html_lang = data["lang"].strip()
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            prop = (data.get("property") or data.get("name") or "").lower()
            content = data.get("content", "").strip()
            if prop == "og:site_name" and content and not self.signals.og_site_name:
                self.signals.og_site_name = content
            elif prop == "og:locale" and content and not self.signals.og_locale:
                self.signals.og_locale = content
        elif tag == "script" and data.get("type", "").lower().startswith("application/ld+json"):
            self._in_ld = True
            self._ld = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            if self.signals.title is None:
                text = " ".join("".join(self._title).split())
                self.signals.title = text or None
        elif tag == "script" and self._in_ld:
            self._in_ld = False
            self.ld_blocks.append("".join(self._ld))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title.append(data)
        elif self._in_ld:
            self._ld.append(data)


def _walk(node: Any, orgs: list[str], countries: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk(item, orgs, countries)
        return
    if not isinstance(node, dict):
        return
    kinds = node.get("@type")
    names = kinds if isinstance(kinds, list) else [kinds]
    if any(isinstance(k, str) and k.lower() in _ORG_TYPES for k in names):
        name = node.get("name")
        if isinstance(name, str) and name.strip() and name.strip() not in orgs:
            orgs.append(name.strip())
    country = node.get("addressCountry")
    if isinstance(country, dict):
        country = country.get("name") or country.get("@id")
    if isinstance(country, str) and country.strip() and country.strip() not in countries:
        countries.append(country.strip())
    for value in node.values():
        if isinstance(value, (dict, list)):
            _walk(value, orgs, countries)


def parse_home(html: str) -> HomeSignals:
    parser = _HomeParser()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # noqa: BLE001 - malformed markup keeps what was read so far
        pass
    for block in parser.ld_blocks:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        _walk(data, parser.signals.org_names, parser.signals.address_countries)
    return parser.signals
