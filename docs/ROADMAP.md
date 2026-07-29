# CIP Roadmap — to end state

**Owner:** Warren · **Version:** 1.0 · 2026-07-28
**Status:** proposed — commit to `docs/ROADMAP.md` after review

This is the ordered path. `docs/BACKLOG.md` holds deferred detail; `docs/memory/CURRENT.md`
holds today. If this file and CURRENT disagree about *what's next*, CURRENT wins for the
current session and this file gets corrected.

---

## End state

A multi-tenant channel intelligence and commercial planning platform where the PM's
**lineup, promotion case, forecast and budget live in CIP**, informed by an intelligence
layer nobody else has (plan-vs-executed, PM bias, promo effectiveness). Dependency comes
from the *planning tools*; the intelligence layer is what makes them better than Excel.

---

## Standing constraints (apply to every phase)

1. **Tenant config, never constants.** Every phase asks: BU vocabulary, period conventions,
   currency, legal-form rules, column maps, export templates — all config. Single-tenant
   hardcoding is the recurring trap.
2. **Every artifact is bidirectional.** Build in CIP → export in tenant format. Upload tenant
   file → reconcile against CIP. Upload is never removed; it is the on-ramp for tenant #2.
3. **Phase exit = something visible.** A screen or a number you would put in front of a
   manager. If a phase can't produce one, it's infrastructure and belongs *inside* another
   phase.
4. **Defect log, not defect fix.** During load/soak, defects are recorded and fixed in one
   batch at the phase boundary — unless they block the load. This is the discipline that
   stops single modules running for weeks.
5. **Consult fires per phase, not per unit.** Once at phase entry to lock scope and reject
   thin paths; again only at a named domain fork. Units inside a phase run on the cheap
   script gate (tsc error-list diff, matched test file sets, prohibited-pattern grep,
   base-integrity check).
6. **No new import surface** until the one before it has loaded real data.

---

## Phase overview

| Phase | Name | Blocks | Exit artifact |
|-------|------|--------|----------------|
| **P0** | Stabilise the base | everything | `main` current, CI is a gate |
| **P1** | Load the corpus | A- and B-lane | CPOR + DSI + shipment + lineups populated on cip |
| **A1** | Proposed vs Executed | B2 | Plan-accuracy surface |
| **A2** | CPOR intelligence | B3, B4 | Promo effectiveness surface |
| **A3** | Channel stock + velocity | B1 | Derived SOH / weeks-of-cover |
| **B1** | Forecasting | B2, B4 | Demand forecast by product × customer × period |
| **B2** | Lineup builder | — | Next-quarter lineup authored in CIP |
| **B3** | Budget layer | B4 | Envelope + committed vs actual |
| **B4** | Promotion plan builder | — | New CPOR case authored from history + forecast |
| **P3** | CST (forward-only) | P4 | Live weekly sell-through facts |
| **P4** | Listings + channel execution | — | Price/availability observation history |
| **P5** | Productise | — | Second tenant onboardable |

A-lane and B-lane run **in parallel** after P1, converging at B2/B4.

---

## P0 — Stabilise the base

**Why first:** a roadmap built on a base that silently diverges is worthless. A branch reset
already cost a week of DSI work; CI has not been a gate since PR #7 merged with `--admin`.

**Done (2026-07-28)**
- ✅ `main` @ `c323484` — arc A–F + DSI multifile + shipping KPIs + mapping clarity
- ✅ Branch audit complete; three real misses named (below)

**Remaining**
- Fix the pnpm CI version clash; CI becomes a **required** gate
- Build `scripts/verify-gate` — tsc error-list diff, matched test file sets,
  prohibited-pattern grep, **base-integrity check** (merge-base vs expected, reflog reset
  scan, branches-ahead-of-main list)
- **Resolve the three parked misses** — decide each explicitly, do not leave drifting:

| # | Item | Call to make |
|---|------|--------------|
| 1 | **Header vocabulary → template config.** Retire hardcoded header strings (`dealer name group`, `customer name`) from `dsi_mapping_workflow.py`; add per-template header-alias map + never-auto-map denylist; fix precedence to **confirmed memory > template alias > heuristic** (currently `apply_exact_raw_customer_header_overrides` beats memory — backwards). Extract ASUS header spellings + denylist from stash `park-dsi-asus-dealer-name-automap`, then drop the stash | P1 blocker; retires debt rather than adding to it |
| 2 | `feat/ops-master-grid-shell-parity` (~36 commits, base `618448c`) — **KILL.** Name is misleading: `MasterDataGridShell` already shipped for masters (customers/products/distributors) in BACKLOG-061 Theme B, PR #7, on `main` since 2026-07-10. This branch only extends it to *ops lists* (CPOR cases, PM gaps, shipment evidence, PVE) — mechanical re-application on a layout Unit F has since moved. Extract two real items to BACKLOG, delete branch | Extract → delete |
| 3 | `fix/pm-bulk-upsert-coercion-and-sql-types` `558d088` — `channel_id` CASE + typed cast | Cherry-pick; real psycopg3 typeless-NULL hazard |

**Do not take:** `fix/web-grid-community-stabilization` — forces community AG Grid, conflicts
with the Enterprise pattern.

**Exit:** CI blocks a red build; gate script runs clean; zero unexplained branches ahead of
`main`.

**Consult:** none. This is hygiene.

---

## P1 — Load the corpus

**Why:** the ingest machinery is largely built and largely unproven on real volume. Every
significant defect of the last month surfaced from touching real data, not from review.

**Scope**
- CPOR historical: resolve the blocked cases, plan-apply, verify case codes preserved
- DSI weekly: current files through the multifile path (headers, one job per layout group)
- Shipment: current inbound through steward → facts
- Lineups: confirm corpus completeness for the quarters A1 will report on

**Discipline:** timeboxed. Defects go to a log. Only load-blocking defects get fixed inline.
Batch-fix at the boundary.

