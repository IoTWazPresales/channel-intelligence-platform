# Library review - 2026-11-24 (list only, nothing changed)

Warren's step 6 (t412u): for each module, what is in use now and which established, maintained,
permissively licensed (MIT / Apache-2.0 / BSD / ISC) libraries would make it smarter or better.
**Nothing in this document has been installed or changed.** Each row is a candidate for a later,
separately approved PR.

House rules that still apply to every row: reuse before adding; no new chart library unless Warren
lifts that rule; no fuzzy auto-joins (a similarity score may only rank suggestions in a steward
queue); nothing country-specific built in; LGPL/GPL/MPL are avoided (for example python-stdnum, fpdf2).

How status was judged: the dependency files on integrate (`apps/api/requirements.txt`,
`apps/web/package.json`) and the reviewer's knowledge of each project's releases and licence.
No registry lookups were made for this list, so **re-check the licence and last release on
PyPI / npm before adopting any row.** Effort: S = under a day, M = 1-3 days, L = a week or more.

## In use today (summary)

- **API:** FastAPI, Starlette, Uvicorn, SQLAlchemy 2 (async + psycopg3/asyncpg), Alembic, Pydantic 2,
  Celery 5.4 + Redis, pandas, openpyxl, xlrd, python-dateutil, httpx, msal (Microsoft Graph mail),
  anthropic (AI import resolver, sell-through narrative), numpy, stdlib `imaplib` / `smtplib` / `email`,
  stdlib `difflib` (name normalisation suggestions), stdlib PBKDF2 passwords.
- **Discovery / listing capture (added this wave):** crawlee[playwright] 0.6.12, playwright 1.65,
  browserforge, ddgs, extruct, price-parser, tldextract, protego; own GS1 check-digit helper.
- **Web:** Next 15, React 19, MUI 6 (+ icons, Emotion), AG Grid Community 33, Recharts 2,
  MapLibre GL 5, TanStack Query 5, react-hook-form + zod, zustand, dnd-kit, react-grid-layout,
  react-resizable, @xyflow/react + dagre, undici. Tests: Vitest, Testing Library, Playwright.
- **Hand-rolled where a library exists:** minimal PDF writer (`report_export._text_pdf`), demand
  forecast maths (`services/demand_forecast/*`), retry/back-off in listing capture, place gazetteer
  matching (`store_dc/place_name.py`).

## Module by module

### 1. Discovery
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| trafilatura | Apache-2.0 (since 1.8; older releases GPL, so pin a new one) | Active | Main-content and metadata extraction when a page has no structured data; better product-name and spec text for model-code matching | M | Low. Read-only parser behind the existing reader |
| selectolax | MIT | Active | Much faster HTML parsing than BeautifulSoup or lxml for sitemap and search-result pages | S | Low |
| courlan | Apache-2.0 | Active | URL cleaning, dedupe and "is this a product URL" filtering before crawling | S | Low |
| w3lib | BSD-3 | Active (Scrapy project) | Canonical URL and encoding helpers | S | Low |
| ultimate-sitemap-parser | MIT (GPL in old versions, so verify) | Active | Robust sitemap index / gzip / news sitemap walking instead of our own | S | Low |
Keep: Crawlee + Playwright, ddgs, protego, tldextract, extruct.

### 2. Listing capture
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| tenacity | Apache-2.0 | Active | Declarative retry/back-off. Only if it can express the existing #100 spacing and 403/429 rules exactly; otherwise keep ours | S | Medium. Behaviour must not change |
| Babel | BSD-3 | Active | Locale-aware number and currency parsing alongside price-parser (comma vs dot decimals per tenant locale) | S | Low |
| curl_cffi | MIT | Active | TLS-fingerprint-friendly HTTP client for sites that block plain httpx, before falling back to a browser | M | Medium. Must still honour robots and pacing |
Keep: price-parser, extruct, Playwright fallback.

