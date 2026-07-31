# CIP Autonomous Build Charter

**Version:** 1.2 · 2026-08-01 · Owner: Warren  
**Status:** authoritative execution doc (absorbs former `docs/WORKFLOW_DUAL_AGENT.md`).

This governs how Cursor builds the remainder of CIP with bounded autonomy — zones, gates,
verification, and the Cursor ↔ CLI dual-agent loop. It sits **under** `docs/ROADMAP.md`
(what to build, in what order), is bound by `docs/COMMERCIAL_DOMAIN_RULES.md` (**domain
ground truth — never overridden**), and sits **beside**
`docs/STEWARD_EXPERIENCE_CONTRACT.md` (what done means),
`docs/STEWARD_ENGINE_DECISIONS.md` (why it's built this way), and
`docs/COMMERCIAL_SEMANTICS.md` (metrics, grains, owning surfaces — **authoritative**).
A metric mattering to a phase does not make that phase's screen its home. Where they
conflict, the contract, decisions log, and commercial semantics win.


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

**AMBER — halt at the point the risk is real, not after the work is done.**

- **Design-stage halt (before any code):** new commercial semantics — a new metric,
  a new lifecycle state, or any tile/filter added to a user-facing surface. Report:
  the concept, its owning surface per `COMMERCIAL_SEMANTICS.md`, the pre-build
  existence-audit output, and — if proposing a new home — why the existing owner
  cannot be extended. Wait for Warren.
- **Post-build halt (after verification):** domain data load sign-off, and first use
  of a new source file family.

Building the wrong thing correctly is the failure this prevents. A halt that occurs
after the build is finished cannot catch a wrong-surface error.

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
| **A1 Proposed-vs-Executed** | Plan accuracy, fill rate (shipped-only), over-plan intake, short/unplanned/no-PO; PM bias/slip per `COMMERCIAL_SEMANTICS` | Numbers reconcile to shipped facts; Warren confirms plausibility | AMBER | 2 sessions |
| **A2 CPOR intelligence** | Spend by customer/BU/promo type; delivery rate; claim rate; support cost per unit sold; norms; comparable-case | Totals reconcile to loaded CPOR cases | GREEN once formulas locked in semantics | 2 sessions |
| **A3 Channel stock + velocity** | Derived SOH, weeks of cover (dist×product), zero-velocity guard, replenishment flag v1 | Latest-per-(distributor, product) proven; no snapshot summing | GREEN | 2 sessions |
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

Verification opens the **owning** surface for the concept, plus any surface the
change claims to affect. If the concept renders on two surfaces, that is a
duplication defect — report it, do not treat it as coverage.

**Pre-build existence audit — mandatory before any UI work.**
`grep -rn "<concept>" apps/web/src` and `apps/api/app/services`. A hit means the
concept exists — STOP, report where, extend that surface. No hit — consult
`docs/COMMERCIAL_SEMANTICS.md`; owner listed, build there; no owner, halt and ask.
Print the audit output in the unit report. A UI change claimed without it is
rejected. Metrics not defined in `COMMERCIAL_SEMANTICS.md` are not built.

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
6. **Source file access** — **ANSWERED: upload on request.** There is no staging folder and no
   disk path. Cursor must never look for source files on disk or assume a file location. When
   a step needs real data, **STOP and request the upload**, stating: which domain, which
   periods, how many files, and what will be done with them. Warren uploads to the chat.
   `.gitignore` must exclude source data (`*.xlsx`, `*.xls`, `*.csv`, dumps) so uploaded data
   is never committed. Uploaded files are working copies, not an archive — a later re-run may
   require re-upload.

   **Consequence:** every file-dependent step is **AMBER by definition** — it cannot chain
   unattended. P1 runs at Warren's pace. Work downstream of loaded facts (analytics, planning,
   app shell) still chains freely in GREEN.
7. **Hosting** — **DEFERRED BY CHOICE.** Completing locally. P2-1 deployment is out of scope
   until Warren sets a target.
8. **Rollout users** — **ANSWERED.** Admin adds users and assigns roles; no self-registration.
9. **CST customers** — **ANSWERED.** Eight send directly: Takealot, Evetech, Computer Mania,
   Incredible Connection, Amazon, HiFi Corp, Makro, Game. Multi-format from day one.

**Answered already:** A1 quarter window — all quarters with lineup coverage, credible core
26Q1 → current.

---

## Dual-agent loop (Cursor ↔ CLI Opus | Fable)

