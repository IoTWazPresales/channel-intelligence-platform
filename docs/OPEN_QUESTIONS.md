# Open Questions

**Protocol:** `docs/AUTONOMOUS_BUILD_CHARTER.md` § Question Queue  
**Seeded:** 2026-07-31 from `docs/COMMERCIAL_DOMAIN_RULES.md` § Still open  
**Rules:** Append-only within a module. Resolved entries move to **Resolved** with answer + date. Non-blocking questions do not stop work — record the assumption and continue. Blocking questions halt that module only.

Each entry: what is unclear · why it matters · interim assumption · what would change · blocking or not.

---

## Open

### Q-011 — PROGRAM-A Unit 2 / bulk-select survivor+contested guard predicates

| Field | Value |
|-------|--------|
| **What is unclear** | (1) Survivor guard predicate: refuse when target case already has ≥1 linked PO or status `po_issued`+ as proxy for 7/9/90, OR explicit protected-case-id set (incl. 122/145 / D-031 nuance on 9)? (2) Any protected survivors currently at pre-PO status (`draft_imported`/`accepted`)? Status proxy unsafe if yes. (3) Guarded target: hard-refuse vs allow with per-item override (`allow_protected=true`) that bulk cannot pass? (4) Contested: confirm D-033 — UI exclude + preview competing ids + annotation, **no service gate** — or supersede D-033 for contested bulk ack? |
| **Why it matters** | Blocks BACKLOG-115/110 service+UI guard. Payload already has `competition`; web type drops it. No `is_survivor` column exists. |
| **Interim assumption** | Unit 2 parked NEED_HUMAN. Programme continues Unit 3+. Do not implement guard until Warren answers. Contested stays FLAG≠BLOCK unless Warren supersedes D-033. |
| **What would change** | Service refuse semantics; select-all exclusion set; whether D-033 is superseded. |
| **Blocking?** | **Yes for Unit 2 only** |
| **Blocks** | PROGRAM-A Unit 2; feeds Unit 5 S14 |
| **Owner** | Warren |
| **Raise by** | PROGRAM-A Unit 2 CONSULT NEED_HUMAN |
| **Source** | `.tmp/unit2_bulk_select_consult_opus_response.md` 2026-08-05 |

### Q-010 — PROGRAM-A Unit 1 / PR #17 promotion decomposition

| Field | Value |
|-------|--------|
| **What is unclear** | (1) Is BACKLOG-098 Celery beat (`87e5be1`) ready to promote now, or hold until a named readiness bar? STATE_AUDIT_2026-08-02 #7 deferred merge until beat ready. (2) Are lineup budget commits `120a62a` + `3ed1348` still valid after D-028/D-029/D-030, or must drawdown route through `resolve_layered_period` instead of branch `normalize_period_label`? (3) Approve split: land `eb333fe` + `2ae6192` now; gate beat on (1); gate budget on (2)? (4) Doc conflict rule confirm: preserve main, ADD branch; CONTEXT add-only; re-check contract edit vs 1.6. |
| **Why it matters** | Blocks Unit 1 main promotion; Unit 8 scopes against post-Unit-1 tree. All-or-nothing promote is a false binary (Opus CONSULT 2026-08-05). |
| **Interim assumption** | Unit 1 parked NEED_HUMAN. Programme continues Unit 2+. Do not land any of the five commits until Warren answers. |
| **What would change** | Which commits land on main; whether budget_position / beat remain stranded; Unit 8 baseline. |
| **Blocking?** | **Yes for Unit 1 only** |
| **Blocks** | PROGRAM-A Unit 1; Unit 8 post-merge scope |
| **Owner** | Warren |
| **Raise by** | PROGRAM-A Unit 1 CONSULT NEED_HUMAN |
| **Source** | `.tmp/unit1_pr17_consult_opus_response.md` 2026-08-05 |
| **Note** | Warren 2026-08-05 ("complete also open") still needs explicit answers to Q-010 1–4 and Q-011 1–4 before Units 1–2 IMPLEMENT. |

### Q-003 — Hosting target

| Field | Value |
|-------|--------|
| **What is unclear** | Hosting target, budget, and data residency for remote deployment |
| **Why it matters** | Unlocks P2-1 deployment; without it the app stays local-only |
| **Interim assumption** | Complete locally; multi-user readiness (auth, roles, shell) still in scope and buildable locally. P2-1 stays RED until Warren sets a target |
| **What would change** | Infra, env topology, backup/DR hosting, and remote-access path |
| **Blocking?** | **Yes for P2-1 only**; not for local multi-user work |
| **Blocks** | Deployment |
| **Owner** | Warren (deferred by choice) |
| **Raise by** | When Warren sets a hosting target |
| **Source** | Domain rules Still open #3 |

### Q-004 — Per-customer CST file formats

| Field | Value |
|-------|--------|
| **What is unclear** | Exact per-customer CST layout families for the eight direct senders (Takealot, Evetech, Computer Mania, Incredible Connection, Amazon, HiFi Corp, Makro, Game) |
| **Why it matters** | P4 is multi-format from day one; header-vocabulary (D-022) and per-customer layout profiles are the shape |
| **Interim assumption** | Formats are discovered at first load per customer; no single-format pilot |
| **What would change** | Layout profiles, mapping templates, and steward queues per customer |
| **Blocking?** | No until P4 load of that customer |
| **Blocks** | P4 (per customer at first load) |
| **Owner** | Discovered at first load |
| **Raise by** | P4 entry / first customer file |
| **Source** | Domain rules Still open #4 |

