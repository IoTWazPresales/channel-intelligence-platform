# Staged work plan — remaining CIP work

**Date:** 2026-09-21 · **Refreshed:** 2026-09-24 (run `PROGRAMME_20260924`) · **EIF node:** N-0030 · **Branch:** `feat/ns-2-brief-nav-collapse`
**Inputs:** Warren's decisions of 2026-09-21 (§0) and 2026-09-23 (D-a..D-h, §0b) · `docs/ROADMAP.md` · `docs/BACKLOG.md` after the N-0030 audit (`.eif/audit/BACKLOG_AUDIT_20260921/BACKLOG_AUDIT.md`) · the programme ledger.
**Status:** **refreshed** — absorbs the 21 Sep §3 answers, D-g, and the stale items the 23 Sep briefing found (2.6, 2.7, 2.8, 3.1, 3.5, `e264410`, node count, 4.5 and Stage 9 already built).

> **The ledger is the queue.** Since 2026-09-24 every item below has a ledger node (column "Node"). `python .eif/runtime/programme/program.py frontier` returns the next item; this file is the narrative, the ledger is the truth. Where they disagree, the ledger wins.
>
> Code is evidence; this plan is a claim. Measured figures were read from the running tree or from `cip` (read-only, `current_database()=cip` printed first) on the date given.

**Ledger at refresh (2026-09-24):** 71 nodes (N-0001..N-0072; N-0064 reserved for D-h). 22 complete, 5 rejected, 8 in progress (N-0028..N-0035), 36 proposed (N-0036..N-0072), 6 of them blocked on Warren (N-0060, N-0063, N-0065, N-0068, N-0071, N-0072). The 2026-09-21 text said "29 nodes"; that was already stale at 35 when the 23 Sep briefing ran.

---

## 0. Decisions this plan is built on (Warren, 2026-09-21)

| # | Decision | Consequence in this plan |
|---|----------|--------------------------|
| D1 | **Fresh independent GOV-008** for N-0028 and N-0029. No self-completion. | Queue item 3: one fresh reviewer per node, own run and actor. |
| D2 | **Density: 40/40 rows + 13px grid type**, not the lab's 36/36. | Stage 2.1–2.3 — **done** (`5e70f33`, `a4fe957`, `459f4c9`); review nodes N-0031 and N-0035. |
| D3 | **All columns pickable** on fact grids. | Stage 2.4 = N-0034 (one generic picker). |
| D4 | `CporCaseWorkspace`'s five orphaned tabs **are needed** → settlement desk. | Stage 2.7 — tabs **done** (`ff118ec`, N-0032); retirement is N-0044 (D-c). |
| D5 | P1 sign-off: discover, then ask. | **Dissolved by discovery:** P1 exited 2026-08-01. Nothing to sign. |
| D6 | Build features 1–9. **Feature 10 (CST historical backfill) excluded.** | Stage 7 uplift and Stage 6 depth items are data-gated. |
| D7 | Customer/distributor **codes never in identity columns**. | Stage 2.4 name-only sweep + `Customer code` / `Distributor code` columns. |
| D8 | External access: **R0/month**, local, Cloudflare Quick Tunnel, only once auth is real. | 3.1 and 3.5 **done** (`26a6e1a`, N-0033). |
| D9 | Use EIF for the checks it does. | Every item is a ledger node (§1). |

### 0a. Warren's answers to the 21 Sep §3 questions (recorded 2026-09-21; previously only in `CURRENT.md`)