**Absorbed from** former `docs/WORKFLOW_DUAL_AGENT.md` (2026-08-01 merge).  
**Operational skill:** `~/.cursor/skills/dual-agent-fable` / project `cip-dual-agent-fable`.  
**Consultant default: Opus.** Use Fable when Warren names Fable, or to finish an in-flight
Fable VERIFY chain. Cursor states `Consultant: Opus|Fable` in every sync pin.

**Do not put here:** current branch, HEAD, job IDs, Alembic tip — those live in
`docs/memory/CURRENT.md`.

### Quality bar (non-negotiable)

Optimize for UX, design, architecture, scalability, flexibility, best business practice —
never for speed or “smallest diff.”

| Rule | Meaning |
|------|---------|
| **Canonical clone or STOP** | Clone living reference behaviour/operator experience, not merely import a shared primitive. |
| **No half-PASS** | Thin mounts / stub wizards / sync-only where async+progress is the bar → incomplete. |
| **Code is evidence; docs are claims** | CURRENT/BACKLOG/ROADMAP “done” must be proven in the running tree. |
| **Cursor must not self-PASS** | After clone/parity units, seed CLI VERIFY; only `VERDICT: PASS` closes. |
| **VERIFY walks the contract** | Steward/import: S1–S14 against shipped tree; REQUIRED absent without waiver → STOP. |

**Product bar:** best practice is default; propose the better path; patches are last resort.
CONSULT states operator experience first; never recommend thin when a correct unified
architecture exists.

### Roles

| Role | Owns | Must not |
|------|------|----------|
| **Warren** | Priorities, merge/promote, cip writes, alembic approval | — |
| **Cursor** | Implement → tests → CURRENT/CONTEXT → commit/push → seed consultant | Next unit before PASS; alembic without Warren; `git add -A`; half-parity PASS |
| **CLI consultant** | CONSULT / VERIFY | Edit files during consult/verify; migrations; PASS thin mounts |

Browser Claude / claude.ai project chat is **retired** for this loop.

### When to use

Multi-unit roadmap / BACKLOG Large / mushy product decisions / independent verify.  
**Not required for:** one-line fixes, typo commits, single-file obvious bugs.

### Loop (one unit)

```
0. Sync pin (Cursor) — include Consultant: Opus|Fable
1. CONSULT (CLI) — interview if mushy; short scope lock if BACKLOG complete
2. Unit prompt → Warren skims → Cursor IMPLEMENT
3. Cursor: tests → CURRENT/CONTEXT → explicit git add → commit → push → report
4. VERIFY → VERDICT: PASS | STOP
5. On PASS: next unit; on STOP: fix and re-verify
```

**Hard gate:** no next-unit implementation until `VERDICT: PASS` (or Warren written waiver
in CURRENT).

### CIP standing rules (dual-agent)

- Spec / BACKLOG entry read-only unless Warren says edit
- Database writes follow **Autonomy zones** above (single rule — no blanket ban):
  GREEN/AMBER permitted unattended for import loads and steward applies (job-reversible);
  RED for merges / supersessions / destructive bulk without clone-proof; migrations and
  schema changes need Warren’s explicit approval
- Explicit `git add <paths>` — never `-A` / `.`
- FLAG ≠ BLOCK where domain requires
- Never auto-create dims from import evidence
- Import/steward: `.cursor/rules/import-parity.mdc` at DSI/shipment experience bar
- Behaviour-changing units ship a `## Verification sequence` (shape in Browser verification
  section above)

### Scope lock / contract scoping

Greenfield → interview (max 5 questions/round). Complete BACKLOG → short scope lock.
Steward/import: CONSULT enumerates S-rows of `STEWARD_EXPERIENCE_CONTRACT.md`; exclude only
with Warren waiver line. Reduced “lean/chrome-only” scope without waiver → defective prompt.

### Artifacts

`.tmp/<topic>_consult_*.md`, `_cursor_prompt.md`, `_cursor_report.md`, `_verify_*.md` —
never committed. Templates: `.cursor/templates/consult_seed_template.md`,
`verify_seed_template.md`.

### Invoke (repo root, PowerShell)

```powershell
Get-Content .tmp\<name>_consult_opus_seed.md -Raw |
  claude -p --model opus --output-format text --dangerously-skip-permissions |
  Out-File .tmp\<name>_consult_opus_response.md -Encoding utf8
```

(Fable: `--model fable` and matching filenames.)

### Handover starter

```
Run cip-session-handover
Run cip-dual-agent-fable
Branch: <name> @ <short SHA>
Next: <unit from CURRENT>
Skip: <do not re-audit>
Consultant: Opus
Mode: CONSULT
```
