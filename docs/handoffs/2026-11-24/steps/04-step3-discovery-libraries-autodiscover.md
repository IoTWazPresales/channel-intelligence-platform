# Step 3

- **Status:** Code written (cloud). Not merged. Not visually checked. cip_test not run.
- **Branch:** `cursor/u3-step3-discovery-10a0`
- **Worktree:** cloud agent
- **PR:** https://github.com/IoTWazPresales/channel-intelligence-platform/pull/134 against `feat/integrate-20261103` (do not merge)
- **Commits:** `40950fca`, `372ea058`, then the Warren decisions follow-up, on `cursor/u3-step3-discovery-10a0`

## Checklist

- [x] Read `docs/handoffs/2026-11-24/RULES.md` and this step's prompt
- [ ] Discovery libraries work and auto-discover when services are up. No live writes.

Code is written. The live proof and the cip_test before/after counts are local.

## Mount instruction (U1 owns MarketSurface.tsx — do not edit it here)

In `apps/web/src/features/market-listings/MarketSurface.tsx`, the listings lens is the
`PriceMatrixLens` rendered when `lens === 'listings'` (the line that is
`{lens === 'listings' ? <PriceMatrixLens /> : null}`, currently line 918).

Render `<SiteConfirmBar />` immediately above `<PriceMatrixLens />`, and only when
`lens === 'listings'`. Import it from `@/features/market-listings/SiteConfirmBar`.
Do not mount it on Discover sites or Feed proposals.

## Constants kept or added

- `HOSTS_PER_QUERY = 3` — Warren's top 2–3 search results. A cap on a result list, not a tenant rate.
- `MAX_DEBOUNCE_HOURS = 8784` — rejects a typed value above about a year. Not a default.
- `MAX_COALESCE_SECONDS = 86400` — rejects a typed confirm wait above one day. Not a default.
- `MAX_MATRIX_CUSTOMERS = 200` — rejects a longer saved id list. Not a default.
- `MAX_SITEMAP_CHARS = 5000000` (now in `web_discovery/sitemaps.py`) — ignores a sitemap document larger than this. Not a tenant setting.
- `_SITEMAP_SEEDS = 2` and `_SITEMAP_INDEX_CHILDREN = 2` — same bounds as the old sitemap walk, plus robots `Sitemap:` lines.
- Removed: `SCHEDULED_RUN_DEBOUNCE` and `CONFIRM_COALESCE_SECONDS`. No 24 and no 120 in product code.
- Celery crontab `hour=5, minute=20` stays. It wakes the process. It is not the tenant's gap.

## Warren's decisions (27 Nov 2026)

1. `ultimate-sitemap-parser==1.8.2` (GPL-3.0-or-later) is added and reads product-page sitemaps through `web_discovery/sitemaps.py`. Every sitemap request still goes through the robots check and the site's pacing. `web_discovery/pages.py` (domain detection) keeps its own sitemap reader.
2. `listing_seed` is a source of a site again in product-page discovery: a named marketplace, a domain or origin seed, and the seed's site fields copied onto blank site fields, plus confirmed web sites. Domain detection (`candidates.py`) still does not use the seed host, as the close-off asked.
3. No crawl-delay floor on top of the site's own rate.
4. 05:20 UTC only wakes the job. The gap is the tenant's saved hours.
5. Matrix extras stay this browser's last steward save.
6. `tenant.locale` stays optional.
7. `372ea058` reformatted shipment, CST, CPOR, DSI, product-master and listing-poll tasks and non-discovery parts of `autoconfig.py` and `tenant_settings.py`. Those edits are reverted. `_site_health` and `capture_health` match the discovery base.

No migration was required: the timings are keys on the existing `tenant_setting` table.

## Tests

No-database unit tests and the library proof script were run on this cloud Linux machine. That is not the real runtime. `apps/api/tests/test_w1b_retail_discovery.py` (restored to its listing_seed form) and `apps/api/scripts/ops/discovery_proposal_counts.py` were not run. No live writes.

## Resume notes

Do not open a second branch for this step. Finish locally: cip_test, visual gate, review, merge, deploy.