| §3 question | Answer | Status |
|---|---|---|
| 1. 2.2 `packages/ui/**` in `change_paths`? | **Yes** — Warren amended `AUTONOMY_POLICY.md` (`e264410`). | Applied; 2.2 shipped on option (a) (`a4fe957`). |
| 2. 4.1 repair of inverted `dim_product` windows? | **Agent decides the rule; clone run first; cip apply only with counts shown.** | N-0047. Per the 23 Sep stop rules nothing writes to cip this run: the cip apply is listed ready-for-cip. |
| 3. 4.4 line-window migration? | **Approved** — write and prove on `cip_test`; `alembic upgrade head` on cip needs an explicit "run". | N-0050. |
| 4. 3.2 role matrix? | **Enforce on the existing admin/steward/planner/viewer roles; Warren adds users.** No new roles. | N-0038. |
| 5. BACKLOG-198 catalogue grain? | **Unknown, stays open.** | N-0068 blocked (D-0023). |
| 6. 3.5 tunnel? | **Instructions given, Warren runs.** | Done (N-0033, `docs/PILOT_TUNNEL_RUNBOOK.md`). |
| 7. 2.9 design-lab? | **Keep lab as a fixture skin over production primitives.** | N-0054. |

### 0b. Warren's decisions of 2026-09-23 (ledger D-0012..D-0019, accepted)

| # | Ledger | Decision (short) | Where it lands |
|---|---|---|---|
| D-a | D-0012 | Approve N-0030 once this file is refreshed. | This refresh. |
| D-b | D-0013 | Grid search, saved views, export = three shared workbench-ui nodes after N-0034; reuse the inbound-shipments optional-columns pattern; no migration. | N-0041, N-0042, N-0043. |
| D-c | D-0014 | `CporCaseWorkspace` retires once the desk absorbs BACKLOG-202; the two orphan panels are mounted if unique, deleted if duplicate. | N-0044. |
| D-d | D-0015 | Untracked files → archive outside the repo; never delete; commit only real source. | N-0045. |
| D-e | D-0016 | 4.6 and 4.7 are **not decided**. | N-0071, N-0072 blocked. |
| D-f | D-0017 | No customer code mint pass; no remap of the 7 verified rows. | Holds 4.5 use. |
| D-g | D-0018 | Sellable BU grain = **every `dim_product.product_line` value**, not the brief's five. Hardcoded five-line sets are defects. | N-0040; also N-0065, N-0057. |
| D-h | D-0019 | Agent recommends proposed-vs-executed intelligence; chartered unstarted; not built. | N-0064 (position per recommendation). |

**D-g measurement (cip, 2026-09-24):** `dim_product.product_line` has **14** distinct named values (NB 6,848 · NX 5,173 · PF 2,049 · NR 1,910 · PT 1,311 · LM 561 · XB 183 · PD 93 · AI 11 · NV 10 · NL 8 · CB 6 · AX 3 · AZ 1) plus **10 NULL rows** — not 16. Finding for Warren (does "16" count something else?).

**Standing exclusions.** EIF-repo defects (BACKLOG-159, 166, 167, 169–177) are out of CIP scope. BACKLOG-193 (AG Grid Enterprise) **dropped**. BACKLOG-200 **held** pending the N-0029 review.

---

## 1. Stages and their ledger nodes

Ordering rule: a stage sits after everything it needs to be *proven*, not merely written. The ledger encodes the order as `depends_on`.

### Stage 0 — Ledger hygiene ✅ (N-0030)
Backlog audited, this plan written and refreshed, queue chartered into the ledger (2026-09-24).

### Stage 1 — Independent reviews (queue item 3)
| Node | What | Status 2026-09-24 |
|---|---|---|
| N-0033 | Session auth gate + loopback web + quick tunnel (R3) | awaiting independent referent |
| N-0028 | Start work cards + Lineup cases | awaiting fresh GOV-008 |
| N-0031 | Stage 2a grid heights / mappings states / honesty fixes | awaiting a11y + referent |
| N-0032 | Five CPOR tabs on the desk | awaiting a11y + rendered + referent |
| N-0035 | Stage 2.2/2.3 density (retroactive charter) | awaiting referent + rendered |
| N-0029 | Grid clipboard + Case book | awaiting fresh GOV-008 (after Stage 2 density, now landed) |