### 3. Imports and AI import
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| python-calamine | MIT | Active | Fast Excel/ODS reading (Rust) for large retailer files; pandas supports `engine="calamine"` | S | Low. Read path only; compare outputs on a sample |
| charset-normalizer | MIT | Active (already a transitive dependency of many packages) | Detect CSV encodings instead of trying a fixed list | S | Low |
| pandera | MIT | Active | Declarative column and value checks on parsed frames, with readable error reports for stewards | M | Low |
| instructor | MIT | Active | Pydantic-validated, retried structured outputs from the LLM in `ai_import_resolver` (the anthropic SDK's tool use can do this too, so this is optional) | S | Low |
Keep: openpyxl (writing), pandas, anthropic.

### 4. Matching and GTIN
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| RapidFuzz | MIT | Active | Faster, better similarity scoring than `difflib.SequenceMatcher` for **ranking steward-queue suggestions only**, never auto-linking | S | Low, if the scores stay advisory |
| Splink | MIT | Active (UK MoJ) | Probabilistic record linkage (customer, site and product dedupe) with explainable match weights for the steward queue | L | Medium. Needs DuckDB; must stay a suggestion engine |
| recordlinkage | BSD-3 | Slow releases | Alternative to Splink | M | Medium (maintenance) |
Keep: own GS1 helper (python-stdnum is LGPL), exact model/part-code rules.

### 5. Forecasting and replenishment
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| statsforecast (Nixtla) | Apache-2.0 | Active | ETS, Theta and Croston/TSB (intermittent demand, which suits SKU x store sell-through) to sit alongside the current velocity and analogue methods, with backtest metrics | M | Medium. Changes numbers users see, so run it shadow-mode first |
| statsmodels | BSD-3 | Active | Classical decomposition and seasonality checks; alternative to statsforecast | M | Medium |
| scikit-learn | BSD-3 | Active | Analogue-product similarity (nearest neighbours on attributes) for new-SKU forecasts | M | Medium |
| holidays | MIT | Active | Public-holiday calendars per **tenant country** for the business calendar and forecast features | S | Low, if driven by the tenant country setting |

### 6. Pricing
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| Babel | BSD-3 | Active | Currency display and rounding per tenant locale | S | Low |
| py-moneyed | BSD-3 | Active | Money type (amount plus currency) to stop mixing ZAR and USD floats in the CPOR waterfall | M | Medium. Touches many call sites |
Keep: Decimal maths; VAT now comes from tenant settings (R-05 branch).

### 7. Maps
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| supercluster | ISC | Stable (Mapbox) | Fast point clustering for store pins at country zoom (MapLibre's GeoJSON clustering uses it internally; usable directly for custom markers) | S | Low |
| @turf/turf (modular) | MIT | Active | Distance, nearest-DC, point-in-polygon and buffers in the browser | S | Low |
| Shapely + pyproj | BSD-3 / MIT | Active | Server-side geometry for store-to-DC distance and coverage areas | M | Low |
| Photon (self-hosted geocoder) | Apache-2.0 | Active | Real suburb/mall lookup for BACKLOG-267 instead of the GeoNames town list (needs an OSM extract and a Java service) | L | Medium. Ops work; must stay a proposal, steward confirms |
Keep: MapLibre GL, OpenFreeMap tiles.

### 8. Dashboard charts
House rule: no new chart library. Stay on Recharts 2 (target lines now use its `ReferenceLine`).
If Warren ever lifts the rule: @mui/x-charts (MIT community tier, matches the MUI theme), Apache
ECharts (Apache-2.0, best for large series) or visx (MIT). Effort L, risk medium (a second chart stack).
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| @mui/x-date-pickers | MIT (community) | Active | Proper date-range pickers for target periods and fixed windows instead of plain date text fields | S | Low |

### 9. PDFs and reports
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| Playwright `page.pdf()` | Apache-2.0 | Already installed | Render the existing HTML report or page to a real PDF (fonts, tables, charts) instead of the single-font hand-made PDF. **No new dependency** | S | Low. Recommended first choice |
| ReportLab (open-source) | BSD | Active | Programmatic PDF layout if the HTML route is not wanted | M | Low |
| Jinja2 | BSD-3 | Active | HTML templates for report and digest emails | S | Low |
Avoid: fpdf2 (LGPL). WeasyPrint is BSD but needs GTK/Pango on Windows, so it carries install risk.

### 10. Email and mailbox
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| IMAPClient | BSD-3 | Active | Friendlier IMAP than stdlib `imaplib` (IDLE, UID handling) for non-Graph mailboxes | S | Low |
| mail-parser | Apache-2.0 | Moderate activity | Robust MIME, attachment and header parsing for ingested mail | S | Low |
| premailer | BSD-3 | Slow releases | Inline CSS so digest emails render in Outlook | S | Low |
Keep: msal + Graph for Microsoft 365.

### 11. Scheduling
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| celery-redbeat | Apache-2.0 | Active | Beat schedule stored in Redis **with a lock**, so a second beat can never double-fire, and schedules become editable at runtime (fits tenant-setting schedules) | S | Low-medium. Swap the beat scheduler class; test on cip_test first |
| flower | BSD-3 | Active | Read-only Celery monitoring UI (queues, task history) | S | Low. Bind to localhost only |
Today's check found one beat (the second process was the Windows venv launcher's child), so redbeat is prevention rather than a fix.

### 12. Auth
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| argon2-cffi (or pwdlib) | MIT | Active | Argon2id password hashing instead of stdlib PBKDF2, with transparent rehash on next login | S | Low. Keep verifying old hashes |
| Authlib | BSD-3 | Active | OIDC single sign-on (Entra ID / Google) for users, next to the existing session auth | M | Medium. A security-sensitive change |
| PyOTP | MIT | Active | TOTP two-factor for admin and steward accounts | S | Low |

### 13. UI
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| notistack | MIT | Active | Stacked snackbars for save/apply results instead of per-page Alerts | S | Low |
| cmdk | MIT | Active | Ctrl+K command palette to jump to customers, products and pages | S | Low |
| nuqs | MIT | Active | Type-safe URL query state for filters (shareable filtered views; fits the redirect and filter work) | M | Low-medium |
| react-error-boundary | MIT | Active | Per-panel error boundaries so one failing widget doesn't blank a page | S | Low |
| date-fns | MIT | Active | One date library for the web (pairs with x-date-pickers) | S | Low |
Theme alignment (step 8) needs no library: MUI theme tokens already drive both themes.

### 14. Cross-cutting (optional)
| Candidate | Licence | Status | Would replace / add | Effort | Risk |
|---|---|---|---|---|---|
| structlog | MIT / Apache-2.0 | Active | Structured JSON logs with job and tenant context (`job_log_context` today) | M | Low |
| sentry-sdk (self-hosted or GlitchTip) | MIT | Active | Error tracking for API, worker and web | S | Low. Keep data on-prem |

## Suggested order if Warren wants any of this
1. Playwright `page.pdf()` for reports (no new dependency).
2. celery-redbeat (stops double-firing for good).
3. RapidFuzz for steward suggestions, plus python-calamine for imports.
4. argon2-cffi.
5. statsforecast in shadow mode, plus holidays from the tenant country.
6. notistack, react-error-boundary, x-date-pickers.
Each one as its own small PR with the licence named.