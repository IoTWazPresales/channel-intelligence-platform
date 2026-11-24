# CURRENT state

**Last updated:** 2026-11-25 — step 0 recovery rules and handoff logs are on `docs/impl-process-rules-20261125` (not merged). Prior note 2026-11-24 — store map review fixes (smaller semi-transparent land dots, Move+undo, shipping-map glow). Discovery V2 merged and live (a6f498ce, migration 0066); stock-based listing scope (BACKLOG-270) merged, off until a tenant saves it. Last prior live acceptance: 22 November (`c685bf63`).
**Branch:** `docs/impl-process-rules-20261125` (this docs unit). Trunk remains `feat/integrate-20261103`, cut from `ca8f5f7f`. Confirm HEAD with `git rev-parse`. Do not treat a hash written here as HEAD.
**Deploy gate (BACKLOG-245, 2026-11-24):** `cip-deploy.ps1` now gates the worker on a fresh Redis heartbeat (`python -m app.worker.liveness_check --since <restart>`) plus a live pid; `celery inspect ping` is recorded as a diagnostic only (the solo pool cannot answer it while busy). **AI import (2026-11-24):** spec integrated at `docs/specs/AI_ASSISTED_IMPORT.md`; build waits on Warren's decisions (BACKLOG-271). BACKLOG-168 verified Done. **Theme (BACKLOG-272, 2026-11-24):** tokens aligned to the dashboard-v2 mockups (secondary text 0.82, dark Paper shadow 0.25). **Theme/scroll follow-up (t417u, 676fe8c3 / 98e19cf7, live 13:40):** typography and elevated chrome closer to the mockups; nested empty-space page scroll removed (AppShell main is the only scroller). BUILD_ID `FtjQS2XoM4HHQBgL0pHOw`. **Close-off (2026-11-24):** BACKLOG-262/263/264/250 closed (merged and live); stage/wave table at `docs/audits/STAGE_WAVE_STATUS_20261124.md`; EIF nodes N-0102/N-0119 built and live but closable only through EIF. **Deploy (2026-11-24 04:08):** first passing `cip-deploy.ps1 -Execute`; BACKLOG-245 Done; live BUILD_ID `q9HdrTrS8TCvaWBgiNm2y` at `4c8b0355`. **VAT (Opus R-04/R-05, merged 2026-11-24, Warren t417u):** planner SRP uses the tenant VAT rate (Settings -> tenant profile -> VAT rate), new case lines and incl-VAT SOH costs too; no implied 15%; gazetteer from tenant country. Live rate 0.15 saved through Settings at deploy. **Wave t417u (2026-11-24, coding by local Cursor):** VAT live (BACKLOG-273 Done); standalone `/promotions/timeline` reporting-only (BACKLOG-253, 14eb0cfc); planner Timeline by customer reporting-only and 6-month axis (c4f85535, t426u-t430u); timeline full width with detail in a drawer (035ff93c, t435u); reporting-only defaults on planner queues/headline counts, case book, plan templates, store-map chips and sell-through overview (19c7fd46, t437u-t440u); Discovery on live (BACKLOG-274, API live fetch via `apps/api/.env`); background loading (BACKLOG-275). Cursor jobs run one at a time (concurrent sessions tripped EIF SESSION_CLOSURE_REQUIRED). **Next agent:** Dashboard V2 slices 1 and 2 merged (BACKLOG-269 done except light-theme screenshots); BACKLOG-267 panel caption done. Next: BACKLOG-266 audit, then price fixes R-04/R-05. Read [durable handoff](../handoffs/2026-11-23/README.md).

## Branch, database and topology

- Web last verified atc685bf63 / BUILD_ID`CbNqqIUC9jWVb7H6po90e`. API/worker last deployedb3b54f5e; no backend restart for the final UI corrections. Integration and product feature branches were pushed; no main promotion.
- Windows local ModeB; web3000/API8001/Postgres5432 database`cip`/Redis6379. No Docker. API Python3.12 venv; system3.14 only for non-API documentation scripts.
- Source/applied UI Alembic`20261120_0065`, last verified22November. Warren executed natural0063->0064->0065; do not repeat the old operator wrapper. Schema/grants/798existing relation metadata/counts and3.35GB backup/hash independently checked; exact backup path/hash in handoff.
- Retained clone`cip_ui_migrate_20261122_1df81d9e4dcb`: real backup/restore/naturalUP-DOWN-UP passed without stamping. Final browser fixtures restored to tenant1/app_user3/auth_session135/layout0 with exact full-row digests; independently rechecked READ ONLY. Sharedcip_test untouched by this continuation.
- Original untracked`.agents/`,`.eif/upgrade-history/`,`.eif/upgrade-work/`,`apps/api/.env.bak-20261117` preserved/unstaged. Source worktrees preserved; no automatic cleanup or restoration.

