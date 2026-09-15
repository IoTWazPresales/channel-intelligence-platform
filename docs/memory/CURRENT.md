# CURRENT state

**Last updated:** 2026-09-15 (N-0026 implementer validate; GOV-008 not recorded)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `78c98fd` (N-0026 product). Last ledger pin: `00db1ec` (programme snapshot **655**). Last evidence pin: `ced70ef`. Last views pin: `6000442`. Run `NS14_PROMO_PLAN_20260914` / actor `gov-001`.

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022`

## On feat/ns-2-brief-nav-collapse

- **Programme:** PRG-20260831T145514. **N-0018–N-0024 complete.** **N-0025** `in_progress` / `validate`; GOV-008 **VERIFIED_WITH_LIMITATIONS** — not completed. **N-0026** `in_progress` / `validate`; lease released; independent GOV-008 not recorded. Do not reopen N-0013. D-0002 remains open.
- **D-0010 accepted** Option A: keep rail expansion. Rail and tabs are not one destination set.
- **N-0026 implementer:** propose a promotion plan from customer + period on Promotion Planner (D-0008). Playwright 1280: Start work **Create promotion plan** → `/promotions?propose=1`; Computer Mania 2026Q2 compose **40** `commercial_lineup_line` rows, **10** same-customer comparables. Create draft not confirmed. Strip: drafts 0 / ended 74 / settled 210 / planned reserve $253k / actual support $650k — no 257%. UNCOVERED → BACKLOG-183–186. Evidence `.eif/audit/NS14_PROMO_PLAN_20260914/implementer-evidence.md`. Do not run GOV-008 on this node in this session.
- **N-0025 GOV-008:** independent clicks closed CST (to Choose file), settle (to Confirm settlement on case 46), steward queue (empty legacy; 2814 per-job). Viewer live: no Start work verbs. Planner live UNVERIFIED (no tenant user). Payments “Back to Payments lens” same-URL residual → BACKLOG-182. Evidence `.eif/audit/GOV008_N0025_20260914/independent-rendered-review.md`. Do not remediate N-0025.
- **N-0025 implementer:** one Start work panel on Overview `/brief`. Role-gated verbs route to existing screens (unified lineup, CST import, inbound import, case book, steward queue). Payments/Terms default to wizard/editor. Claims rows route to Import Center `cpor_claim_evidence` and Case book. Data four LensTabs kept; also-here strip names rail-only leaves. Sell-through filters/grid show names; API still ids. Empty Business dashboard compact below; Attention 431px at 1280 (not lab 312). Evidence `.eif/audit/NS13_START_WORK_20260914/implementer-evidence.md`.
- **N-0023 GOV-008 VERIFIED** vs impl `NS11_RAIL_20260913`. Sticky pin-during-scroll independently VERIFIED.
- **N-0024 GOV-008 VERIFIED_WITH_LIMITATIONS** vs impl `NS12_NAV_DEST_20260913`. Named destinations land on the named jobs.
- **GOV-008 N-0019–N-0022:** still recorded in `docs/design/gov-008-n0019-n0022.md`.

**Mobile:** DIRECTION §6 desktop-primary with named 390px workflows. N-0025 Start work VERIFIED at 390×844 (above Attention).

**Next:** Node 2 — steward queue by failure type (new run / actor `gov-001`). Do not reuse `NS14_PROMO_PLAN_20260914` or `GOV008_N0025_20260914`. Do not run GOV-008 on nodes 1–4. Do not remediate N-0025.

**Design language:** FROZEN v1.1 is **demoted**. Production follows implemented design-lab React. Do not cite a frozen design-language version or grammar number.

**Deferred:** BACKLOG-174–180. BACKLOG-181 token port done; IA settled D-0010 Option A. BACKLOG-182 Payments same-URL leftover. BACKLOG-183–186 N-0026 UNCOVERED (listing/competitor join; observed WoC; uplift; A2-05 other-customer ranking). BACKLOG-173. Budget ledger writer not chartered. Leftover `/market` stub. Stores master grid UNCOVERED. Cross-job steward accept/reject until Design Language v2. Pin-as-widget on Overview UNCOVERED. `/dashboard` legacy UNCOVERED.

**Env:** local Windows. Web `:3000` + API `:8001`. Sync/async engine on `cip` (`current_database()=cip`).
