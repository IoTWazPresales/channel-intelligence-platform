# CIP Autonomous Build Charter

**Version:** 1.1 · 2026-07-31 · Owner: Warren
**Status:** proposed — commit to `docs/AUTONOMOUS_BUILD_CHARTER.md` after the interview
section is answered.

This governs how Cursor builds the remainder of CIP with bounded autonomy. It sits
**under** `docs/ROADMAP.md` (what to build, in what order), is bound by
`docs/COMMERCIAL_DOMAIN_RULES.md` (**domain ground truth — never overridden**), and sits
**beside**
`docs/STEWARD_EXPERIENCE_CONTRACT.md` (what done means) and
`docs/STEWARD_ENGINE_DECISIONS.md` (why it's built this way). Where they conflict, the
contract and decisions log win.

---

## Why this is possible now and was not in June

Autonomy is only safe on top of guardrails that did not exist a month ago: an enumerated
contract, an append-only decisions log, a mechanical gate script, clone-proof discipline for
destructive paths, and a trunk with no diverged branches. Those are the preconditions. Do not
relax them to move faster — they are the reason speed is available at all.

---

## The four known failure modes and their mitigations

**1. Verification proves what exists, not what is missing.**
Browser testing would have passed the CPOR chrome-only drawer: everything it clicked worked.
*Mitigation:* every module carries enumerated contract rows **written before implementation**.
Verification runs against the rows, never against whatever got built.

**2. Reconciliation is not correctness.**
Cursor can prove file totals equal fact totals. It cannot know a customer should not be in
that list, or that a quarter's plan looks wrong.
*Mitigation:* mechanical reconciliation is Cursor's. Domain plausibility is Warren's, at
defined gates, with a numbered verification sequence.

**3. "Ping me when blocked" fails when the agent does not know it is blocked.**
The CPOR plan-apply gap was never hit and stopped on — it was never noticed.
*Mitigation:* the **Question Queue** is mandatory and must be populated even when nothing
feels blocking. An empty queue after a module is itself a finding to report.

**4. "As long as it needs" has no exit condition.**
Agents optimise toward the stated bar; unbounded, they polish. This is what turned modules
into multi-week efforts.
*Mitigation:* every module has explicit exit criteria and a time budget. Hitting the budget
triggers a report, not a push.

---

## Database policy

| Operation | Policy |
|---|---|
| Import / load writes to `cip` | **Permitted unattended.** Idempotent, reversible by deleting the job |
| Steward resolution applies | **Permitted unattended.** Reversible; provisional entities are valid link targets |
| Customer/distributor **merge** | **Clone-proof first.** Physically repoints ~29 FK columns + soft tombstone — deleting the job does not undo it |
| Supersession applies | **Clone-proof first.** Pointer rewrites are not job-reversible |
| Bulk destructive steward applies | **Clone-proof first**, printed numbers, all-or-nothing |
| Alembic migrations against `cip` | **Explicit approval only.** Never unattended |
| Schema changes | **STOP and report.** Never unattended |

**Before the first autonomous load:** take a `pg_dump` snapshot of `cip` using the explicit
binary path (`C:\Program Files\PostgreSQL\18\bin\`). Record the dump path in CURRENT.md.

**Permanent:** `ALLOW_TESTS_ON_DEV_DB` stays unset. Tests never write to `cip`. Smoke and
validation scripts run against `cip_test` / `cip_alembic_smoke` with **both**
`DATABASE_URL_SYNC` and `DATABASE_URL_SYNC_MIGRATE` overridden, resolved URLs printed.
Verify `current_database()` before any write; if it is not the expected target, STOP.

---

## Autonomy zones

**GREEN — build, verify, commit, continue. Report at module exit.**
- Analytics and read surfaces over existing facts (A1 surfaces, A2, A3)
- Import pipeline work on established patterns
- Steward surfaces mounting the generic engine
- Config extraction, header vocabulary, tenant parameterisation
- Backlog batch-fixes, test repair, mechanical refactors
- Anything the gate script can prove

**AMBER — build and verify, then HALT for Warren before committing to `cip` data or
proceeding.**
- Any domain data load sign-off (does this number match reality?)
- New commercial semantics: fill rate, bias, landing, budget math, forecast outputs
- First use of a new source file family
- Anything where the *definition* of a metric is being chosen

**RED — do not proceed. Queue and stop.**
- Merges, supersessions, destructive bulk applies without a clone-proof run
- Schema changes or migrations
- Any domain rule not already settled in the decisions log or domain rules
- Anything contradicting a locked D-entry (cite it, propose a supersede, wait)

---

## Module inventory and exit criteria

Each module exits when **all** of: contract rows satisfied or waived · browser verification
sequence passes · mechanical reconciliation passes · question queue populated · defects
logged · committed and pushed · CURRENT + CONTEXT updated.

| Module | Contract rows | Exit criterion | Zone | Budget |
|---|---|---|---|---|
| **P1 loads** (DSI, shipment, CPOR, lineups) | Census buckets per domain × period | Census reconciles: rows in = rows out, drops explained, domain invariant holds | AMBER at sign-off | 1 session per domain |
| **A1 Proposed-vs-Executed** | Plan accuracy, fill rate (shipped-only), deal-stock landing, PM bias | Numbers reconcile to `fact_inbound_shipment`; Warren confirms plausibility | AMBER | 2 sessions |
| **A2 CPOR intelligence** | Spend by customer/BU/promo type, cost per unit, settlement rate | Totals reconcile to loaded CPOR cases | GREEN | 2 sessions |
| **A3 Channel stock + velocity** | Derived SOH, weeks of cover, zero-velocity guard | Latest-per-(distributor, product) snapshot rule proven; no snapshot summing | GREEN | 2 sessions |
| **P2-1 Deployment** | *(deferred — no hosting target set)* | — | RED until hosting decided | — |
| **P2-2 Alembic replayability** | Chain replays on empty DB without `stamp head` | Fresh DB provisions from migrations alone | GREEN | 1 session |
| **P2-3 Auth + RBAC + user mgmt** | Login, sessions, 4 roles, admin-adds-users, tenant scoping, steward audit | Cross-tenant leakage impossible; roles enforced server-side | AMBER | 2 sessions |
| **P2-4 App shell + landing** | Navigation, IA, landing surface, freshness banner | A manager reaches any surface unaided | AMBER | 2 sessions |
| **P2-5 Monitoring + backup/DR** | Error tracking, job-failure alerts, automated backup, tested restore | A restore has actually been performed | GREEN | 1 session |
| **P3-1 Semantic layer** | Metric registry, dimension registry, validity rules, config-driven | Invalid metric×grain combos refused with explanation | AMBER | 3 sessions |
| **P3-2 Query engine** | Metric+dim→SQL, invariants applied, aggregates, cache | NFR render targets met | GREEN | 2 sessions |
| **P3-3 Report builder** | Build, slice, filter, visualise; author + consume modes | A governed report built end-to-end in UI | AMBER | 3 sessions |
| **P3-4 Dashboards + sharing** | Save, publish, role-aware share | — | GREEN | 2 sessions |
| **P3-5 Export + delivery** | Excel/PDF, event + scheduled trigger, freshness declared, missing-data alert | Report lands in an inbox stating its vintage | AMBER | 2 sessions |
| **P3-6 SQL viewer (admin)** | Read-only, role-gated, timeout, row cap, audit log | Not reachable by non-admin roles | GREEN | 1 session |
| **B1 Forecasting** | Finest-grain forecast, sum-rollup, confidence bands, analogue provenance | Rollup proven; new-launch analogue path defined | AMBER | 3 sessions |
| **B2 Lineup + budget builder** | Net requirement, bias correction, profit-with-reservation, two treatments, budget position (landed-basis), FX modes, 1H split, export, upload-reconcile | A lineup authored in CIP with reservation and exported in tenant format | AMBER | 5 sessions |
| **B4 Promotion plan builder** | Comparable-case lookup, volume from B1, budget check vs B2 reservations, export | A case authored end-to-end | AMBER | 3 sessions |
| **P4 CST forward-only** | Multi-format weekly ingest (8 customers), per-customer layout profiles, article alias steward, SOH recon, listing seeds | Facts arriving weekly from ≥2 customers, reconciling to derived stock | AMBER | 5 sessions |
| **P5 Listings** | Registry, fetch, observation accrual, intelligence v1 | ≥2 weeks observations + live CPOR | GREEN | 2 sessions |
| **P6 Multi-tenant** | Tenant config surface, onboarding, provisioning, billing hooks | Second tenant onboardable without code changes | GREEN | ongoing |
| **X-1 Unit E VERIFY** | CST steward contract rows | PASS or named gaps waived | GREEN | 1 session |
| **X-2 Distributor merge** | Merge engine extended to `dim_distributor` | Clone-proven E2E before commit | RED until clone-proof | 2 sessions |
| **X-3 Existing surface retrofit** | Contract audit: PO mgmt, PM gaps, channels/regions, product master, admin masters, commercial planner | Each surface graded, retrofitted or waived | GREEN | 3 sessions |
| **X-4 Lifecycle defect trio** | Heartbeat fires · liveness-aware reaper · retry guard | All three proven on a live slow job | GREEN | 1 session |
| **X-5 BACKLOG-076 amounts** | Corrupt unit amounts (~$36M) | Root-caused and corrected before any external demo | AMBER | 1 session |
| **X-6 Backlog burn-down** | BACKLOG-066 → 087 | Worked at phase boundaries by trigger | GREEN | ongoing |

**Budget semantics:** hitting the budget does not mean stop building. It means **report
status, list what remains, and continue only after Warren reads it.** No silent overruns.

---

## Browser verification — mandatory shape

Every module that changes a user-facing surface ships a **numbered verification sequence**
that Cursor runs itself in the browser, and that Warren can re-run.

Each step states:
1. **Action** — exact file to upload, exact URL/screen, exact control to click
2. **Expected result** — with real numbers, not "should work"
3. **Fail condition** — what specifically constitutes a failure

Minimum coverage per module:
- Happy path end-to-end (upload → map → validate → apply → surface renders)
- Every contract row that has a visible surface, exercised
- One deliberate error path (bad file, unresolved token, blocked case)
- Reconciliation: source totals vs displayed totals, printed side by side
- Idempotency: re-run and confirm no duplicate facts

**Cursor runs this before claiming a module complete.** A module claimed complete without a
run sequence and printed results is rejected.

---

## Question Queue protocol

File: `docs/OPEN_QUESTIONS.md`. Append-only within a module; resolved entries move to a
Resolved section with the answer and date.

Cursor **must** append a question when:
- A domain decision is required that is not settled in the decisions log or domain rules
- A source file contains something unexplained (unknown column, unexpected value, ambiguity)
- Two implementations are defensible and the choice is commercial, not technical
- Something looks wrong but is not blocking

Each entry: what is unclear · why it matters · what Cursor did in the meantime (assumption
made and where) · what would change if the answer differs · blocking or not.

**Non-blocking questions do not stop work.** Cursor proceeds on a stated assumption, records
it, and continues. Blocking questions halt that module only — other GREEN work continues.

**An empty queue after a module is a finding**, not a success. Report it.

---

## Consult and the no-patches rule

**Consult fires:**
- After each module completes, before the next begins — grade against contract rows
- When a fix has been attempted **twice** without resolving root cause
- At any RED-zone decision
- At phase entry (per roadmap)

**NEVER PATCH — hard constraint.**
A fix must name the root cause. Prohibited: suppressing a symptom, widening a type to silence
an error, catching an exception to skip a failing path, adding a special case for the failing
input, or adjusting a test to match broken behaviour.

If root cause is not identified after **two** attempts: **STOP**, write what was tried and
what was ruled out, and escalate to consult. A third blind attempt is prohibited.

---

## Reporting cadence

**Per module:** one report — what shipped, contract rows PASS/PARTIAL/WAIVED, verification
sequence run + results, reconciliation numbers, defects logged, questions queued, commit hash,
what is next.

**Daily digest** when running unattended: modules touched, current zone, anything AMBER
waiting on Warren, anything RED blocked.

**Warren's involvement:** AMBER gates and RED blocks only. Everything else is read-later.

---

## Scalability constraint (applies to every module)

Tenant vocabulary, period conventions, currency, legal-form rules, column maps, BU grain and
export templates are **configuration**. Any tenant-specific string entering code is a defect,
not a shortcut. Uploaded ASUS files are **examples of a shape**, never the definition of it.
Every module must be answerable to: *what changes for tenant #2, and is it config?*

---

## Regression strategy

Per-module browser verification proves that module. It does **not** prove module 9 didn't
break module 3. As modules accumulate this becomes the dominant risk.

- **Smoke suite** — a growing set of browser sequences, one per completed module, reduced to
  its happy path only. Runs before every module's commit, not just the module being built.
- **Adding to it is part of module exit.** A module is not complete until its happy path is in
  the smoke suite.
- **Runtime budget** — if the suite exceeds 15 minutes, parallelise or trim to the highest-value
  paths. Do not let it become something that gets skipped.
- **Metric regression** — once the semantic layer exists (P3-1), every governed metric gets a
  pinned expected value against a fixed data snapshot. A metric changing value without an
  intentional definition change is a hard failure.
- **A red smoke suite blocks the commit.** No exceptions, no `--admin` equivalent.

---

## The demo artifact

The commercial objective is managers who cannot stop using it. That requires a thing to show,
maintained as a first-class deliverable rather than assembled in a panic.

**Maintain `docs/DEMO_SCRIPT.md`** from A1 onward: the sequence to walk a manager through,
the numbers each screen should show, and what to say about each. Updated at every module exit
that touches a demo surface.

**Minimum demo spine:** login → landing surface with freshness → plan accuracy and PM bias
across years → promo effectiveness → author next quarter's lineup → scheduled report landing
in an inbox.

**Rule:** if a defect would make a demo screen wrong or embarrassing, it is AMBER, not
log-and-continue. BACKLOG-076 (corrupt unit amounts) is the current example.

---

## Interview triggers

Unanswered questions block their modules. They must be **surfaced, not waited on**.

- Cursor raises the relevant interview question in `docs/OPEN_QUESTIONS.md` **one phase before**
  the blocked module, not at the moment of blocking.
- If a blocked module's turn arrives unanswered: skip it, continue with the next non-blocked
  module, and report the skip prominently. Never idle, never guess.
- Questions 1 and 2 (budget) require input from PMs, not just Warren — expect calendar time.
  Raise them at A2 entry.

---

## Interview — Warren answers before B3 and P4

These are the questions Cursor cannot resolve. Unanswered, they hard-block their modules.

1. **Budget envelope** — **ANSWERED.** Derived, not allocated: the reservation is embedded in
   the lineup's profit line. Landed-quarter basis. USD from ZAR. Unspent returns; cancelled
   frees immediately. Pot per sales model/customer, movable. See
   `docs/COMMERCIAL_DOMAIN_RULES.md` §1. **Still open:** money ceiling vs support-% ceiling.
2. **PM bottom** — **ANSWERED.** Fixed per quarter, per SKU.
3. **Forecast grain and rollup** — **ANSWERED.** Sum the fine grain; quarter re-derivation is a
   comparison view only. Seasonality trusted as confidence allows. New products by analogue
   (spec, segment, price, GPU, predecessor) with analogue recorded as provenance.
4. **A1 quarter window** — confirmed as all quarters with lineup coverage, core 26Q1 →
   current. *(Answered)*
5. **CST pilot customer** — which account, and who sends the weekly file? *(Blocks P3)*
6. **Source file access** — **ANSWERED.** Files are on local disk at the staging root given at
   kickoff. Cursor reads them directly; never request uploads. Staging root lives **outside the
   repo**; `.gitignore` must exclude source data (`*.xlsx`, `*.xls`, `*.csv`, dumps). Folder
   layout is tenant config, not a constant.
7. **Hosting** — **DEFERRED BY CHOICE.** Completing locally. P2-1 deployment is out of scope
   until Warren sets a target.
8. **Rollout users** — **ANSWERED.** Admin adds users and assigns roles; no self-registration.
9. **CST customers** — **ANSWERED.** Eight send directly: Takealot, Evetech, Computer Mania,
   Incredible Connection, Amazon, HiFi Corp, Makro, Game. Multi-format from day one.

**Answered already:** A1 quarter window — all quarters with lineup coverage, credible core
26Q1 → current.
