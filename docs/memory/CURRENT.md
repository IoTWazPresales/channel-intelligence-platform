# CURRENT state

**Last updated:** 2026-09-13 (N-0022 implementer product + Playwright browser; engine close in this pass)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `712d9d8` (N-0022 leftover stock leaves; N-0021 `fec7d0e`; N-0020 `ce88549` / ledger `ff8a97c`)

**Last ledger pin:** N-0020 validate + lease release (seq **423**). N-0021 engine seq **427–429**. N-0022 engine seq **433–435** (evidence.add / validate / lease.release). Ledger `git add` of programme paths denied `CONTROL_PLANE_PROTECTED`.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0018 complete**. **N-0019–N-0022** implementer validate (GOV-008 pending). **Do not start N-0006. Do not reopen N-0013.** Independent GOV-008 for N-0019–N-0022 is a later session, different run/actor.
- **Product (Planning / Admin):** unchanged this node. Coverage `docs/design/N0020_PLANNING_COVERAGE.md`, `docs/design/N0021_ADMIN_COVERAGE.md`.
- **Product (Stock leftover leaves):** Lab ThinLens on `/channel-intelligence` and `/forecasts`. CST grid relocated to `/channel-intelligence/workspace`. Forecast grid + compute-from-history relocated to `/forecasts/workspace`. Cover / Movement / Execution untouched. `navConfig.ts` Stock hrefs/labels unchanged. Coverage `docs/design/N0022_STOCK_LEAVES_COVERAGE.md`.
- **NUMBER RULE** Administration `cip` 2026-09-13: users **2** / running **0** (64 pending not running) / failed 24h **0** / SQL 7d **0**.
- **NUMBER RULE** Stock leftover `cip` 2026-09-13 (`current_database()=cip` first): current week **W37**; CST this week **0**; latest CST **W40** 2026-09-28 (Computer Mania · Game, not TechMart); sell-out trailing 8 **0 of 8**; latest sell-out **W24** 2026-06-12; forecast rows **38625** on relocated workspace only.
- **Browser VERIFIED:** Playwright 1280×800. Admin hub vs lab (prior). Stock: lab W36 ThinLens vs production W37 honesty; workspace CST grid; `/forecasts` honesty without compute CTA; `/forecasts/workspace` compute CTA; `/stock?lens=cover` Network cover. `browser_cdp` not used.
- **D-0002** remains the open decision (untouched). Live `/admin/mappings` still the deferred legacy queue leaf.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. Planning, Administration, and these leftover stock leaves are **not** named — 1280 only.

**Next:** Independent GOV-008 vs N-0019–N-0022 (different actor/run). Operator: commit programme ledger (`CONTROL_PLANE_PROTECTED` on `git add` of those paths). Do not self-complete these nodes.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React. Judge composition, not LabShell rail (BACKLOG-181).

**Deferred:** BACKLOG-174–181. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
