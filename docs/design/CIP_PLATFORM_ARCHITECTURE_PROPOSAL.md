# CIP Full-Platform Architecture Proposal

**Status:** Awaiting operator product/design approval (N-0013)  
**Date:** 2026-09-02  
**Branch:** `feat/ns-2-brief-nav-collapse`  
**Evidence base:** `docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md` (50 capabilities · BLN-0001)  
**Programme:** PRG-20260831T145514 · node **N-0013**

---

## 1. Executive summary

Full-platform reconciliation proves the current programme charter is **incomplete**: it locked a six-container North Star as immutable product architecture, excluded Reports and Admin from redesign scope, and allowed frontier construction (N-0010 Response, N-0011 Steward) into an IA that reconciliation shows is only **partially converged** (double chrome, dual nav truth, latent routes, 10 API-without-UI gaps).

EIF concludes:

1. The **job-container model** (attention → plan → channel position → funding → commercial action → data trust) remains the strongest fit for 50 reconciled capabilities — but **buyer-facing names, utility reach, URL honesty, and shell convergence** must be redesigned before further container construction.
2. `CIP_DESIGN_LANGUAGE.md` FROZEN v1.1 remains the **quality/craft benchmark** (tokens, grammars, Read strip, grid discipline) — not an immutable IA or naming spec.
3. **N-0010, N-0011, and all post-reconciliation implementation** are dependency-blocked until Warren approves this package.

**Proposed spine (6 jobs + 2 utilities):**

| # | Proposed label | Job | Grammar |
|---|---|---|---|
| 1 | **Brief** | What needs attention today | 3 — signal blotter |
| 2 | **Plan** | Assortment & buy planning | 2 — instrument + grid |
| 3 | **Channel** | Channel position & execution | 2 — lens switcher |
| 4 | **Settlement** | Funding & claims | 1 — queue + case |
| 5 | **Actions** | Ranked commercial response | 4 — actions + calculator |
| 6 | **Data** | Imports & master data | 5 — factory + worklists |
| U | **Reports** | Builder, dashboards, inbox | 6 — Composer |
| U | **Admin** | Users, settings, ops, audit | utility |

---

## 2. What was wrong with the existing programme frame

| Finding | Evidence | Programme action |
|---|---|---|
| Charter assumed six containers are settled product architecture | `PROGRAM.yaml` charter assumption: "Do not reopen the accepted product architecture" | Charter amended — architecture is hypothesis until N-0013 operator acceptance |
| Reports and Admin excluded from redesign | Charter `exclusions: Reports, Admin` | Removed from exclusions; utility redesign in scope |
| Frontier nodes build into unsettled IA | N-0010/N-0011 proposed with old names and `/commercial-planner` residue | Blocked pending N-0013; re-scoped titles on approval |
| Reconciliation not wired to programme | `CIP_FULL_PLATFORM_RECONCILIATION.md` orphan to charter | Registered as authoritative evidence for N-0013 |
| Completed NS tranches treated as final IA | N-0004–N-0009 complete under old charter | **Preserved** as implementation evidence; convergence waves follow approval |
| N-0006 ledger drift | Product shipped; node `proposed` | Hygiene item — not architecture-blocked; Warren decision on backfill |

---

## 3. Architecture challenge — container count

### Alternatives considered

| Model | Verdict | Why |
|---|---|---|
| **Retain 6+2 with renamed jobs** (recommended) | **ACCEPT** | Reconciliation matrix maps cleanly; domain boundaries (plan origination vs execution vs funding vs action vs data) are real; grammars 1–6 already align |
| **Merge Plan + Channel** | REJECT | Violates BLN-0001 boundary: lineup owns plan origination; stock/channel measures execution against plan |
| **Merge Settlement + Actions** | REJECT | Funding book (grammar 1) vs ranked response (grammar 4) are distinct operator jobs; B4 compose → settlement case is a handoff, not a merge |
| **Promote Reports to primary job** | REJECT | Grammar 6 Composer is episodic output, not daily operator workflow; utility with restored sub-links is sufficient |
| **8+ primary containers** | REJECT | No reconciliation evidence that 50 capabilities need more top-level jobs; would recreate the 30-leaf nav problem |

