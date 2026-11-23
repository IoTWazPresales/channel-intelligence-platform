# CURRENT state

**Last updated:** 2026-11-23 — BACKLOG-268 store-map revisions implemented. Last prior live acceptance: 22 November (`c685bf63`).
**Branch:** `feat/integrate-20261103`. Confirm HEAD with `git rev-parse` after merge.
**Next agent:** Discovery V2 is next unless Warren reprioritizes. Read [durable handoff](../handoffs/2026-11-23/README.md), [map revision brief](../handoffs/2026-11-23/MAP_FEEDBACK.md), and [Targets status](../handoffs/2026-11-23/TARGETS_STATUS.md).

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

## Store map (BACKLOG-268) — implemented 2026-11-23, provider still unanswered

- Default SVG store map and the default-off MapLibre prototype now share the Shipments filled point/halo marker language (`MapMarker`; proposed pins use a dashed outer ring, not hollow-only rings), `MapPanel` theme in light and dark, and the shipping map box ratio. Pins, proposed pins, details and confirm/skip/bulk controls sit in the right-hand panel with internal scrolling. Existing confirm writers were reused; nothing was auto-confirmed.
- MapLibre attribution is the compact collapsible (i) control, with required OSM/provider credit retained. Tile provider is still unanswered and was not configured or enabled. Prototype remains off by default (`cip.storeMap.prototype.v1`).
- Revision-reference images remain in `docs/handoffs/2026-11-23/assets/`. Last known live payload: 310 stores / four customers / 192 proposed points / zero confirmed. Fourways A02 and Clearwater A01 stay unverified; BACKLOG-267 before any confirmation.
- Warren has not yet accepted the revised look on the live screen.

## Targets / Dashboard V2 ? not done

- Only a design spec and standalone HTML Dashboard/target-builder prototypes were recovered. Submit opens an illustrative dialog; no matching new Targets route/API/product implementation was found. Draft dark/light styling exists; the requested live redesign is not delivered.
- Exact original drafts now preserved in`docs/design/dashboard-v2/` and`docs/specs/DASHBOARD_V2.md`; they retain design-only provenance. See handoff/TARGETS_STATUS.md for source evidence and limitations.
- Earlier Dashboard visual direction approved in **both themes**, stock health BELOW sales charts. Expanded replenishment/aged-stock mock-up/detail/build pending. Previous saved light screenshot duplicated dark and is not light-theme acceptance evidence. BACKLOG-269 tracks remaining delivery.

## Next ? one task / one delegated agent at a time

1. BACKLOG-268 implemented; Warren reviews the live default store map. Do not enable a tile provider or confirm store locations (BACKLOG-267).
2. Discovery V2 is next unless reprioritized: committed S1/S2/S3c/S5 not integrated; S3a dirty foundations/incomplete lint; S4 dirty/failed saved checks; S3b Crawlee+Playwright finder pending. Keep live Preview-only and exact GTIN/model evidence. No automatic schedule activation.
3. Dashboard/Targets delivery per accepted theme/placement decisions, then AI-assisted import implementation/three-customer clone proof. AI proposes; steward confirms fixed rules. Requested library review follows original live lanes.
4. Recovery manifests name every relevant branch/base and dirty file. Verified Git bundle and ZIP preserve seven separate refs plus three dirty worktrees/15untrackedfiles; restore only into new worktrees after inspection, never blindly into integration.

## Boundaries / blockers

- No main push/promotion. Map tile provider remains unconfigured; no store-location confirmation or DB mutation is authorized by BACKLOG-268.
- Codex session registration was absent on22November. Future protected DB work requires installed operator mechanism; never fabricate state/self-grant/borrow a session/use missing hooks as permission. Do not set ALLOW_TESTS_ON_DEV_DB casually. Cloud guard denial is a stop condition.
- No hook/policy/.claude/CLAUDE.md edits; engineering-rules.mdc missing and not invented. Preserve existing failed artifacts and the two-attempt stop rule. Agent quotas may be exhausted; all outstanding scope is durable outside chat.
