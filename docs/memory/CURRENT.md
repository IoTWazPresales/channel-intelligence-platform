# CURRENT state

**Last updated:** 2026-09-14 (N-0025 implementer validate)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `04695c1` (N-0025 product/docs). Last ledger pin: `47602ff` (programme snapshot **613**). Last views pin: `a7a9b6b`. Run `NS13_START_WORK_20260914` / actor `gov-001`.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0018–N-0024 complete.** **N-0025** `in_progress` / stage `validate`; lease released. Do not complete in the implementation run. Do not reopen N-0013. D-0002 remains open.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.
- **N-0025 implementer:** one Start work panel on Overview `/brief`. Role-gated verbs route to existing screens (unified lineup, CST import, inbound import, case book, steward queue). Payments/Terms default to wizard/editor. Claims rows route to Import Center `cpor_claim_evidence` and Case book. Data four LensTabs kept; also-here strip names rail-only leaves. Sell-through filters/grid show names; API still ids. Empty Business dashboard compact below; Attention 431px at 1280 (not lab 312). Evidence `.eif/audit/NS13_START_WORK_20260914/implementer-evidence.md`.
- **N-0023 GOV-008 VERIFIED** vs impl `NS11_RAIL_20260913`. Sticky pin-during-scroll independently VERIFIED.
- **N-0024 GOV-008 VERIFIED_WITH_LIMITATIONS** vs impl `NS12_NAV_DEST_20260913`. Named destinations land on the named jobs.
- **GOV-008 N-0019–N-0022:** still recorded in `docs/design/gov-008-n0019-n0022.md`.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844 (above Attention).

**Next:** Independent GOV-008 for N-0025 (`GOV008_N0025_*` / actor `gov-008`) vs impl `NS13_START_WORK_20260914`. Do not complete N-0025 in that review until the reviewer records it. Then D-0002 when Warren chooses.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
