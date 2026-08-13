# CIP Roadmap — to end state

**Owner:** Warren · **Version:** 3.1 · 2026-08-02
**Status:** proposed — commit to `docs/ROADMAP.md` after review
**v3.1 changes:** Open decisions #1/#2 marked resolved (align with OPEN_QUESTIONS Q-001/Q-002);
register lists only still-open items.
**v3.0 changes:** B2+B3 merged into one lineup+budget builder (reservation is embedded in the
profit line) · landing-quarter moved from deferred to A1/A2 core · net-requirement planning
added to B2 · P2 deployment deferred, multi-user readiness retained · P4 CST is multi-format
across 8 customers.

Companion docs: `docs/COMMERCIAL_DOMAIN_RULES.md` (**domain ground truth — authoritative**),
`docs/AUTONOMOUS_BUILD_CHARTER.md` (how work is executed),
`docs/STEWARD_EXPERIENCE_CONTRACT.md` (what done means for steward surfaces),
`docs/STEWARD_ENGINE_DECISIONS.md` (why it's built this way).
`docs/memory/CURRENT.md` holds today; if it disagrees with this file about what's next,
CURRENT wins for the session and this file gets corrected.

---

## End state

A multi-tenant channel intelligence and commercial planning platform, delivered as a service,
where a PM's **lineup, promotion case, forecast, budget and reporting live in CIP** —
informed by an intelligence layer nobody else has (plan-vs-executed, PM bias, promo
effectiveness) and served through governed analytics that cannot produce two versions of the
same number.

**Dependency comes from the planning tools and the weekly report landing in an inbox.**
The intelligence layer is what makes them better than Excel; the analytics platform is what
makes them unavoidable.

---

## Standing constraints (every phase)

1. **Tenant config, never constants.** BU vocabulary, period conventions, currency,
   legal-form rules, column maps, folder layouts, metric definitions, export templates — all
   configuration. Uploaded ASUS files are examples of a *shape*, never the definition of one.
2. **Every artifact is bidirectional.** Build in CIP → export in tenant format. Upload tenant
   file → reconcile against CIP. Upload is never removed; it is the on-ramp for tenant #2.
3. **Phase exit = something visible.** A screen or a number you'd put in front of a manager.
   If a phase can't produce one, it's infrastructure belonging inside another phase.
4. **Defect log, not defect fix.** During load and soak, defects are recorded and fixed in one
   batch at the phase boundary. This is the discipline that stops modules running for weeks.
5. **Consult fires per phase, not per unit.** Plus at named domain forks and RED-zone
   decisions. Units inside a phase run on the gate script.
6. **No new import surface** until the previous one has loaded real data.
7. **Never gap-fill actuals with predictions.** Forecast is a separate labelled layer.
8. **Freshness is declared, never assumed.** Every surface states its data vintage.
9. **One concept, one owning surface.** Every metric, filter and lifecycle state has
   exactly one owning screen (`docs/COMMERCIAL_SEMANTICS.md`). Other surfaces read or
   link; they never re-implement. A metric mattering to a phase does not make that
   phase's screen its home. Metrics not defined in `COMMERCIAL_SEMANTICS.md` are not built.

---

## Non-functional targets

These are the "optimisation not speed" bar. Measured at P2 exit and held thereafter.

| Target | Bar |
|---|---|
| Page load (data surface, warm) | < 2s p95 |
| Report render (governed metric, 1 year, 1 dimension) | < 5s p95 |
| Import validate (10k rows) | < 60s, with live progress |
| Import apply (10k rows) | < 120s, idempotent, resumable |
| Concurrent users | 25 without degradation |
| Fact table scale | 10M rows per tenant without query redesign |
| Job failure visibility | Surfaced in UI within 60s of failure |
| Data retention | Full history; no destructive purge path |

---

## Phase overview

| Phase | Name | Blocks | Exit artifact |
|-------|------|--------|----------------|
| **P0** | Stabilise the base | everything | `main` current, CI is a gate |
| **P1** | Load the corpus | A- and B-lane | Data census signed off per domain |
| **A1** | Proposed vs Executed | B2 | Plan-accuracy surface |
| **A2** | CPOR intelligence | B3, B4 | Promo effectiveness surface |
| **A3** | Channel stock + velocity | B1 | Derived SOH / weeks-of-cover |
| **P2** | Usable by others | P3, adoption | Deployed, authenticated, navigable app |
| **P3** | Analytics platform | adoption | Governed report builder + scheduled delivery |
| **B1** | Forecasting | B2, B4 | Demand forecast, both grains |
| **B2** | Lineup + budget builder | B4 | Next-quarter lineup authored in CIP with reservation |
| **B4** | Promotion plan builder | — | New CPOR case authored from history |
| **P4** | CST (forward-only) | P5 | Live weekly sell-through facts |
| **P5** | Listings + channel execution | — | Price/availability observation history |
| **P6** | Multi-tenant productisation | — | Second tenant onboardable, no code changes |
| **X** | Retrofit + backlog burn-down | — | continuous lane |

---

## P0 — Stabilise the base

**Done:** `main` current with the full consolidation arc · branch hygiene complete, no branch
outside `main` · CI with real Postgres and `cip_test` · `scripts/verify-gate` proven (caught
its own false PASS).

**Remaining:** DSI header vocabulary (D-022 / BACKLOG-082) — **Done 2026-08-01** (P1-1).

**Deferred:** required GitHub status check on `main` — **dropped** (BACKLOG-087 removed;
Warren will not buy Pro). Process gate = CI + `scripts/verify-gate` + no casual `--admin` merges.

---

## P1 — Load the corpus

**Locked order:** census + defect-log scaffold → header vocabulary → DSI weekly → shipment
inbound → CPOR historical → lineups completeness → boundary batch-fix + sign-off.
Middle domains are permuteable; scaffold-first, vocabulary-before-DSI, and sign-off-last are
not.

**Blocking (fix inline):** identity mis-map · auto-create dim attempt · CPOR case-code loss ·
job crash.
**Log and continue:** steward queues · coverage gaps · NULL `pod_date` · FLAG leftovers ·
merge re-opens.

**Exit:** `docs/DATA_CENSUS.md` (domain × period, bucketed) + `docs/P1_LOAD_DEFECT_LOG.md`.
Verified means rows reconcile, no silent drops, domain invariant holds, **and Warren has run
the verification sequence and signed off** — never "rows exist".

---

## Lane A — Intelligence (backward-looking)

### A1 — Proposed vs Executed
**Entry:** P1 lineups + shipment signed off.
**Scope:** plan accuracy by quarter/BU/customer; fill rate (shipped-only); over-plan intake
(formerly “deal-stock landing”); over-ship as met-plan not penalty; PM volume bias and slip
per `docs/COMMERCIAL_SEMANTICS.md` (SPEC ONLY until built).
**BACKLOG-068 SUPERSEDED:** Budget attaches to the quarter stock **landed**, so
landing-quarter derivation is a first-class **dimension** available to A1/A2 analysis —
it is **not** a new tile on the Plan-vs-Executed screen. **`pod_date` completeness is
owned by Shipping** (`/shipping`); A1 consumes that measurement, it does not re-render it.
See `docs/COMMERCIAL_SEMANTICS.md`. Two axes coexist: fill rate / plan execution stays
**shipped**-basis; budget consumption is **landed**-basis. Never conflated.
**Support bias:** planned reservation vs actual CPOR spend — **CPOR-owned**, not PvE; blocked
on Q-002 (reservation = derived_from_profit). Do not put on Plan vs Executed.
**Window:** all quarters with lineup coverage; credible core 26Q1 → current.
**Exit:** plan-accuracy surface (fill + exceptions). Credibility artifact. *(A-lane wrap 2026-08-01: fill/exceptions/bias-slip BU/over-plan intake shipped; Q-009 → PM=business_line; Q-002 → derived-from-profit. **A1-09 Support bias IMPLEMENTED 2026-08-08** on CPOR Cases — `GET /cpor/intelligence/support-bias`. BACKLOG-068 Landed lens remains parked.)*

### A2 — CPOR intelligence
**Entry:** P1 CPOR historical signed off.
**Scope:** support spend by customer/BU/promo type (**BU = `dim_product.product_line`**);
**delivery rate** (`result_qty/estimate_qty`); support cost per unit sold under promo
(`support ÷ result_qty`); over/under-delivery patterns; per-customer support norms
(trailing 4Q, % and absolute, window config); comparable-case lookup ranked
(customer → BU → promo type → quarter proximity → volume).
**Currency:** USD compute/aggregate; display ZAR alongside; ZAR sums at each case’s FX.
**Out of scope:** cost per **incremental** unit (BACKLOG-089); **claim rate** (non-computable
until settlement stores an **owed** amount ≠ computed support — see `COMMERCIAL_SEMANTICS`.
**Paid** = distributor payment reconciliation via Ken — separate future input; **Warren owns files** — BACKLOG-092).
**Exit:** promo effectiveness surface. *(A-lane wrap 2026-08-01: A2-01/02/04/05/06 shipped. **BACKLOG-093 Promo load IMPLEMENTED 2026-08-08** — case tab + `…/promo-load-recon`.)*

### A3 — Channel stock + velocity
**Entry:** P1 DSI + shipment signed off.
**Scope:** derived channel stock (latest reported SOH per distributor×product − sell-out since
snapshot + POD-landed since; pipeline never counts); velocity; weeks of cover with
zero-velocity guard; replenishment signal.
**Exit:** *(A-lane wrap 2026-08-01: A3-01/02/03/04 shipped — WoC dist×product + 4w replenishment + YoY coverage. **A3-V VERIFY PASS 2026-08-08** on `/sell-out`.)*

---

## P2 — Usable by others

**Why here:** everything before this runs on your laptop. Nobody can depend on an app that
only exists on one machine, and dependency is the entire objective.

**Scope**
- **Deployment — DEFERRED.** Hosting target not set; the app is being completed to run
  locally. Revisit when Warren sets a target, budget and residency. Everything below is
  buildable and valuable locally.
- **User management** — admin adds users and assigns roles; no self-registration
- **Auth** — login, session management, password reset
- **RBAC** — roles at minimum: admin (config + SQL viewer), steward (import + resolve),
  planner (build + author), viewer (consume). Steward actions audited
- **Tenancy isolation** — every query tenant-scoped; cross-tenant leakage is a hard defect
- **App shell** — navigation, information architecture, and a **landing surface**: what a
  manager sees on login. State of the business, freshness, what needs attention
- **Monitoring** — error tracking, job failure alerting, uptime, log aggregation
- **Backup / restore / DR** — automated backups, tested restore, documented RTO/RPO

**Exit:** a second user logs in, sees a landing page, navigates to a surface, and you are not
involved. (Remote access awaits a hosting decision; multi-user readiness does not.)

**Note:** Alembic chain was squashed to baseline `20260801_0001` (B1-01 / P2-2).
Fresh DBs: `alembic upgrade head` alone — no `stamp head`. Legacy revisions live under
`apps/api/alembic/versions_legacy/` for archaeology only.

---

## P3 — Analytics platform

**Positioning:** not a PowerBI competitor in general. Categorically better *for channel
commercial planning*, because generic BI hands people columns and everyone invents their own
fill rate. CIP hands people **governed metrics**. Three analysts get one number.

### P3-1 Semantic layer (the actual product)
- **Metric registry** — locked definitions in `docs/COMMERCIAL_SEMANTICS.md`: fill rate,
  plan accuracy, PM volume bias, over-plan intake, velocity, weeks of cover (dist×product),
  support cost per unit sold, delivery rate, claim rate, channel stock. Each with formula,
  source facts, grain, and owning surface. Metrics not in that file are not built.
- **Dimension registry** — period, customer/account, distributor, product, BU, sales model,
  channel, region, `site_label`.
- **Validity rules** — each metric declares the grains at which it is meaningful. The builder
  *prevents* invalid combinations and explains why (e.g. SOH by lineup quarter is refused).
- **Config, not code** — tenant #2 defines its own metrics without a deploy.

### P3-2 Query engine
Composes metric + dimensions + filters into SQL. Users never write SQL. Domain invariants
applied automatically (latest-per-snapshot for SOH; shipped-only for fill). Materialised
aggregates + result cache to meet the NFR targets.

### P3-3 Report builder
Pick metric → slice by dimensions → filter → choose visual. "Easy" comes from the semantic
layer doing the thinking, not from a dumbed-down UI. Serves **both** audiences: authors build,
viewers consume, same governed numbers.

### P3-4 Dashboards, save and share
Saved reports, dashboards, sharing with role awareness, personal vs published.

### P3-5 Export and delivery
Excel and PDF export. **Scheduled delivery** — event-triggered (load completes → dependent
reports refresh → subscribers notified) **and** calendar-scheduled (Monday 7am regardless,
because missing data is itself the intelligence, per the tenant cadence rule).
**Every report declares its data vintage on its face.**

### P3-6 SQL / table viewer — admin only
Read-only connection, role-gated to admin, query timeout, row cap, audit log of who ran what.
**Not exposed to planners or viewers** — raw SQL access produces numbers that contradict the
governed metrics and destroys the single-source-of-truth guarantee.

**Exit:** a governed report built in the UI, scheduled, delivered to an inbox, declaring its
freshness.

---

## Lane B — Planning (forward-looking)

### B1 — Forecasting
**Entry:** A3.
**Scope:** demand forecast at the finest grain (product × customer × period), **rolled up by
summing**; quarter re-derivation available as a comparison view only. Seasonality trusted as
soon as confidence supports it. New products forecast by analogue (spec, segment, price band,
GPU, predecessor) with the analogue recorded as provenance. Confidence banding explicit.
Forecast is never merged into actuals.

### B2 — Lineup + budget builder *(B2 and B3 merged)*
**Entry:** A1 (bias) + A3 (stock/cover) + B1 (forecast).
**Why merged:** the reservation is embedded in the lineup's profit line — PM bottom sets the
floor, planned profit carries reserved support. A lineup builder that does not compute
profit-with-reservation is not usable by a PM. See `docs/COMMERCIAL_DOMAIN_RULES.md` §1, §4.

**Scope**
- **Net requirement planning:** `lineup qty = forecast − channel stock on hand − in-transit
  + target cover`. Target cover in weeks, per product (grain and unit tenant-configurable).
  In-transit = shipped-not-landed **plus** open POs where a PO exists.
- **Bias correction** from A1 — the thing Excel cannot do.
- **Profit line with embedded reservation** — PM bottom (fixed per quarter), planned price,
  derived reserved support.
- **Two commercial treatments per line** — normal-price volume vs discount volume (nominally
  50/50, actual split follows profit expectation).
- **Budget position** — aggregate reservations, drawn down by CPOR actuals, **on landed-quarter
  basis**. Unspent returns on under-delivery; cancelled cases free immediately. Reallocation
  across sales-model/customer permitted with audit trail. Track against both money and
  support-% views; money ceiling is primary (Q-001); support-% is a view, not an alternate
  hard constraint type.
- **FX** — booked or floating per case, USD denominated, derived from ZAR. Tenant-configurable
  pairing.
- 1H always splits Q1+Q2 (`uniform_half`), steward-overridable. Export to tenant template;
  upload existing lineup for reconciliation.

**Exit:** a next-quarter lineup authored in CIP with profit and reservation, exported in tenant
format. **This is the dependency moment.**

**Unit 1–3 (author loop) on `feat/b2-author-loop`:** net req → Apply → draft
`fact_lineup_plan_item` (+ optional `commercial_lineup_case`) → builder-economics + budget position
(`reservation_source=derived_from_profit`); half-year slots + A1 bias toggle; CSV + XLSX on-ramp.
Remaining B2 polish: **tenant export template** — full column-map parity with the tenant’s
existing lineup workbook **if** they reject the generic CSV/XLSX on-ramp. Shape lives in
tenant/profile config (P6), never OEM-branded app law. First-tenant sample files are fixtures
only (see governing rule: uploaded OEM files exemplify a shape, never define one). **B4** next
when author loop trusted.

### B4 — Promotion plan builder
**Entry:** A2 + B1 + B2.
**Scope:** author a new CPOR case — comparable historical cases from A2, volume from B1, budget
check against B2 reservations, waterfall math from CPOR v1, export in tenant format. Upload
path preserved.

**Unit B4-01 on `feat/b4-promo-draft`:** `/promotions` compose uses B2 lineup-derived budget;
`POST …/promo-plan-draft/create-case` writes a draft CPOR case (browser smoke: case #300 from seed 298).

## P4 — CST (forward-only)

**Deliberate de-risk:** do **not** backfill history first. Start from next week's files with
one or two accounts. Recon, article-alias resolution and listing seeds all work on forward data
alone. History only adds velocity/seasonality depth and becomes an optional later job.

**Not a single pilot.** Eight customers send weekly files directly: Takealot, Evetech,
Computer Mania, Incredible Connection, Amazon, HiFi Corp, Makro, Game. P4 is a **multi-format
ingest problem from day one** — expect a distinct layout family per customer. Per-customer
layout profiles are the shape; header-vocabulary config (D-022) is a hard prerequisite.

**Scope:** live weekly ingest across customer formats, article-alias steward, SOH
reconciliation (reported SOH is a check, never truth), listing seed emission.

**Progress 2026-08-09 (residuals + agent-safe follow-ons on `feat/p4-cst-six-customer-shapes`):**
Takealot on main (PR #25). Residual jobs: Amazon **910/918** (totals→units + **51 listing seeds**),
Game **911** (dual-header + SOH), IC **912** / HiFi **913**, CM **916→917** (`mtd_delta`).
**Generic** unit↔total + **generic** `feed_profile.listing_seed` (any marketplace customer).
Native CST **`.xls`** via xlrd (DSI parity). CST validate **`on_progress`** heartbeats wired.
Evetech soak **919/920**. Unit E Import Centre steward browser walk on job **911** (S1–S3/S8/S9 visible;
Locations FLAG≠BLOCK).
**Still open under P4:** historical backfill after soak. Forward apply soak **done 2026-08-10**
(7/8 customers with facts; Amazon FLAG — unresolved ASINs). Game W27 wide-week steward residual
(job 928) optional. Listing registry promote + live fetch moved to P5 (shipped on this branch).
Game header surfacing for `Asus Sales W27+` **done** (no new structure_type — dual_header fix).
**Q-003 hosting:** closed — local-only.


---

## P5 — Listings + channel execution

**Entry:** P4 live; CPOR cases live. **Live fetch + schedule may start immediately**
(Warren 2026-08-09) — do not wait for ≥2 weeks of observations to enable
`CIP_LISTING_LIVE_FETCH` / `CIP_LISTING_CAPTURE_SCHEDULE`. The ≥2 weeks bar applies
to **intelligence v1** (promo activated vs not, price compliance), not to starting history.
**Scope:** listing registry population, auto-finder (report ID → suggested URL → human
confirm), live fetch + schedule, observation history, then intelligence v1.

**Progress 2026-08-10:** env gates; auto-finder Amazon/Takealot/**Evetech** (no Google);
confirm-suggested; Amazon soak 51; Evetech 44 confirmed + polled (JSON-LD prices);
Takealot poll hits Next.js shell → parse_failed until better fetch. Observations tab +
manual poll on `/listing-capture`. **Listing↔CPOR activation** (BACKLOG-130) = point-in-time
obs price vs `cpor_case_line.srp`; persists `parse_flags.cpor_activation` including
`no_case_detected` — **not** gated on ≥14d history. Takealot REST fetch shipped 2026-08-13
(`feat/p5-residual`). Activation `not_activated` / `price_consistent` proven on historical
windows with live prices. Residual: upload latest CPOR covering **today**, then re-poll.

---

## P6 — Multi-tenant productisation

**Scope:** tenant configuration surface (BU vocabulary, period conventions, legal-form
normalizer, column-map profiles, metric definitions, export templates), onboarding path for
tenant #2, per-tenant branding, billing/packaging mechanics, tenant provisioning automation.
**Exit:** a second tenant onboarded without code changes.

**Note:** config extraction happens *continuously* inside every phase, not as a big bang here.

---

## Lane X — Retrofit and backlog burn-down (continuous)

Runs alongside all phases in GREEN autonomy. Never blocks a phase; never blocked by one.

- **Unit E (CST steward) VERIFY** — **PASS** Opus 2026-08-09 (S1–S14); browser walk job 911; stamp on
  `feat/p4-cst-six-customer-shapes` @ `69f64fa`.
- **Distributor merge** — same engine as customer merge, extended to `dim_distributor`
- **Existing surface retrofit** — PO management, PM gaps, channels/regions, product master,
  admin masters, commercial planner: audit each against the contract, retrofit or waive
- **Ops-list grid parity** (BACKLOG-085) — fold into whichever phase touches those pages
- **Lifecycle defect trio** — CST validate `progress_at` **wired 2026-08-09**; reaper inspect +
  retry/busy-guard already shipped for main pipeline. Remaining: non-CST importers if any gap.
- **BACKLOG-076** — corrupt unit amounts (~$36M). KPI exclude shipped; fact cleanup needs Warren.
- **BACKLOG-066 → 086** — worked down at phase boundaries, prioritised by trigger (087 removed)

---

## Dependency graph

```
P0 ──> P1 ──┬──> A1 ──────────────┐
            ├──> A2 ──────┬────────┼──> B3 ──┐
            └──> A3 ──> B1 ┴──> B2 <──────────┘
                            └──────────> B4
       P1 ──> A-lane ──> P2 ──> P3
       P1 ──────────────> P4 ──> P5
       (continuous) ────> P6 config extraction
       (continuous) ────> Lane X
```

**True parallelism:** A1 ∥ A2 ∥ A3 · Lane X ∥ anything · P2 infrastructure ∥ B-lane feature
work · P6 config extraction ∥ anything.
**Never parallel:** two units touching the steward engine · two units holding migrations ·
anything ∥ a P1 load domain.

---

## Application-level acceptance gate

The app is **done enough to sell** when all hold:

1. A manager logs in from their own machine and reaches a landing surface unaided
2. Weekly data loads run without you touching a CLI
3. A governed report is scheduled and lands in an inbox with its freshness declared
4. A PM authors next quarter's lineup in CIP and exports it in tenant format
5. A promotion case is built end-to-end from historical comparables and a budget check
6. Plan-accuracy and PM-bias numbers survive a domain expert's challenge
7. Backups run automatically and a restore has been tested
8. A second tenant can be onboarded with configuration only
9. No tenant-specific string exists in application code
10. The defect log contains no open item that would mislead a commercial decision

Items 1–6 are the demo. Items 7–10 are what make it a product rather than a demo.

---

## Operating guide

*(Restored 2026-08-01 — this section existed in v2 and was dropped by the v3 full-file
rewrite.)*

### How to read this file

- **Phase** = a destination with an exit artifact. Weeks, not days.
- **Unit** = one Cursor session's work. Hours to a day. Units live in the phase, not here.
- The **phase overview** tells you what is legal to start. The **dependency graph** tells
  you why. If a phase's blocker hasn't produced its exit artifact, that phase is not
  startable — the downstream work would be built on guesses.

### What you can start right now

Anything whose blocker is satisfied. **P1 exited 2026-08-01** (census + defect log sealed).
**A1 / A2 / A3** core + residuals closed 2026-08-08 (A1-09, A2-093, A3-V). Parked remain: 068 / 089 / 092 / 097.
**B1 / B2 author loop / B4-01 / P2 auth / P3 report builder** already on `main` — do not rebuild;
prove demo gate + close remaining holes (password reset, schedule soak, BACKLOG-076).
**P4/P5** on `feat/p4-cst-six-customer-shapes` (PR #26): multi-customer CST shapes + listing
capture/activation flags — promote when Warren asks. Next: CPOR upload + re-poll, or demo-gate
holes. Lane X runs continuously in GREEN alongside anything.

### What you cannot do

- Start a phase whose blocker hasn't exited.
- Fix defects inline during a load phase — they go to the log, batched at the boundary.
  This is the single discipline that stops modules running for weeks.
- Add a new import surface while the previous one has no real data through it.
- Build a metric onto a surface that doesn't own it (`docs/COMMERCIAL_SEMANTICS.md`).
- Leave a branch unmerged for more than a day.

### Parallel work — the test

Two units may run in parallel **only if all five hold**:

1. **Disjoint file surfaces** — no file appears in both diffs. Overlap means serialize.
2. **At most one migration in flight.**
3. **Neither is destructive or engine-level** — merges, supersession, bulk apply, and
   steward-engine edits run alone.
4. **Different owning surfaces** (`docs/COMMERCIAL_SEMANTICS.md`) — two units touching the
   same surface serialize even if the files differ.
5. **Both merge to `main` the same day.**

If any fails: serialize. The bottleneck is your attention and merge conflicts, not
Cursor's throughput.

**Naturally parallel:** A1 ∥ A2 ∥ A3 · Lane X ∥ anything · P6 config extraction ∥ anything.
**Never parallel:** two units on the steward engine · two units with migrations ·
anything ∥ a P1 domain load (that needs your eyes, not your attention split).

### How to run parallel work

1. Each unit gets its **own branch off current `main`**, named for the unit.
2. Each gets its **own Cursor session**.
3. Each ends with commit + push + **merge to `main` the same day**.
4. Rebase the sibling branch off the new `main` before continuing.

Two in flight is the practical ceiling. Three means one is drifting.

**Why the same-day rule:** `feat/ops-master-grid-shell-parity` reached ~36 commits while
`main` moved ~45 past its base, and became cheaper to delete than reconcile. A separate
incident lost a week of DSI work to a silent branch reset. Long-lived branches are this
project's most expensive recurring failure.

### When consult fires

| Situation | Consult? |
|-----------|----------|
| Phase entry — lock scope, name exit artifact, name owning surfaces, reject thin paths | **Yes** |
| Domain fork — variance vs capability gap, budget semantics, forecast grain | **Yes** (or Warren directly) |
| New metric with no owning surface | **Yes** |
| Destructive path — merge, supersession, bulk apply | **Yes** |
| Two failed fix attempts without root cause | **Yes** (charter no-patches rule) |
| A unit inside an open phase, scope already locked | No — gate script |
| Hygiene, config extraction, mechanical re-application | No |
| Bug with a known cause | No |
| Anything the gate script can prove mechanically | No |

**Gate script covers:** tsc error-list diff, matched test file sets, prohibited-pattern
grep, base-integrity check, pre-build existence audit. Cheap, every unit, no usage cap.
Reserve paid judgment for decisions, not verification.

### Phase entry checklist

1. Read this file, the charter, `COMMERCIAL_DOMAIN_RULES.md`, `COMMERCIAL_SEMANTICS.md`.
2. **Name the owning surface for every metric the phase introduces.** No owner = design
   decision for Warren, never an agent default. Metric must be defined in
   `COMMERCIAL_SEMANTICS.md` or not built.
3. Run consult once: lock scope, name the exit artifact, reject thin paths.
4. Units inside the phase run on the gate script.

### Weekly rhythm

- **Start of week:** what phase, what's its exit artifact?
- **Daily:** one or two units. Merge to `main` before stopping.
- **Phase exit:** batch-fix the defect log, produce the artifact, update CURRENT +
  CONTEXT changelog, re-read this file.
- **When a phase runs long:** the question is never "push harder." It's "did the defect
  log turn back into inline fixing?"

### Document discipline

Docs whose content is **factual claims about the codebase** — surface ownership, route
inventories, module status — are generated from the tree by Cursor and reviewed by
Warren/consult. They are not drafted from memory. The v1 surface-ownership draft was
written from memory and was wrong in 5 of 13 rows, including two errors of exactly the
kind it existed to prevent. Authoritative map: `docs/COMMERCIAL_SEMANTICS.md`.

Docs whose content is **decisions and process** — this roadmap's phases, the charter, the
decisions log — are authored by Warren/consult and verified against the tree where they
make factual claims.

**Full-file rewrites drop sections.** This Operating guide was lost that way. When
replacing a governing doc wholesale, diff the section list before and after and report
any section that disappears.

---

## Open decisions register

Still open (authoritative detail: `docs/OPEN_QUESTIONS.md`; domain mirror:
`docs/COMMERCIAL_DOMAIN_RULES.md` § Still open):

| # | Decision | Blocks | Owner | OPEN_QUESTIONS |
|---|----------|--------|-------|----------------|
| 3 | ~~Hosting target~~ | — | **Closed** — local-only (Warren 2026-08-09) | Q-003 |
| 4 | Per-customer CST file formats (8 customers) | P4 forward multi-format | Discovered at first load | Q-004 |

**Deferred by design (not an open question — see Out of scope):** branch/location modelling;
never alias branches to parent customers. Blocks tagged-customer sell-through until a
deliberate model ships.

**Resolved (do not re-ask):**

| # | Decision | Resolution | Source |
|---|----------|------------|--------|
| 1 | Budget constraint type — money vs support-%? | **Money ceiling** is primary; support-% is a view / weak target, not an alternate hard-constraint type. Over ceiling → reapproval. | Q-001 · `COMMERCIAL_DOMAIN_RULES` |
| 2 | Lineup reservation — workbook column or derived? | **Derived** from PM bottom vs planned price (`derived_from_profit`); not an explicit reservation column. | Q-002 · `COMMERCIAL_DOMAIN_RULES` · A1/B lane shipped on this basis |

**Settled and recorded in `docs/COMMERCIAL_DOMAIN_RULES.md`:** budget derivation · landing-quarter
basis · currency and FX handling · unspent return and cancellation · pot grain · PM bottom
cadence · 50/50 volume split · forecast rollup · seasonality · new-product analogue · target
cover · in-transit definition · user management · reporting audience · IP ownership ·
budget constraint type (Q-001) · reservation derivation (Q-002).

## Out of scope

- Field-merchandising mobile app — separate product, separate timeline
- CST historical backfill — optional job after P4 proves the pipe
- Branch/location model — deferred; never alias branches to parent customers