---

## Resolved

### Q-U3 — PROGRAM-A Unit 3 NR line-count / Sheet1 — **Resolved 2026-08-05**

| Field | Value |
|-------|--------|
| **Answer** | Done bar = **~120** NR case lines (BU-sliced from 126 sheet rows). Ignore Sheet1 (content ⊆ NR → exclude). Resume D-034 → clone → cip. Shipped case **146** = 120 lines; case **130** soft-superseded. |
| **Source** | Warren 2026-08-05 PROGRAM-A chat |

### Q-001 — Budget constraint type — **Resolved 2026-08-01**

| Field | Value |
|-------|--------|
| **Answer** | Binding axis = **money (rand/USD) ceiling**. Over ceiling → **case must be reapproved** (no silent overspend). Support-% is weak for this tenant — reservation is more a **target** than a % cap; little % headroom and no per-line customer sales cap today. **TENANT-VARIABLE:** profile keys `constraint_axis` (`money` \| `support_pct` \| `dual` \| `none`) and `over_budget_action` (`require_reapproval` \| `warn` \| `block`). Current tenant default: `money` + `require_reapproval`. Hard reapproval workflow = BACKLOG (profile stub ships first; `hard_enforce` stays false until that unit). |
| **Source** | Warren 2026-08-01; `commercial_tenant_profile.py`; domain §1.8 |

### Q-002 — Lineup reservation column vs derived — **Resolved 2026-08-01**

| Field | Value |
|-------|--------|
| **Answer** | Reservation **comes from profit** — derived from PM bottom vs planned economics (not a separate handed-down pot). Commercial context: local P&L is often not profitable; **HQ inflates PM bottom** so support room is already embedded in the floor — do not invent an external budget pot. **TENANT-VARIABLE:** `reservation_source` = `derived_from_profit` \| `explicit_column` \| `hybrid`. Current tenant default: `derived_from_profit`. Support-bias planned side may use this derived reservation. |
| **Source** | Warren 2026-08-01; domain §1.1 / §1.8 data-model; `commercial_tenant_profile.py` |

### Q-009 — Lineup PM attribution source for volume bias — **Resolved 2026-08-01**

| Field | Value |
|-------|--------|
| **Answer** | This tenant: PMs are allocated **per business line** (NB, NR, NV, NX) — not a separate person field on lineup. Volume-bias PM grain = existing **BU / product_line** buckets (`by_bu`); `pm_attribution: business_line`. Other businesses may use person fields — **TENANT-VARIABLE** `pm_attribution_mode` = `business_line` \| `person_field` \| `none`. Do not invent a person PM column for the current tenant. Onboarding/settings later override the profile. |
| **Source** | Warren 2026-08-01; `commercial_tenant_profile.py`; PvE `compute_volume_bias` |

### Q-008 — A2-03 claim rate — **Resolved 2026-08-01 (non-computable)**

| Field | Value |
|-------|--------|
| **Answer** | **No** independent **owed** amount. U5 claim evidence = product × date × **units** (+ optional unit_price); rollup sets `result_qty`; `ttl_result` = `support_unit × result_qty` with the **same** approval `support_unit`. Settlement tab shows estimate/result/ttl_* — no owed field distinct from computed support. Therefore claim rate collapses into delivery rate → **do not build**; removed from catalogue → non-computable register (TRIGGER: **owed** amount distinct from computed support). **Paid** is out of scope here — it needs distributor payment reconciliation from Ken / admin, not claim-evidence settlement. |
| **Source** | Tree audit `claim_evidence*.py`, `settlement.py`, `waterfall.py`, settlement UI; Warren 2026-08-01 |

### Q-005 — A1 PM planning bias surface — **Resolved 2026-08-01**

| Field | Value |
|-------|--------|
| **Answer** | Formulas locked in `COMMERCIAL_SEMANTICS` A1-07/A1-08. **Built 2026-08-01:** BU volume bias + ship-quarter slip on `/plan-vs-executed` (`volume_bias`, `slip`). **PM** for current tenant = business-line mode (Q-009 resolved 2026-08-01) — same grain as `by_bu`. |
| **Source** | Warren → COMMERCIAL_SEMANTICS consolidation; A1 bias/slip unit; Q-009 |

### Q-006 — A2 promo-effectiveness metrics — **Resolved 2026-08-01**

| Field | Value |
|-------|--------|
| **Answer** | Formulas locked in `COMMERCIAL_SEMANTICS` §4.3. Cost per **incremental** unit = DO NOT BUILD (BACKLOG-089). BU = `dim_product.product_line`. A2-01/02/06 implemented (A2-U1). A2-03 claim rate → non-computable (Q-008 / D-027: need distinct **owed**, not paid). **A2-04/05 IMPLEMENTED (A2-U2)** — norms + ranked comparable; B4 consumes `build_comparable_cases`. |
| **Source** | Warren → COMMERCIAL_SEMANTICS / ROADMAP A2 |

### Q-007 — A3 replenishment + WoC grain — **Resolved 2026-08-01**

| Field | Value |
|-------|--------|
| **Answer** | WoC grain = **distributor × product only**; customer-grain velocity vs channel stock is a defect (BACKLOG-090 — do not “fix” with another average). Replenishment v1 = threshold flag, **default 4 weeks**, tenant config. Derived stock latest-per-pair already correct (ROADMAP false claim removed). |
| **Source** | Warren → COMMERCIAL_SEMANTICS A3; code audit `channel_ops_derived_stock` / `channel_ops.py` |