**Conclusion:** Container **count** survives challenge; **names, utility menus, URL namespace, and shell chrome** do not.

---

## 4. Proposed buyer-facing naming

Hard rules (from `NAMING.md`, retained): operator-owned nouns; no implementation language; survives aloud in a business review.

| Current | Proposed | Disposition | Rationale |
|---|---|---|---|
| Brief | **Brief** | RETAIN | Credible daily attention queue for channel ops |
| Lineup | **Plan** | RENAME | "Lineup" reads as shelf assortment; buyers expect *Plan* / *Buy plan* for net-requirement origination |
| Stock | **Channel** | RENAME | Four lenses exceed "stock"; *Channel* communicates position & execution across the journey |
| Settlement | **Settlement** | RETAIN | CPOR / trade-spend settlement is conventional |
| Response | **Actions** | RENAME | *Actions* communicates ranked commercial decisions; "Response" is opaque |
| Steward | **Data** | RENAME | First-time buyers understand *Data* (imports + masters); subtitle "Imports & masters" in onboarding |
| Reports | **Reports** | RETAIN | Utility label clear; expand sub-nav |
| Admin | **Admin** | RETAIN | Utility label clear; expand sub-nav |

### Secondary lens / route terms

| Term | Proposed |
|---|---|
| Movement | **Movement** (retain) |
| Execution | **Fill vs plan** (rename from "Execution") |
| Cover | **Cover** (retain) |
| Inbound | **Inbound** (retain) |
| Commercial Planner (legacy) | Absorb into **Actions**; retire hub as standalone |
| CPOR Cases | **Settlement cases** (route under `/settlement`) |

---

## 5. Information architecture

### 5.1 Primary spine

```
Channel Intelligence
  Brief          ← landing; /brief; absorbs dashboard/exceptions/coach
  Plan           ← /plan (was /lineup); net requirement, approval
  Channel        ← /channel?lens=* (was /stock); Cover|Movement|Fill vs plan|Inbound
  Settlement     ← /settlement (was /commercial-planner/cpor-cases)
  Actions        ← /actions (was /commercial-planner + orphans)
  Data           ← /data (was /admin/imports hub + masters)
  ─────────
  Reports        ← builder · dashboards · inbox (RESTORE sub-links)
  Admin          ← users · settings · sql · ops · audit (RESTORE sub-links)
```

### 5.2 Middleware redirects (transition)

Legacy routes retained as redirects until Wave 3 retirement:

| Legacy | Target |
|---|---|
| `/dashboard`, `/exceptions`, `/getting-started` | `/brief` |
| `/lineup`, `/buy-plans` | `/plan` |
| `/sell-out`, `/plan-vs-executed`, `/shipping`, `/inventory` | `/channel?lens=…` |
| `/commercial-planner/cpor-cases` | `/settlement` |
| `/commercial-planner` | `/actions` |
| `/admin/imports` | `/data` |

### 5.3 Context routes (preserved, spine-prefixed)

`/forecasts`, `/channel-intelligence`, `/budgets`, `/budget-requests`, `/listing-capture`, `/market` (parked), `/roadmap` (parked).

### 5.4 Capability accounting (reconciliation matrix)

All 50 rows in `CIP_FULL_PLATFORM_RECONCILIATION.md` §6 map to a proposed home:

| Decision class | Count | Post-approval home |
|---|---|---|
| KEEP | 18 | Unchanged capability; may move URL/chrome |
| MERGE | 9 | Brief, Channel lenses, Plan, Settlement portfolio |
| REDESIGN | 4 | Spine, Settlement queue, Plan container, Cover lens |
| RESTORE | 4 | Reports utility (dashboards, inbox); Admin utility (sql, ops, audit) |
| BACKLOG | 9 | Explicit deferrals with TRIGGER (unchanged) |
| NEEDS PRODUCT DECISION | 6 | **Resolved in this proposal** (see §5.5) |
| RETIRE | 0 | No silent retirement |

### 5.5 Product decisions resolved (for approval)

