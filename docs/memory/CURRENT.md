# CURRENT state

**Last updated:** 2026-11-24 — store map review fixes (smaller semi-transparent land dots, Move+undo, shipping-map glow). Discovery V2 merged and live (a6f498ce, migration 0066); stock-based listing scope (BACKLOG-270) merged, off until a tenant saves it. Last prior live acceptance: 22 November (`c685bf63`).
**Branch:** `feat/integrate-20261103`. Confirm HEAD with `git rev-parse` after merge.
**Next agent:** Next wave item: Dashboard V2 and Targets (BACKLOG-269) unless Warren reprioritizes. Read [durable handoff](../handoffs/2026-11-23/README.md).

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

- Discovery V2 merged `a6f498ce` (Crawlee, Playwright, extruct, price-parser, tldextract, protego, ddgs; licences in the merge commit). Migration `20261123_0066_web_discovery` applied on live as owner after a 3.36 GB backup. Live Discovery settings saved 24 Nov 00:57 by Warren's approval (ZA, .co.za/.com, free web search, 5 s/10/20 s, browser on); schedule OFF. Live Discover button is disabled while the API reports live fetch off (D-0061 worker-only); Warren to decide.
- Stock-based listing scope (BACKLOG-270) uses existing stock facts and the existing poll beat. Off until `listing_scope.settings` is saved for the tenant.

## Store map (BACKLOG-268) — OpenFreeMap chosen 2026-11-23

- Sell-through shows the MapLibre store map when this tenant has a TileJSON URL in tenant settings. No provider URL is hardcoded in code or migrations; Warren chose OpenFreeMap and it is stored as this tenant's setting via the existing settings API. The SVG dotted basemap remains the fallback and is still used by On the water. Attribution stays the compact OSM/provider (i) control.
- Shared land dots stay on the dense 0.7 deg / 4px grid, but are smaller and semi-transparent (SVG stroke 1.0 at about 0.42–0.45 opacity; MapLibre dotted-land uses a tighter, ~0.42 alpha stipple) so the land reads cleanly.
- Confirmed pins are not draggable until the user presses Move pin. Unconfirmed and proposed pins stay draggable. Pin moves can be undone in the session with Ctrl+Z / Cmd+Z or Undo, through the same save path. Boundary rings were replaced with the shipping-map soft glow (`MapMarker`). No store locations were auto-confirmed. BACKLOG-267 still applies. Fourways A02 and Clearwater A01 stay unverified.

## Targets / Dashboard V2 ? not done

- Only a design spec and standalone HTML Dashboard/target-builder prototypes were recovered. Submit opens an illustrative dialog; no matching new Targets route/API/product implementation was found. Draft dark/light styling exists; the requested live redesign is not delivered.
- Exact original drafts now preserved in`docs/design/dashboard-v2/` and`docs/specs/DASHBOARD_V2.md`; they retain design-only provenance. See handoff/TARGETS_STATUS.md for source evidence and limitations.
- Earlier Dashboard visual direction approved in **both themes**, stock health BELOW sales charts. Expanded replenishment/aged-stock mock-up/detail/build pending. Previous saved light screenshot duplicated dark and is not light-theme acceptance evidence. BACKLOG-269 tracks remaining delivery.

## Next ? one task / one delegated agent at a time

1. Warren reviews the latest live store-map fixes (smaller dots, Move+undo, glow). Do not confirm store locations (BACKLOG-267).
2. Discovery V2 is next unless reprioritized: committed S1/S2/S3c/S5 not integrated; S3a dirty foundations/incomplete lint; S4 dirty/failed saved checks; S3b Crawlee+Playwright finder pending. Keep live Preview-only and exact GTIN/model evidence. No automatic schedule activation.
3. Dashboard/Targets delivery per accepted theme/placement decisions, then AI-assisted import implementation/three-customer clone proof. AI proposes; steward confirms fixed rules. Requested library review follows original live lanes.
4. Recovery manifests name every relevant branch/base and dirty file. Verified Git bundle and ZIP preserve seven separate refs plus three dirty worktrees/15untrackedfiles; restore only into new worktrees after inspection, never blindly into integration.

## Boundaries / blockers

- No main push/promotion. OpenFreeMap is this tenant's setting only, not a product default. No store-location confirmation is authorized.
- Codex session registration was absent on22November. Future protected DB work requires installed operator mechanism; never fabricate state/self-grant/borrow a session/use missing hooks as permission. Do not set ALLOW_TESTS_ON_DEV_DB casually. Cloud guard denial is a stop condition.
- No hook/policy/.claude/CLAUDE.md edits; engineering-rules.mdc missing and not invented. Preserve existing failed artifacts and the two-attempt stop rule. Agent quotas may be exhausted; all outstanding scope is durable outside chat.