**Exit:** each domain has real, verified rows on cip; a written defect log; a one-page data
census (what exists, what's missing, per domain per period).

**Consult:** none — unless a load reveals a domain rule that needs settling.

**Risk:** entity resolution volume. Expect steward work; that's the system doing its job,
not a defect.

---

## Lane A — Intelligence (backward-looking)

### A1 — Proposed vs Executed

**Entry:** P1 lineups + shipment loaded.

**Scope:** plan accuracy by quarter / BU / customer; fill rate (shipped-only); deal-stock
landing rate; over-ship as met-plan not penalty; PM planning bias across years; slip and
timing analysis.

**Exit artifact:** a plan-accuracy surface you'd show a manager. This is the credibility
piece and the differentiator no aggregator replicates.

**Tenant check:** BU grain from `dim_product.product_line`; quarter derived from period
dates, never labels.

**Open:** does PvE gate on `pod_date` (BACKLOG-068) — decide at entry.

### A2 — CPOR intelligence

**Entry:** P1 CPOR historical loaded.

**Scope:** support spend by customer / BU / promo type; cost per incremental unit; settlement
rate (result vs estimate); over/under-delivery patterns; which promo types actually moved
volume; per-customer historical support norms.

**Exit artifact:** promo effectiveness surface + "comparable past cases" lookup (the input
B4 consumes).

**Tenant check:** promo-type vocabulary and channel (disti/reseller) are config.

### A3 — Channel stock + velocity

**Entry:** P1 DSI + shipment loaded.

**Scope:** derived channel stock (latest reported SOH − sell-out since snapshot + POD-landed
since snapshot; pipeline and open-order never count); velocity; weeks of cover with a
zero-velocity guard; replenishment signal.

**Exit artifact:** channel stock / cover surface.

**Known defect to close here:** channel stock tile summing all SOH snapshots instead of
latest-per-(distributor, product).

---

## Lane B — Planning (forward-looking)

### B1 — Forecasting

**Entry:** A3 (velocity + cover).

**Scope:** demand forecast computed at the **finest available grain** (product × customer ×
period) and rolled up to **product × distributor × quarter**. Inputs: sell-out velocity,
seasonality where history supports it, pipeline, channel cover. Confidence banding.
Manual override with provenance.

**Exit artifact:** forecast surface at both grains, with the rollup rule documented.

**Open at entry:** rollup rules (sum vs re-derive); minimum history for seasonality;
what happens for products with no sell-out history (new launches).

**Tenant check:** period conventions (quarter definitions) are config.

### B2 — Lineup builder

**Entry:** A1 (bias) + B1 (forecast).

**Scope:** author next-quarter lineup inside CIP, seeded by forecast and **bias-corrected by
PvE** (this is the thing Excel cannot do). 1H files always split Q1+Q2 with the
`uniform_half` convention. Steward-overridable. Export to tenant lineup template; upload
existing lineup for reconciliation.

**Exit artifact:** a lineup authored in CIP and exported in ASUS format.

**This is the dependency moment** — the first tool a PM opens weekly.

### B3 — Budget layer

**Entry:** A2 (actual spend history) + **PM budget questions answered** (see Open Decisions).

**Scope (shape depends on the answers):**
- *If a real envelope exists:* pot per grain, reservations against approved cases, committed
  vs actual, release on cancel/under-delivery, roll-over rules.
- *If no envelope:* spend analytics + derived guardrails from historical norms, no ledger.

**Exit artifact:** budget position surface — envelope, committed, actual, remaining.

**Tenant check:** currency and FX handling; VAT and margin remain derived, never stored as
canonical truth.

### B4 — Promotion plan builder

**Entry:** A2 + B1 + B3.

**Scope:** author a new CPOR case in CIP: comparable historical cases surfaced from A2,
volume expectation from B1, budget check from B3, waterfall math from CPOR v1, export in
tenant CPOR format. Upload path preserved for cases authored elsewhere.

**Exit artifact:** a new promotion case built end-to-end in CIP.

---

## P3 — CST (forward-only)

**Entry:** B-lane core shipped; a customer willing to send weekly files.

**Deliberate de-risk:** **do not backfill history first.** Start from next week's files with
one or two accounts. Recon, article-alias resolution and listing seeds all work on forward
data alone. History only buys velocity/seasonality depth and becomes an optional later job.

**Scope:** live weekly ingest, article-alias steward, SOH reconciliation (reported SOH is a
check, never truth), listing seed emission.

**Exit artifact:** sell-through facts arriving weekly, reconciling against derived channel
stock.

**Then optional:** CST historical backfill as a separate, scoped job.

---

## P4 — Listings + channel execution

**Entry:** P3 live; CPOR cases live.

**Scope:** listing registry population, live fetch + schedule enabled, observation history
accrual, then listing intelligence v1 (promo activated vs not, price compliance).

**Hard dependency:** intelligence needs live CPOR **and** ≥2 weeks of observations. Cannot
be pulled earlier.

---

## P5 — Productise

**Scope:** per-tenant configuration surface (BU vocabulary, period conventions, legal-form
normalizer, column-map profiles, export templates), onboarding path for tenant #2, RBAC,
export-per-tenant-requirement, pricing/packaging mechanics.

**Exit artifact:** a second tenant can be onboarded without code changes.

---

## Dependency graph

```
P0 ──> P1 ──┬──> A1 ─────────────┐
            ├──> A2 ──────┬──────┼──> B3 ──┐
            └──> A3 ──> B1 ┴──> B2 <───────┘
                            └──────────> B4
P1 ──────────────────────> P3 ──> P4
(any time after P1) ─────> P5 (config extraction, incremental)
```

**True parallelism:** A1 ∥ A2 ∥ A3 after P1. B1 starts once A3 lands. B3 can start on A2
alone. P5 config extraction can happen incrementally inside every phase rather than as a
big-bang at the end — preferred.

---

## Open decisions register

| # | Decision | Blocks | Owner |
|---|----------|--------|-------|
| 1 | Budget envelope: real pot or derived guardrail? (grain, currency, roll-over, release-on-cancel, 50/50, margin ceiling vs money) | **B3, B4** | PMs → Warren |
| 2 | PM bottom: fixed per-SKU floor for a period, or per-deal negotiated? | B3, B4 | PMs |
| 3 | Forecast rollup rules; minimum history for seasonality; new-launch handling | B1 | Warren |
| 4 | PvE `pod_date` gating (BACKLOG-068) | A1 | Warren |
| 5 | Branch/location modelling (currently deferred by design) — blocks tagged-customer sell-through reporting | P3+ | Warren |
| 6 | CST customer for forward-only pilot | P3 | Warren |

---

## Explicitly out of scope / later

- Field-merchandising mobile app — separate product, separate timeline
- CST historical backfill — optional job after P3 proves the pipe
- Branch/location model — deferred; do not alias branches to parent customers
- Second-tenant onboarding — P5, but extract config continuously

---

## Operating guide

### How to read this file

- **Phase** = a destination with an exit artifact. Weeks, not days.
- **Unit** = one Cursor session's work. Hours to a day. Units live in the phase, not here.
- The **overview table** tells you what is legal to start. The **dependency graph** tells you
  why. If a phase's blocker hasn't produced its exit artifact, that phase is not startable —
  no exceptions, because the downstream work will be built on guesses.

### What you can start right now

Anything whose blocker column is satisfied. Today that's **P0 only**. P1 opens when P0 exits;
A1/A2/A3 all open together when P1 exits.

### What you cannot do

- Start a phase whose blocker hasn't exited (building B1 forecasting before A3 velocity means
  inventing the inputs).
