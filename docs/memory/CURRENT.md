# CURRENT state

**Last updated:** 2026-09-13 (D-0010 accepted Option A; N-0023 rail port awaiting GOV-008)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `6a2e912` (N-0023 CapabilityRail port; ledger `7bdb718`; views `f09ebdb`)

**Last ledger pin:** `abaf04b` programme rev **530**. Run `NS11_D0010_ACCEPT_20260913` / actor `operator` (seq 529–530). N-0023 **in_progress** at **validate** (lease released). Independent GOV-008 not recorded.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0018–N-0022 complete.** N-0023 chartered and implemented (rail tokens). Do not reopen N-0013. D-0002 remains open.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set (Overview has no tabs; Data 13 rail leaves vs 4 grouped tabs with products/customers/duplicates/CST rail-only; Funding tabs include a substrate leaf the rail omits). Only Stock is a true duplicate — Stock-level, not IA. No IA change implemented. Evidence `.eif/audit/NS11_RAIL_20260913/D0010_OPERATOR_ACCEPTANCE.md`.
- **N-0023:** production `CapabilityRail` ports LabShell `1f434e4`/`130189e`. Collapsed-active = no fill, primary icon + weight 600. Playwright 1280 + 390 drawer. vitest 4/4. Sticky CSS VERIFIED; pin-during-scroll UNVERIFIED (Funding+Market persist left ~52px rail scroll).
- **GOV-008 N-0019–N-0022:** still the last independent review (`docs/design/gov-008-n0019-n0022.md`). Do not treat BACKLOG-181 as a defect of those nodes.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0023 drawer rail verified at 390. Attention triage is named (N-0019).

**Next:** Independent GOV-008 on N-0023 (`gov-008` vs impl `NS11_RAIL_20260913`) in a new chat. D-0002 when Warren chooses. Stock tab/rail duplication is a Stock-level question, not programme IA.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React. Rail tokens now match LabShell (N-0023). Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