## Proven live / limits

- Inventory:055bc770/f8bb446f integrated2d374040; six actual browser route/redirect checks pass, including same-origin filters and Movement navigation. Movement dataset acceptance is outside those route checks. BACKLOG-266 covers other aliases.
- Line-up:071be7bb integrated7f2785d4; native button/grid double-toggle corrected.177reporting items/sixgroups and reporting header semantics checked, five acceptance records/ten real mouse-keyboard gestures pass. Approval/edit/import writes were not exercised.
- Database-map:23f47395/567f8bfa integratedc685bf63; seven independently executed live checks pass:142tables/285FKlinks, readablefit340px/zoom1, empty/clear cycles, stable positions and FK selection. ReactFlow internal-store visibility fixes transient minimapNaN; no alternate writer/layout algorithm.
- Final clean product gates:lint0errors/48baseline warnings, nonincremental types0, build84pages, unfiltered291files/1818tests0 (623.31s, no retry/filter/suppression). Clone browser Save/reload/user+tenant isolation passed with actual app ASGI IPC; unrelated shell readers stubbed, fixture bearer sessions. This does not test Save via the Next proxy/password logout or retained-client switching. Live normal sign-in/catalog/rendering separately proved.
- Web-only release0; launches5->6, others unchanged; two web/API200/healthy-state/count/build samples82.349s apart. Candidate3107 stopped after ownership checks; stale PIDs in evidence are historical. Original failures retained, never relabeled PASS. Portable summaries in handoff/evidence; raw local proof under`.tmp/coordinator-20261121/` and`.tmp/coordinator-20261122/`.
- Earlier canonical stack deploy`deploy-20261122-145442.json` remains FAILED at busy-solo Celery ping. Later idle ping/heartbeat and stability are separate evidence. BACKLOG-245 retains the heartbeat-based deploy gate follow-up; read DEV_TOPOLOGY before worker changes.

## Discovery V2 and listing scope (2026-11-24)

- Discovery V2 merged `a6f498ce` (Crawlee, Playwright, extruct, price-parser, tldextract, protego, ddgs; licences in the merge commit). Migration `20261123_0066_web_discovery` applied on live as owner after a 3.36 GB backup. Live Discovery settings saved 24 Nov 00:57 by Warren's approval (ZA, .co.za/.com, free web search, 5 s/10/20 s, browser on); schedule OFF. Discover is not hard-disabled. The buttons stay off only while `previewBlockReason` is set (`DiscoveryLens.tsx` lines 39-45; `discoveryApi.ts` line 290 when `capabilities.live_fetch` is false). `GET /listing-capture/discovery/capabilities` (`listing_discovery.py` lines 69-84) returns `live_fetch` from `listing_live_fetch_enabled()` (`observation.py` lines 230-243), which is true when `CIP_LISTING_LIVE_FETCH` or Settings `cip_listing_live_fetch` is truthy. D-0061 is not worker-only (`observation.py` line 235). This session did not read `.env`. The scheduled beat runs discovery only for tenants with `discovery.schedule_enabled` true (`tasks.py` lines 885-895); a missing `tenant_setting` row is off (migration `20261120_0064` docstring). This session did not query that row. The "schedule OFF" words above are the 24 Nov CURRENT claim, not a new query.
- Stock-based listing scope (BACKLOG-270) uses existing stock facts and the existing poll beat. Off until `listing_scope.settings` is saved for the tenant.

## Store map (BACKLOG-268) — OpenFreeMap chosen 2026-11-23

- 2026-11-24 t417u: StoreMap shares On the water's side hover cards and basemap dot/land treatment (pps/web/src/features/maps/mapHover.tsx, mapBasemap.ts). Merged a3fcbd5d to integrate (pending this deploy). Steward pin flows unchanged.

