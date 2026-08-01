# Open Questions

**Protocol:** `docs/AUTONOMOUS_BUILD_CHARTER.md` § Question Queue  
**Seeded:** 2026-07-31 from `docs/COMMERCIAL_DOMAIN_RULES.md` § Still open  
**Rules:** Append-only within a module. Resolved entries move to **Resolved** with answer + date. Non-blocking questions do not stop work — record the assumption and continue. Blocking questions halt that module only.

Each entry: what is unclear · why it matters · interim assumption · what would change · blocking or not.

---

## Open

### Q-001 — Budget constraint type

| Field | Value |
|-------|--------|
| **What is unclear** | Is the binding constraint a **money ceiling** or a **support-% ceiling per unit**? (`COMMERCIAL_DOMAIN_RULES` §1.8) |
| **Why it matters** | Determines how budget enforcement is coded in B2; wrong hard-enforcement would block valid spend or allow overspend |
| **Interim assumption** | Track spend against **both** money and support-% views; do **not** hard-enforce either until Warren confirms |
| **What would change** | Enforcement gates, validation errors, and B2 budget-position UI would bind to one axis instead of dual tracking |
| **Blocking?** | No for tracking/build; **Yes** for hard enforcement |
| **Blocks** | Budget enforcement |
| **Owner** | Warren |
| **Raise by** | A2 entry (charter interview trigger) |
| **Source** | Domain rules Still open #1 |

### Q-002 — Lineup reservation column vs derived

| Field | Value |
|-------|--------|
| **What is unclear** | Is the lineup reservation an **explicit column** in the PM workbook, or **purely derived** from PM bottom vs planned price? |
| **Why it matters** | Lineup schema, CPOR linkage, budget consumption, and support-bias inputs depend on the answer |
| **Interim assumption** | P1-5 leave-alone: no new lineup file discovery this phase. Existing `po_issued` cases (3 / 285 lines / 52 PO links) power A1 **fill** without reservation discovery. Support-bias remains CPOR-owned (`SURFACE_OWNERSHIP`); do not invent a PvE support tile until this is answered |
| **What would change** | Schema columns, import mapping, and any cross-read of reservation into A1/CPOR |
| **Blocking?** | **No for A1 fill-rate surface**; **Yes for support-bias / B2 reservation authoring** |
| **Blocks** | Support-bias attribution; B2 lineup schema |
| **Owner** | Warren / PMs |
| **Raise by** | Before A1 claims support-bias; before B2 |
| **Source** | Domain rules Still open #2; P1-5 leave-alone 2026-08-01 |

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

### Q-009 — Lineup PM attribution source for volume bias

| Field | Value |
|-------|--------|
| **What is unclear** | Where does **product manager / PM** attribution live for lineup plan lines — workbook column, case field, customer `account_owner_internal`, or elsewhere? |
| **Why it matters** | A1-07 requires bias by **BU and PM**. Tree has no PM field on `commercial_lineup_case` / line `raw_row_payload`; customer `account_owner_internal` is empty on cip. BU bias ships without inventing a PM dimension. |
| **Interim assumption** | Compute **BU-only** volume bias; `pm_attribution: unavailable` until source locked |
| **What would change** | `by_pm` buckets on PvE read model + UI tile; possible import/mapping of PM onto case or line |
| **Blocking?** | **No for BU bias / A1-08 slip**; **Yes for PM volume-bias buckets** |
| **Blocks** | A1-07 PM dimension only |
| **Owner** | Warren / PMs |
| **Raise by** | Before claiming full A1-07 PM bias |
| **Source** | Tree audit 2026-08-01; A1 bias/slip unit |

---

## Resolved

### Q-008 — A2-03 claim rate — **Resolved 2026-08-01 (non-computable)**

| Field | Value |
|-------|--------|
| **Answer** | **No** independent **owed** amount. U5 claim evidence = product × date × **units** (+ optional unit_price); rollup sets `result_qty`; `ttl_result` = `support_unit × result_qty` with the **same** approval `support_unit`. Settlement tab shows estimate/result/ttl_* — no owed field distinct from computed support. Therefore claim rate collapses into delivery rate → **do not build**; removed from catalogue → non-computable register (TRIGGER: **owed** amount distinct from computed support). **Paid** is out of scope here — it needs distributor payment reconciliation from Ken / admin, not claim-evidence settlement. |
| **Source** | Tree audit `claim_evidence*.py`, `settlement.py`, `waterfall.py`, settlement UI; Warren 2026-08-01 |

### Q-005 — A1 PM planning bias surface — **Resolved 2026-08-01**

| Field | Value |
|-------|--------|
| **Answer** | Formulas locked in `COMMERCIAL_SEMANTICS` A1-07/A1-08. **Built 2026-08-01:** BU volume bias + ship-quarter slip on `/plan-vs-executed` (`volume_bias`, `slip`). **PM** bias remains blocked on **Q-009** (no PM source in tree). |
| **Source** | Warren → COMMERCIAL_SEMANTICS consolidation; A1 bias/slip unit |

### Q-006 — A2 promo-effectiveness metrics — **Resolved 2026-08-01**

| Field | Value |
|-------|--------|
| **Answer** | Formulas locked in `COMMERCIAL_SEMANTICS` §4.3. Cost per **incremental** unit = DO NOT BUILD (BACKLOG-089). BU = `dim_product.product_line`. A2-01/02/06 implemented (A2-U1). A2-03 claim rate → non-computable (Q-008 / D-027: need distinct **owed**, not paid). A2-04/05 still SPEC ONLY. |
| **Source** | Warren → COMMERCIAL_SEMANTICS / ROADMAP A2 |

### Q-007 — A3 replenishment + WoC grain — **Resolved 2026-08-01**

| Field | Value |
|-------|--------|
| **Answer** | WoC grain = **distributor × product only**; customer-grain velocity vs channel stock is a defect (BACKLOG-090 — do not “fix” with another average). Replenishment v1 = threshold flag, **default 4 weeks**, tenant config. Derived stock latest-per-pair already correct (ROADMAP false claim removed). |
| **Source** | Warren → COMMERCIAL_SEMANTICS A3; code audit `channel_ops_derived_stock` / `channel_ops.py` |