### Stage 2 — Grid, desk and density parity
| # | Item | Node | Status |
|---|------|------|--------|
| 2.1 | Grid heights from one source | N-0031 | ✅ built `5e70f33`; review pending |
| 2.2 | Grid-scoped 13px type token | N-0035 | ✅ built `a4fe957`; review pending |
| 2.3 | Density 40/40 | N-0035 | ✅ built `459f4c9`; review pending |
| 2.4 | All-columns picker + code columns + name-only sweep | N-0034 | discovery done; operator acceptance |
| 2.4b | Shared grid search / saved views / export (D-b) | N-0041 / N-0042 / N-0043 | proposed, after N-0034 |
| 2.5 | Line identifier `both` as two columns | N-0053 | proposed, after N-0034 |
| 2.6 | `MarketSurface` mappings grid → `ModuleDataSection` | N-0031 | ✅ **built** `5e70f33` (was listed open) |
| 2.7 | Five orphaned CPOR tabs onto the desk | N-0032 | ✅ **tabs built** `ff118ec`; workspace retirement + orphan ruling → N-0044 (D-c) |
| 2.8 | Interaction honesty: `LineupScopeBar` Apply, `market.py` readiness | N-0031 | ✅ **built** `5e70f33` (dead `LineupScopeBar.tsx` deleted; `competitor_price_import: substrate` + test) |
| 2.9 | Design-lab as fixture skin | N-0054 | proposed |

### Stage 3 — Access and operations
| # | Item | Node | Status |
|---|------|------|--------|
| 3.1 | `CIP_AUTH_MODE=session` + router-level gate | N-0033 | ✅ **built** `26a6e1a` (+ tests `0d34d2c`); review pending |
| 3.2 | CPOR role checks on existing roles (BACKLOG-136/141) | N-0038 | proposed |
| 3.3 | Tenant scoping sweep | N-0055 | proposed |
| 3.4 | Login rate limit / lockout | N-0037 | proposed |
| 3.5 | Quick Tunnel + multi-user test plan | N-0033 | ✅ **done** (runbook `docs/PILOT_TUNNEL_RUNBOOK.md`); review pending |
| 3.5b | API binds loopback (BACKLOG-206) | N-0036 | proposed |
| 3.6 | Ops safety net: restore on a clone, alerting, resolver fails loudly | N-0052 | proposed |
| 3.7 | Import-complete merged-id assertion (BACKLOG-133/134) | N-0051 | proposed |

### Stage 4 — Data integrity and CPOR correctness
| # | Item | Node | Status |
|---|------|------|--------|
| 4.1 | `dim_product` inverted windows (2,795 rows 2026-09-21) | N-0047 | proposed; clone proof, cip apply listed for Warren |
| 4.2 | `cpor_case.status` vs `workflow_status` drift (4 rows) | N-0048 | proposed |
| 4.3 | MAC check reads CST (BACKLOG-135) | N-0049 | proposed |
| 4.4 | `cpor_case_line` week windows migration (approved for cip_test) | N-0050 | proposed; not applied to cip |
| 4.5 | CIP-minted customer codes | — | ✅ **already built** `66003db9` / `66ae66d9` (2026-07-10); evidence `EV-BUILT-45-MINT`. D-f: no mint pass now. |
| 4.6 | Open→shipped double-count policy (BACKLOG-062) | N-0071 | **blocked — not decided (D-e)** |
| 4.7 | ACZA non-operational sheets (BACKLOG-046) | N-0072 | **blocked — not decided (D-e)** |
| 4.8 | Customer merge alias seal | — | ✅ **already built** `467bc89e` (2026-07-11) + `fc14962c`; evidence `EV-BUILT-48-ALIAS` |

### Queue items outside the original stages
| Item | Node | Status |
|---|---|---|
| Listing links open the real product page (Market & Listings bug) | N-0039 | proposed (queue item 5) |
| D-g five-line assumption sweep | N-0040 | proposed (queue item 6) |
| D-d untracked-file archive | N-0045 | proposed (queue item 9) |
| BACKLOG-143 worktrees and hygiene | N-0046 | proposed (queue item 9) |

### Stage 5 — Analytics delivery — N-0056
Export, event-triggered refresh, calendar delivery, vintage on face. After 3.6 (N-0052).

