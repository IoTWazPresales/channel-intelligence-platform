# CURRENT state

**Last updated:** 2026-09-13 (N-0023 BACKLOG-181 rail port; D-0010 proposed)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `6a2e912` (N-0023 CapabilityRail port; ledger `7bdb718`; views `f09ebdb`)

**Last ledger pin:** programme rev **528**. Run `NS11_RAIL_20260913` / actor `gov-001`. N-0023 **in_progress** at **validate** (lease released). Independent GOV-008 not recorded.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0018–N-0022 complete.** N-0023 chartered and implemented (rail tokens). Do not reopen N-0013. D-0002 remains open. **D-0010 proposed** (rail vs tabs).
- **N-0023:** production `CapabilityRail` ports LabShell `1f434e4`/`130189e`. Collapsed-active = no fill, primary icon + weight 600. Playwright 1280 + 390 drawer. vitest 4/4. Sticky CSS VERIFIED; pin-during-scroll UNVERIFIED (Funding+Market persist left ~52px of rail scroll).
- **D-0010:** recommended Option A — keep rail expansion. Lists are not the same destinations (Data 13 vs 4 tabs). Operator accept/reject before IA work. Evidence `.eif/audit/NS11_RAIL_20260913/D0010_RAIL_VS_TABS.md`.
- **GOV-008 N-0019–N-0022:** still the last independent review (`docs/design/gov-008-n0019-n0022.md`). Do not treat BACKLOG-181 as a defect of those nodes.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0023 drawer rail verified at 390. Attention triage is named (N-0019).

**Next:** Warren accept/reject D-0010 (A keep expansion / B domains-only later / C remove matching tabs). Independent GOV-008 on N-0023. D-0002 when Warren chooses.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React. Rail tokens now match LabShell (N-0023). Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA is D-0010. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
