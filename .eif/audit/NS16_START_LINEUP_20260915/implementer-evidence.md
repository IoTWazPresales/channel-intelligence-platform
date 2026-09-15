# N-0028 implementer evidence — Start work cards and Lineup cases

**Run:** `NS16_START_LINEUP_20260915` · **Actor:** `gov-001` · **2026-09-15**
**Do not complete.** Independent GOV-008 is a later session, different run and actor.
**Playwright MCP only.** No `browser_cdp`. No writes to `cip`.

Cites **D-0008** (accepted). **N-0025** Start work verbs retained. **N-0026** Create promotion plan retained (`/promotions?propose=1`). N-0025 GOV-008 leftovers not remediated.

Reconcile: `.eif/audit/NS16_START_LINEUP_20260915/RECONCILE.md`.

---

## Charter (re-read from ledger before close)

N-0028: Start work uses Import Center outlined cards with no Panel/Card wrapper. All seven verbs remain. Import a lineup → `/admin/imports?unified=1`. Steward-queue copy describes the failure-type queue. Lineup cases keeps PlanningChrome; inner HeadlineStrip + approval ScopeBar; keep grid + action bar. Remove fake trend and hardcoded 26Q3 chips.

---

## Playwright 1280×800 (VERIFIED)

| Step | Result |
|---|---|
| `/brief` Start work | Outlined cards. **Import a lineup** href `/admin/imports?unified=1`. **Create promotion plan** href `/promotions?propose=1` |
| Click Import a lineup | Landed `/admin/imports?unified=1` |
| `/lineup/cases` | Headline **Planned units 7,309** · **1647 plan lines**. Scope **All lines** / **Pending approval · 1646**. Grid 1–1647. No “Planned vs shipped by period”. No “All BUs” |

---

## Product land

| Path | Role |
|---|---|
| `apps/web/src/features/overview/startWork.ts` | Label Import a lineup; steward-queue copy |
| `apps/web/src/features/overview/StartWorkPanel.tsx` | Outlined cards; no Panel wrapper |
| `apps/web/src/features/lineup/LineupContainer.tsx` | HeadlineStrip + ScopeBar; PlanningChrome unchanged |
| `apps/web/src/features/lineup/LineupWorkspace.tsx` | Grid + action bar kept; dark N-0009 fill removed |

vitest: startWork, OverviewHub, lineup/cases page — **7 passed**.

---

## UNCOVERED (not invented)

| Finding | Backlog |
|---|---|
| Cover `?product=` not read on lineup cases | BACKLOG-189 |
| Planner empty-draft POST is not a creation workbench | BACKLOG-190 |

Unmounted N-0009 files (`LineupScopeBar`, `LineupReadStrip`, `LineupTrendInstrument`, `LineupRegimeStrip`, `LineupTaskCrumb`) remain in tree; not remounted.

---

## Untouched

D-0002, N-0006, N-0013, D-0010, BACKLOG-181, Movement/Execution, N-0025 remediation, N-0026 (not re-audited), N-0027 GOV-008. No GOV-008 on this node.
