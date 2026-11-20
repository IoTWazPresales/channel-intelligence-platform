"""An own RFC 9309 robots.txt matcher.

``urllib.robotparser`` does not support ``*`` and ``$`` wildcards or longest-match, so it is not
used. Rules:

- Only the group for ``*`` is used (every group naming ``*`` is merged).
- A longer pattern wins. On a tie, ``Allow`` wins. No matching rule means allowed.
- ``Disallow:`` with an empty value matches nothing.
- 2xx: parse the body. 4xx (including 404): allow everything. 5xx, unreachable or a timeout:
  disallow everything for this run.
- ``Crawl-delay`` (seconds, capped by the caller) and ``Sitemap:`` lines are kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

MODE_PARSED = "parsed"
MODE_ALLOW_ALL = "allow_all"
MODE_DISALLOW_ALL = "disallow_all"

MAX_CRAWL_DELAY_SECONDS = 60.0


@dataclass
class RobotsRules:
    mode: str = MODE_PARSED
    # (is_allow, pattern) for the "*" group, in file order.
    rules: list[tuple[bool, str]] = field(default_factory=list)
    crawl_delay: float | None = None
    sitemaps: list[str] = field(default_factory=list)

    def allowed(self, url_or_path: str) -> bool:
        """True when a crawler in the ``*`` group may fetch this URL (or path with query)."""
        if self.mode == MODE_ALLOW_ALL:
            return True
        if self.mode == MODE_DISALLOW_ALL:
            return False
        target = _path_with_query(url_or_path)
        best_len = -1
        best_allow = True
        for is_allow, pattern in self.rules:
            if not pattern:
                continue
            if not _pattern_regex(pattern).match(target):
                continue
            length = len(pattern)
            if length > best_len or (length == best_len and is_allow and not best_allow):
                best_len = length
                best_allow = is_allow
        return best_allow

    def spacing_floor(self) -> float:
        """The ``Crawl-delay`` to honour, capped."""
        if self.crawl_delay is None or self.crawl_delay <= 0:
            return 0.0
        return min(float(self.crawl_delay), MAX_CRAWL_DELAY_SECONDS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "rules": [[allow, pattern] for allow, pattern in self.rules],
            "crawl_delay": self.crawl_delay,
            "sitemaps": list(self.sitemaps),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RobotsRules:
        rules = [
            (bool(item[0]), str(item[1]))
            for item in data.get("rules") or []
            if isinstance(item, (list, tuple)) and len(item) == 2
        ]
        delay = data.get("crawl_delay")
        return cls(
            mode=str(data.get("mode") or MODE_PARSED),
            rules=rules,
            crawl_delay=float(delay) if isinstance(delay, (int, float)) else None,
            sitemaps=[str(s) for s in data.get("sitemaps") or [] if isinstance(s, str)],
        )


def _path_with_query(value: str) -> str:
    parts = urlsplit(value)
    path = parts.path or "/"
    return path + (f"?{parts.query}" if parts.query else "")


_regex_cache: dict[str, re.Pattern[str]] = {}


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    compiled = _regex_cache.get(pattern)
    if compiled is None:
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        regex = ".*".join(re.escape(piece) for piece in body.split("*"))
        compiled = re.compile(regex + (r"\Z" if anchored else ""), re.DOTALL)
        _regex_cache[pattern] = compiled
    return compiled


def parse_robots(text: str) -> RobotsRules:
    """Parse a robots.txt body into the rules of the ``*`` group, plus the sitemap lines."""
    rules: list[tuple[bool, str]] = []
    sitemaps: list[str] = []
    crawl_delay: float | None = None
    group_agents: list[str] = []
    in_agent_run = False
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        name = name.strip().lower()
        value = value.strip()
        if name == "user-agent":
            if not in_agent_run:
                group_agents = []
                in_agent_run = True
            group_agents.append(value.lower())
            continue
        in_agent_run = False
        if name == "sitemap":
            if value:
                sitemaps.append(value)
            continue
        if "*" not in group_agents:
            continue
        if name in ("allow", "disallow"):
            rules.append((name == "allow", value))
        elif name == "crawl-delay":
            try:
                parsed = float(value)
            except ValueError:
                continue
            crawl_delay = parsed if crawl_delay is None else max(crawl_delay, parsed)
    return RobotsRules(mode=MODE_PARSED, rules=rules, crawl_delay=crawl_delay, sitemaps=sitemaps)


def rules_from_response(status: int, body: str) -> RobotsRules:
    """What a robots.txt fetch result means: 2xx parse, 4xx allow all, anything else disallow all."""
    if 200 <= int(status or 0) < 300:
        return parse_robots(body)
    if 400 <= int(status or 0) < 500:
        return RobotsRules(mode=MODE_ALLOW_ALL)
    return RobotsRules(mode=MODE_DISALLOW_ALL)