- Sell-through shows the MapLibre store map when this tenant has a TileJSON URL in tenant settings. No provider URL is hardcoded in code or migrations; Warren chose OpenFreeMap and it is stored as this tenant's setting via the existing settings API. The SVG dotted basemap remains the fallback and is still used by On the water. Attribution stays the compact OSM/provider (i) control.
- Shared land dots stay on the dense 0.7 deg / 4px grid, but are smaller and semi-transparent (SVG stroke 1.0 at about 0.42–0.45 opacity; MapLibre dotted-land uses a tighter, ~0.42 alpha stipple) so the land reads cleanly.
- Confirmed pins are not draggable until the user presses Move pin. Unconfirmed and proposed pins stay draggable. Pin moves can be undone in the session with Ctrl+Z / Cmd+Z or Undo, through the same save path. Boundary rings were replaced with the shipping-map soft glow (`MapMarker`). No store locations were auto-confirmed. BACKLOG-267 still applies. Fourways A02 and Clearwater A01 stay unverified.

## Targets / Dashboard V2 - slice 1 shipped 2026-11-24

- Personal KPI targets live on existing KPI widgets as `definition_v2.display.target` (no migration). Editor: Number options -> My target. Tile: target line, attainment rail, On track / At risk / Behind. Slice 2 (2026-11-24) adds the home dashboard choice and role-default reset (`dashboard.home` ui-layout plus the tenant setting `dashboard.job_defaults`, unset on live), stock-below-sales starters, the Overview stock health panel, attention owner/age, target period and the trend target line. See BACKLOG-269.

- Only a design spec and standalone HTML Dashboard/target-builder prototypes were recovered. Submit opens an illustrative dialog; no matching new Targets route/API/product implementation was found. Draft dark/light styling exists; the requested live redesign is not delivered.
- Exact original drafts now preserved in`docs/design/dashboard-v2/` and`docs/specs/DASHBOARD_V2.md`; they retain design-only provenance. See handoff/TARGETS_STATUS.md for source evidence and limitations.
- Earlier Dashboard visual direction approved in **both themes**, stock health BELOW sales charts. Expanded replenishment/aged-stock mock-up/detail/build pending. Previous saved light screenshot duplicated dark and is not light-theme acceptance evidence. BACKLOG-269 tracks remaining delivery.

## 24 Nov regressions and recovery

Checked in this session against `ca8f5f7f` unless a commit is named. This session did not query live `cip`.

- Theme2 `edbdfc00` (merged `b79b1d33`, ancestor of this tip) sets `h5` to `0.9375rem` (`apps/web/src/theme/cipTheme.ts` line 36). Page titles use `h5` (`PageHeader.tsx` line 29, `DomainHeader.tsx` line 43). The dashboard mock-up `h1` is 27px (`docs/design/dashboard-v2/index.html` line 62). 0.9375rem is 15px when the root is 16px. Step 4a.
- The page gradient puts a colour in `background-image` (`cipTheme.ts` line 65: `radial-gradient(...), ${t.bg.default}`). A colour is not a valid `background-image` layer, so browsers drop the declaration. The shell root paints `bgcolor: 'background.default'` (`apps/web/src/features/shell/AppShell.tsx` line 129). Step 4a.
- `f1a561cb` renders `PriceMatrixLens` for the listings lens (`MarketSurface.tsx` line 918) and does not render `ListingCaptureHealth` there. Current tests expect the matrix and expect `listing-capture-health` to be absent (`MarketSurface.test.tsx` lines 135 and 138). `0bd7ed1b` does not rewrite six tests: `git show 0bd7ed1b` is a 5-line `beforeEach` that sets `nav.search = 'tab=observations'` in `MarketSurface.test.tsx`. Step 1.
- The planner calendar scope sends `reporting_only` and `official_promotion_types` (`planner/plannerCalendarScope.ts` lines 2-10). Official types are Sell out PP, Sell-Through PP, and Stock PP (In-Direct) (`promotion_type_vocab.py` lines 9-13; filter at `cpor_cases.py` line 653). The planner list query does not drop ended rows (`PromotionPlannerSurface.tsx` lines 170-179 and 270-271). Create-case defaults the type to `Sell out PP` (line 991). Ended cases are loaded on purpose (lines 194-202 and 518). Step 2.
- Live case counts were not re-queried. `terminals\audit-20261124-recovery-sql.txt` section `cpor_superseded` is the row `0 | 310`. The Opus audit reads that as 310 live cases and 0 open (`docs/audits/RECOVERY_AUDIT_20261124.md`). The same file's type/status breakdown includes draft, ended, settled and cancelled rows.
- Takealot and Amazon `listing_site.adapter_key` values are empty; Evetech is `html_page` (same SQL file, section `listing_site`). Observations in that file: Evetech 2026-11-24, Amazon and Takealot 2026-11-04. The 19 Nov audit says commit `3ea6cce4` (3 Nov) deleted the per-site readers, and Warren stopped the 19 Nov restore because the deletion was on purpose (`docs/audits/LIVE_SCREEN_AUDIT_20261119.md` lines 31 and 146). The step prompt's "removed on 19 Nov" mixes those two dates. Step 3.
- `web_discovery/__init__.py` lines 9-10 say the scheduled path applies auto-linked sites. `apply.py` lines 300-313 queue both `auto_accept` and `queue` as proposed sites. `scheduled.py` lines 85-86 call `apply_plan(..., sites_only=True)`, which skips `apply_link_items` (`apply.py` lines 376-384). `scoring.py` lines 230-232: `auto_accept` is exact name key plus country, product hits, home HTTP 200 and robots allowed. That outcome is queued, not confirmed.

