"""N-0085 criteria patch and child units U1..U6 from N0085_DESIGN.md and D-0063 (2026-10-07)."""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
STD = "Tests green on touched areas, tsc exit 0, eslint clean on changed files"
DES = "Design: .eif/audit/PROGRAMME_20261007/N0085_DESIGN.md; decisions D-0061 and D-0063"

patch = {
    "node": "N-0085",
    "expected_revision": 0,
    "acceptance_criteria": [
        "Warren 2026-10-07 (D-0061, D-0063): listing coverage for every reporting customer's site, including Amazon and Makro",
        "Discovery basis: products each customer reported selling in its sell-through files in the last 6 months; exact keys only (normalised EAN, part number, feed id); a page counts only if it shows the EAN or part number; a steward confirms; nothing auto-registers",
        "One page reader per retailer extracts price, stock, promo, title, brand, images, description length, specs, seller/buy box, rating, reviews, page EAN/part number for N-0078",
        "Ordinary browser user agent; polite per-site spacing; per-site pause on 403/429 with back-off; per-run time limit; no CAPTCHA solving or block evasion; a paused site shows on screen",
        "Coverage view per customer: products reported vs listings watched vs awaiting steward vs failing vs not found",
        "Complete when child units N-0101..N-0106 are complete",
    ],
}
(HERE / "p_n0085.json").write_text(json.dumps(patch, indent=2), encoding="utf-8")

CHILDREN = [
    ("N-0101", "N-0085 U1: listing polling on under the supervisor, restock seen again, dead-link back-off, per-site 403/429 pause, run time limit",
     ["api", "infra"], "R2", ["N-0073"],
     ["The supervisor's worker environment sets CIP_LISTING_CAPTURE_SCHEDULE and CIP_LISTING_LIVE_FETCH; status shows both present",
      "A beat run records new Takealot and Evetech observations on cip",
      "An out_of_stock listing seen in stock returns to active (restocked); out_of_stock listings keep being polled",
      "consecutive failures drive the dead-link back-off; a 403/429 pauses only that site (1 h doubling to 24 h) and is recorded",
      "Each poll run takes the oldest-due listings first, mixes retailers and stops at 10 minutes",
      "Market ledger copy 'Checked on a schedule' is true, or changed to what is true", DES, STD]),
    ("N-0102", "N-0085 U2: per-retailer page reader framework (Takealot, Evetech, Amazon), N-0078 fields, registry migrations, discovery for Takealot and Evetech",
     ["api", "schema"], "R2", ["N-0101"],
     ["listing_capture/adapters/<site>.py contract: find(keys), fetch(listing), parse() with the N-0078 field set into parse_flags.fields",
      "Migrations M1-M4 per the design, proven on cip_test before cip; marketplace vocab and status lifecycle (restocked, retired) extended",
      "The 168 stored snapshots re-parse with zero fetches and the same price/stock as before",
      "Discovery job (daily) proposes only corroborated pages (EAN or part number shown) for reported products with no listing; Amazon's 51 listings linked to products by feed id or flagged", DES, STD]),
    ("N-0103", "N-0085 U6: Proposed listings steward worklist with bulk confirm, and a per-customer Coverage lens",
     ["ui", "api"], "R2", ["N-0102"],
     ["Feed proposals becomes Proposed listings: customer, product, page link, how found, what the page shows (title, EAN, price); Confirm selected takes corroborated rows only and lists skipped ones",
      "Coverage lens (?tab=coverage): per customer reported, watched, awaiting steward, failing, not found, not searched, plus site state; drill to products; counts match SQL",
      "A paused site shows a chip with reason and next try; nothing blocks", DES, STD]),
    ("N-0104", "N-0085 U4: Computer Mania reader and discovery (Shopify search, sku/barcode corroboration)",
     ["api"], "R2", ["N-0102"],
     ["Search by part number or model, corroborate via the product's sku/barcode; most of the 36 reported products proposed corroborated", DES, STD]),
    ("N-0105", "N-0085 U3: Game and Makro readers and discovery (Makro site search per D-0063)",
     ["api"], "R2", ["N-0102"],
     ["Game: reader for its product pages and search; the 15 reported products proposed",
      "Makro: reader and site search (Warren D-0063), the 27 reported products proposed; if a site serves only a script shell, record what was tried and show it as not found, never invent", DES, STD]),
    ("N-0106", "N-0085 U5: Incredible Connection and HiFi Corp shared reader and discovery",
     ["api"], "R1", ["N-0102"],
     ["One reader for the shared site; their reported products (4 while reports are stopped) proposed; widens automatically when their reports resume", DES, STD]),
]
for nid, title, facets, risk, deps, criteria in CHILDREN:
    payload = {
        "id": nid, "parent": "N-0085", "title": title, "class": "feature", "origin": "decomposition",
        "status": "proposed", "facets": facets, "risk": risk, "risk_class": "full",
        "touches_existing": True, "depends_on": deps, "acceptance_criteria": criteria,
        "conservation_tags": [], "parity_source": [], "fingerprint": None, "acceptance": "auto",
    }
    (HERE / f"{nid.lower().replace('-', '')}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(nid)
