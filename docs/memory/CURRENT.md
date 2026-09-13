# CURRENT state

**Last updated:** 2026-09-13 (N-0020 implementer product + Playwright browser; engine close in this pass)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `c1b4311` (N-0019 Overview hub + coverage; ledger `60ee43c`) — N-0020 product not yet pinned

**Last ledger pin:** N-0019 validate + lease release (seq **416**). N-0020 leased/baselined/implement + reclaim seq **420** (stage **implement**) until close events land.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0018 complete**. **N-0019** implementer validate (GOV-008 pending). **N-0020** implementer in this pass. **Do not start N-0006. Do not reopen N-0013.** Independent GOV-008 for N-0019–N-0022 is a later session, different run/actor.
- **Product (Planning):** Lab `PlanningSurface` DomainOverview composition on `/lineup`. N-0009 `LineupContainer` relocated to `/lineup/cases`. `/commercial-planner` and `/roadmap` wrapped in `PlanningChrome`. LensTabs on leaves only. `navConfig.ts` Planning hrefs/labels unchanged. Coverage `docs/design/N0020_PLANNING_COVERAGE.md`.
- **NUMBER RULE** `cip` 2026-09-12 (`current_database()=cip` first): cases **29** / lines **2703** / plan units **273982** / shipped vs plan **20%** (6586/32509 on 26Q3) / lines not ready **2703** / economics flagged **0** (0 planner lines). Lab fixtures not copied.
- **Browser VERIFIED:** Playwright 1280×800 `/lineup` vs `/design-lab/planning` two-column; workflow href `/lineup/cases`; relocated assortment workspace; `/commercial-planner` DomainHeader + workspace; `/roadmap` DomainHeader + empty substrate. `browser_cdp` not used.
- **D-0002** remains the open decision (untouched). Live `/admin/mappings` still the deferred legacy queue leaf.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. Planning is **not** named — 1280 only.

**Next:** 1) N-0020 `evidence.add` + `node.stage` validate + `lease.release`. 2) N-0021 Administration then N-0022 Stock leftover leaves. 3) Independent GOV-008 vs N-0019–N-0022 (different actor/run). Do not self-complete N-0020.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React. Judge composition, not LabShell rail (BACKLOG-181).

**Deferred:** BACKLOG-174–181. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