## Next

One step at a time, from `docs/handoffs/2026-11-24/IMPLEMENTATION_LOG.md`.

1. Step 0 process rules (this branch). Session 1 does not merge.
2. Step 1: monitored listings keeps its content and health panel and gains the price matrix as the centrepiece.
3. Step 2: planner shows open customer sell-through promotions, calendar per the mock-up. Mock-up image is not on disk yet.
4. Step 3: discovery libraries, auto-discover when services are up, confirm bar. No live writes.
5. Step 3b: live activation and readers. Deferred until Warren approves live writes.
6. Step 4a: page title size, page gradient, Paper clipping.
7. Step 4b: theme through shared components, one slice per chat.
8. Step 5: rescue dirty worktree work, then prune only what Warren approves.

Store-location confirmation stays unauthorised (BACKLOG-267). Do not promote to `main`.

## Boundaries / blockers

- No main push/promotion. OpenFreeMap is this tenant's setting only, not a product default. No store-location confirmation is authorized.
- Codex session registration was absent on22November. Future protected DB work requires installed operator mechanism; never fabricate state/self-grant/borrow a session/use missing hooks as permission. Do not set ALLOW_TESTS_ON_DEV_DB casually. Cloud guard denial is a stop condition.
- No hook/policy/.claude/CLAUDE.md edits; engineering-rules.mdc missing and not invented. Preserve existing failed artifacts and the two-attempt stop rule. Agent quotas may be exhausted; all outstanding scope is durable outside chat.

## Opus R-04 / R-05 (2026-11-24)

- **R-04:** the planner price read now selects `vat_basis`. `planner_sellthrough.srp_from_price`: incl-VAT price is the SRP; ex-VAT is grossed up by the tenant VAT rate; unknown basis gives `price_vat_basis_unknown`; no rate gives `vat_rate_not_configured`. The planner draft (`promo_plan_builder`) and aged-stock Promote (`stock_actions._srp_for_line`) use `srp`, not the raw price. Live price rows: 2,804 ex_vat, 59 inc_vat, so ex-VAT SRPs were understated by the VAT factor before this.
- **R-05:** `commercial_tenant_profile.configured_vat_rate_pct` returns only the tenant's own `vat_rate_pct` (None when unset). It is used for case-line `vat_rate` (case create refuses with `vat_rate_not_configured`) and the SOH check divisor (incl-VAT costs are withheld with the flag `vat_rate_not_configured`). Settings -> tenant profile has a VAT rate field that is empty until set. The store-map gazetteer is `data/<tenant.country code>_populated_places.csv`; with no country or no file the proposal is manual `no_gazetteer_for_country`. Live has tenant.country ZA, so the store map is unchanged.
- **Still built in elsewhere (not in R-05 scope):** `DEFAULT_VAT_RATE_PCT = 0.15` behind `vat_rate_pct()` (sell-through overview and others) and `support_bias` 0.15 fallback.