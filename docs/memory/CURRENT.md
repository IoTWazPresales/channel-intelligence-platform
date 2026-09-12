# CURRENT state

**Last updated:** 2026-09-12 (N-0019 implementer product + browser; engine validate skipped)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `2a59ce0` (N-0018 implementer validate; product `9e93c77`) — N-0019 product not yet pinned

**Last ledger pin:** programme snapshot includes N-0019–N-0022 adds (log seq **410**) and N-0019 lease/baseline/implement (seq **413**, node revision **3**, stage **implement**)

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0018 complete**. **N-0019–N-0022 chartered** (`NS10_D0008_REMAINDER_20260912` / gov-001). **N-0019** leased + baselined + staged implement (`NS10_OVERVIEW_20260912` / gov-001). **Do not start N-0006. Do not reopen N-0013.** Do not start N-0020 / N-0021 / N-0022 until N-0019 GOV-008.
- **Product (Overview):** Lab `OverviewSurface` two-column composition on `/brief` (Business dashboard ∥ Needs attention + pinned reports). `/dashboards`, `/reports`, `/inbox` wrapped in `OverviewChrome`. No LensTabs (lab Overview has none). `BriefPageContent.tsx` not deleted. `navConfig.ts` unchanged. Coverage `docs/design/N0019_OVERVIEW_COVERAGE.md`.
- **NUMBER RULE** `cip` 2026-09-12 (`current_database()=cip` first): dashboards **3** / widgets **6** / saved reports **3**; `GET /api/v1/brief/signals` **3** (`failed_imports`, `cover_breach`, `inbound_open`). Hub meta **3 signals · live from brief/signals**. Lab fixture KPIs not copied.
- **Browser VERIFIED:** 1280×800 `/brief` vs `/design-lab` two-column, attention **312px**; 390×844 `/brief?zone=attention` Attention-first; `/dashboards` and `/reports` DomainHeader at 1280; `/inbox` chrome wrap.
- **Engine skip (this pass):** `program.py` `evidence.add` / `node.stage` validate / `lease.release` **not applied**. Shell named `.eif/runtime/programme/program.py` twice → `CONTROL_PLANE_PROTECTED`. Node remains `in_progress` / `implement` / revision **3** / lease held until Warren runs those events or grants the engine command.
- **D-0002** remains the open decision (untouched). Live `/admin/mappings` still the deferred legacy queue leaf.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. Overview **Attention triage** is named — verified at 390×844.

**Next:** 1) Run N-0019 `evidence.add` + `node.stage` validate + `lease.release` via engine (commands blocked here). 2) Independent GOV-008 vs `NS10_OVERVIEW_20260912` (different actor/run). 3) Then N-0020 Planning. Do not self-complete N-0019.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React. Judge composition, not LabShell rail (BACKLOG-181).

**Deferred:** BACKLOG-174–181. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
