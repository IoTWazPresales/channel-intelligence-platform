"""Discovery and listing capture name no retailer, site, domain or country (t396u, t397u).

Sites are found by the pipeline and configured as data (``listing_site`` rows). This scan
fails if a retailer name or a country domain ending appears in the discovery or capture
code, the discovery UI, or the discovery migration. The names below are the proof's test
inputs, which is why they may only appear in tests.
"""

from __future__ import annotations

import re
from pathlib import Path

API = Path(__file__).resolve().parents[1]
REPO = API.parents[1]

SCANNED = [
    *sorted((API / "app/services/listing_capture").rglob("*.py")),
    API / "app/api/v1/endpoints/listing_discovery.py",
    API / "app/api/v1/endpoints/listing_capture.py",
    *sorted((API / "alembic/versions").glob("*_web_discovery.py")),
    *sorted((REPO / "apps/web/src/features/market-listings").glob("Discovery*.tsx")),
    REPO / "apps/web/src/features/market-listings/SiteCandidatesQueue.tsx",
    REPO / "apps/web/src/features/market-listings/discoveryApi.ts",
    REPO / "apps/web/src/features/settings/DiscoverySettingsPanel.tsx",
]

BANNED = re.compile(
    r"evetech|takealot|amazon|hifi|incredible\s*connection|incredibleconnection|makro|"
    r"computer\s*mania|computermania|game\.co|\.co\.za|\.com\.au|\.co\.uk|south\s+africa",
    re.IGNORECASE,
)


def test_no_retailer_or_country_literals_in_discovery_and_capture_code() -> None:
    hits = []
    for path in SCANNED:
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BANNED.search(line):
                hits.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:120]}")
    assert hits == [], "site-specific literals found:\n" + "\n".join(hits)


def test_the_scan_covers_the_discovery_modules() -> None:
    names = {path.name for path in SCANNED if path.exists()}
    assert {"pages.py", "crawl.py", "candidates.py", "observation.py", "html_page.py"} <= names
