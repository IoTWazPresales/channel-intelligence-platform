"""Robots policy backed by Protego; HTTP status and spacing policy stay local.

Only the wildcard user-agent group is queried. Protego handles matching,
percent encoding, Allow ties and merged groups. Unlike the previous parser,
repeated Crawl-delay directives use the last valid value (Protego semantics).
New cache records retain the source text; old rule-list records remain readable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Any
from urllib.parse import urlsplit

from protego import Protego

MODE_PARSED = "parsed"
MODE_ALLOW_ALL = "allow_all"
MODE_DISALLOW_ALL = "disallow_all"

MAX_CRAWL_DELAY_SECONDS = 60.0


@dataclass
class RobotsRules:
    mode: str = MODE_PARSED
    # Legacy cache representation; new records use robots_txt.
    rules: list[tuple[bool, str]] = field(default_factory=list)
    crawl_delay: float | None = None
    sitemaps: list[str] = field(default_factory=list)
    robots_txt: str | None = None

    @cached_property
    def _parser(self) -> Protego:
        source = self.robots_txt
        if source is None:
            # Adapt old cached rules to the library, rather than keeping a second matcher.
            lines = ["User-agent: *"]
            lines.extend(
                f"{'Allow' if allow else 'Disallow'}: {pattern}" for allow, pattern in self.rules
            )
            source = "\n".join(lines)
        return Protego.parse(source)

    def allowed(self, url_or_path: str) -> bool:
        """Whether the wildcard group permits this URL or path, including its query."""
        if self.mode == MODE_ALLOW_ALL:
            return True
        if self.mode == MODE_DISALLOW_ALL:
            return False
        parts = urlsplit(url_or_path)
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        return self._parser.can_fetch(target, "*")

    def spacing_floor(self) -> float:
        """The Crawl-delay to honour, capped."""
        if self.crawl_delay is None or self.crawl_delay <= 0:
            return 0.0
        return min(float(self.crawl_delay), MAX_CRAWL_DELAY_SECONDS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "rules": [[allow, pattern] for allow, pattern in self.rules],
            "crawl_delay": self.crawl_delay,
            "sitemaps": list(self.sitemaps),
            "robots_txt": self.robots_txt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RobotsRules:
        rules = [
            (bool(item[0]), str(item[1]))
            for item in data.get("rules") or []
            if isinstance(item, (list, tuple)) and len(item) == 2
        ]
        delay = data.get("crawl_delay")
        source = data.get("robots_txt")
        return cls(
            mode=str(data.get("mode") or MODE_PARSED),
            rules=rules,
            crawl_delay=float(delay) if isinstance(delay, (int, float)) else None,
            sitemaps=[str(s) for s in data.get("sitemaps") or [] if isinstance(s, str)],
            robots_txt=source if isinstance(source, str) else None,
        )


def parse_robots(text: str) -> RobotsRules:
    """Parse through Protego, querying only the wildcard group's delay."""
    source = text or ""
    parser = Protego.parse(source)
    result = RobotsRules(
        mode=MODE_PARSED,
        crawl_delay=parser.crawl_delay("*"),
        sitemaps=list(parser.sitemaps),
        robots_txt=source,
    )
    # Avoid parsing twice before the first cache round-trip.
    result.__dict__["_parser"] = parser
    return result


def rules_from_response(status: int, body: str) -> RobotsRules:
    """2xx parse, 4xx allow all, anything else disallow all for this run."""
    if 200 <= int(status or 0) < 300:
        return parse_robots(body)
    if 400 <= int(status or 0) < 500:
        return RobotsRules(mode=MODE_ALLOW_ALL)
    return RobotsRules(mode=MODE_DISALLOW_ALL)