- Fix defects inline during a load phase — they go to the log, batched at the boundary. This
  is the single discipline that stops modules running for weeks.
- Add a new import surface while the previous one has no real data through it.
- Leave a branch unmerged for more than a day (see parallel rules).

### Parallel work — the test

Two units may run in parallel **only if all four hold**:

1. **Disjoint file surfaces** — no file appears in both diffs. Overlap means serialize.
2. **At most one migration in flight** — only one unit may hold an Alembic revision at a time.
3. **Neither is a destructive or engine-level change** — merges, supersession, bulk apply, and
   steward-engine edits run alone.
4. **Both merge to `main` the same day** — short-lived branches only.

If any fails: serialize. The bottleneck is your attention and merge conflicts, not Cursor's
throughput.

**Naturally parallel pairs** (disjoint by construction):
- A1 (PvE analytics) ∥ A2 (CPOR analytics) — different services, different pages
- A3 (channel stock) ∥ A1 — different fact sources
- P5 config extraction ∥ almost anything — it's config plumbing
- Any hygiene/ops unit ∥ any feature unit

**Never parallel:**
- Two units touching the steward engine
- Two units with migrations
- Anything ∥ a load phase (P1 needs your eyes, not your attention split)

### How to run parallel work

1. Each unit gets its **own branch off current `main`**, named for the unit.
2. Each gets its **own Cursor session**, opening with `Run cip-session-handover`.
3. Each ends with commit + push + **merge to `main` the same day**.
4. Re-base the other branch off the new `main` before continuing.

Two in flight is the practical ceiling. Three means one is drifting.

**Why the same-day rule:** `feat/ops-master-grid-shell-parity` reached ~36 commits while `main`
moved ~45 past its base, and became cheaper to delete than reconcile. A separate incident lost
a week of DSI work to a silent branch reset. Long-lived branches are this project's most
expensive recurring failure.

### When consult fires

| Situation | Consult? |
|-----------|----------|
| Phase entry — lock scope, name exit artifact, reject thin paths | **Yes** |
| Domain fork — variance vs capability gap, budget semantics, forecast grain | **Yes** (or Warren directly) |
| Destructive path — merge, supersession, bulk apply | **Yes** |
| New contract row, or a surface with no contract | **Yes** |
| A unit inside an open phase, scope already locked | No — gate script |
| Hygiene, config extraction, mechanical re-application | No |
| Bug with a known cause | No |
| Anything the gate script can prove mechanically | No |

**Gate script covers:** tsc error-list diff, matched test file sets, prohibited-pattern grep,
base-integrity check. Cheap, runs every unit, no usage cap. Reserve paid judgment for
decisions, not verification.

### Weekly rhythm

- **Start of week:** read this file. What phase are you in? What's its exit artifact?
- **Daily:** one or two units. Merge to `main` before stopping.
- **Phase exit:** batch-fix the defect log, produce the artifact, update CURRENT + CONTEXT
  changelog, then re-read this file before starting the next phase.
- **When a phase runs long:** the question is never "push harder." It's "did the defect log
  turn back into inline fixing?"