| Reconciliation item | Proposal |
|---|---|
| Stock container label | **Channel** |
| Steward container label | **Data** with subtitle |
| Commercial planner fate | **Absorb** into Actions; hub tabs become Actions lenses/workspaces |
| Promotions / pricing / competition / roadmap | **Actions** evidence tools; standalone routes redirect; roadmap/market stay parked |
| Mapping queue page | **Retire UI** on trigger; engine remains in Data steward |
| Dashboard KPI cards vs Brief | **Brief** is complete replacement; KPI cards not restored as landing |

---

## 6. UI redesign direction

### 6.1 Shell (Phase A)

- Extend **brief-mode slim chrome** to all job containers — eliminate double `AppBar` on Channel, Settlement, Plan.
- Single nav truth: `spineNav.ts` authoritative; `navConfig.ts` derives breadcrumbs only.
- Mobile: drawer spine for all containers (not Brief-only).
- Utility flyouts: Reports and Admin expose full sub-link sets reconciliation marked RESTORE.

### 6.2 Primitive library (Phase B)

Extract before Wave 3 legacy migration (reconciliation §2.4):

P0: Workbench chrome kit, ScopeBar  
P1: Grid skin, empty/loading/error states  
P2: Confirm dialog, readiness chips, lens switcher  
P3: Pagination footer, toasts, drawer chrome

Location: `apps/web/src/workbench/` + token extensions in `packages/ui`.

### 6.3 Surface migration (Phase C)

| Wave | Scope |
|---|---|
| **C1 — NS parity** | Rename spine; URL honesty; remove KPI cards from Channel Movement; Inbound lens workbench chrome |
| **C2 — Data factory** | N-0011 re-scoped as Data container |
| **C3 — Actions factory** | N-0010 re-scoped as Actions container |
| **C4 — Legacy admin/commercial** | Adapter migration; retire fallback pages |

### 6.4 Design language relationship

FROZEN v1.1 **grammars, tokens, Read strip, grid discipline, and interaction honesty rules** apply to all waves. Container **labels** and **IA** are superseded by this proposal when approved. BACKLOG-157 (inert-control honesty) becomes a design-language amendment in Phase B.

---

## 7. Downstream programme impact

| Node | Status after N-0013 submission | Action on approval |
|---|---|---|
| N-0004–N-0009 | **complete** (preserved) | Convergence waves C1; no re-open |
| N-0012 | **complete** | Unchanged |
| N-0006 | **proposed** | Ledger hygiene — independent of IA |
| N-0010 | **blocked** | Re-title NS-6 → Actions container; depends N-0013 |
| N-0011 | **blocked** | Re-title NS-7 → Data container; depends N-0013 |
| N-0013 | **ready** (operator acceptance pending) | This document + rendered evidence |

---

## 8. High-fidelity evidence

| Artifact | Path |
|---|---|
| Desktop shell overview | `.eif/audit/NS_RECONCILE_20260902/platform-shell-desktop.html` |
| Mobile shell | `.eif/audit/NS_RECONCILE_20260902/platform-shell-mobile.html` |
| Channel container (Cover lens) | `.eif/audit/NS_RECONCILE_20260902/channel-cover-desktop.html` |
| Gallery index | `.eif/audit/NS_RECONCILE_20260902/index.html` |
| Rendered verification | `.eif/audit/NS_RECONCILE_20260902/rendered-verification.md` |
| Independent review | `.eif/audit/NS_RECONCILE_20260902/independent-rendered-review.md` |

View locally: open `index.html` in a browser, or `file://` paths at 1280px and 390px viewports.

---

## 9. Operator approval package

Warren is asked to approve **one** decision:

> **Adopt the proposed full-platform architecture** — 6 job containers (Brief · Plan · Channel · Settlement · Actions · Data) + 2 utilities (Reports · Admin) with the naming, IA, shell direction, and migration waves in this document — as the governing product frame for all subsequent CIP UI construction.

**Approve** → EIF unblocks N-0010/N-0011 (re-scoped), updates `CIP_NAV_MAP.md` and `NAMING.md`, begins Phase A shell work.  
**Reject or amend** → Record decision on N-0013; no container construction proceeds.

---

*Generated by EIF programme node N-0013. Implementation change scope: NONE until operator acceptance.*