### Stage 6 — Planning journey
| # | Item | Node |
|---|------|------|
| 6.1/6.2 | B2 PM run + lineup authoring workbench (BACKLOG-190) | N-0057 |
| 6.3/6.5 | Unified 1H fan-out + lineup data rules (BACKLOG-103/105/055/065) | N-0058 |
| 6.4 | Bulk-backfill completion UX (BACKLOG-060) | N-0059 |

### Stage 7 — Promotion intelligence v2
| # | Item | Node |
|---|------|------|
| 7.1–7.3 | Listing/competitor evidence, observed cover, comparable scope | N-0061 |
| 7.4 | Uplift from settled claims — **data-gated** (blocked, D-0021) | N-0063 |
| 7.5 | Supply Arrived state + PO coverage | N-0062 |
| D-h | Proposed-vs-executed intelligence (plan accuracy, deal-stock landing, PM bias) | N-0064 (chartered after the D-h moment) |

### Stage 8 — Steward and import engine (trigger-gated) — N-0069 umbrella
Items listed in the 2026-09-21 text (BACKLOG-077, 078, 080, 049, 051, 059, 067, 106, 123, 187, 188, 004, 037, 011, 018, 006, 008, 016, 019, 020) each split into its own node when its trigger fires.

### Stage 9 — Distributor merge ✅ **already built**
`361d138a` (2026-06-30, full distributor merge engine with PO consolidation and soft-redirect) + `fc14962c` resolvers follow `merged_into`. Evidence `EV-BUILT-S9-DISTMERGE`. No node.

### Stage 10 — Multi-tenant productisation (P6) — N-0070
After N-0069, N-0068 (catalogue grain) and N-0065 (BU entitlements).

### Outside-plan candidates (checked 2026-09-24)
| Candidate | Verdict | Node / evidence |
|---|---|---|
| External API layer (spec only until a consumer is named) | **Done as spec** (`docs/EXTERNAL_API_OUTBOUND.md`, `..._INBOUND.md`, `49e08364`) | `EV-BUILT-EXTAPI-SPEC`; first consumer = Warren |
| BU entitlements (user → product lines over D-g) | Missing; needs Warren's semantics | N-0065 blocked (D-0022) |
| Historical lineup backfill | Missing; cip holds 36 cases, 2025 Q1–2026 Q3 | N-0060 blocked (D-0020) |
| Inbound shipments by lineup quarter filter | **Already built** `4d7231f0` (2026-07-08) | `EV-BUILT-INBOUND-LQ` |
| Naming and polish pass for outside buyers | Missing | N-0066 |
| Light/dark theme completion | Both modes exist in `cipTheme`; completion unproven | N-0067 |
| Multi-catalogue column sets | Blocked on BACKLOG-198 grain | N-0068 blocked (D-0023) |

---

## 2. Still open for Warren
Shipment-evidence identifier preference · paid/closed migration on `cpor_case` · first outbound API consumer · 4.6 · 4.7 · BU entitlement semantics · historical lineup archive · catalogue grain · the "16 vs 14" product-line count. The session report carries these in its WARREN block.

## 3. Sequencing at a glance (ledger `depends_on`)

```
N-0030 ─► N-0036 ─► N-0037 ─► N-0038 ─► N-0039 ─► N-0040 ─► N-0044 ─► N-0045 ─► N-0046
  ─► N-0047 ─► N-0048 ─► N-0049 ─► N-0050 ─► N-0051 ─► N-0052 ─► N-0054 ─► N-0055 ─► N-0056
  ─► N-0057 ─► N-0058 ─► N-0059 ─► N-0061 ─► N-0062 ─► N-0066 ─► N-0067 ─► N-0069 ─► N-0070
N-0034 ─► N-0041 / N-0042 / N-0043 ; N-0034 + N-0052 ─► N-0053
blocked on Warren: N-0060 (after N-0058), N-0063, N-0065, N-0068, N-0071, N-0072
reviews (existing nodes): N-0033, N-0028, N-0031, N-0032, N-0035, N-0029
```
