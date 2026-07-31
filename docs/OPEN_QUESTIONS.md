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

### Q-005 — A1 PM planning bias surface

| Field | Value |
|-------|--------|
| **What is unclear** | Does “PM planning bias across years” already exist as a tile/API on `/plan-vs-executed`, or is it a new metric to design? |
| **Why it matters** | ROADMAP A1 scope lists PM bias; pre-build audit required before any new tile (D-023/D-024) |
| **Interim assumption** | A1 exit for this run = existing fill / deal-stock / short / unplanned / no-PO surface + default-period fix. PM bias is a **separate design-stage AMBER** if missing |
| **What would change** | New scorecard fields / tiles on Plan vs Executed only if audit finds no owner |
| **Blocking?** | No for fill-rate credibility; Yes before claiming full ROADMAP A1 scope complete |
| **Blocks** | Full A1 “PM bias” claim |
| **Owner** | Cursor (audit) → Warren if new metric |
| **Raise by** | A1 module |
| **Source** | ROADMAP A1 scope; SURFACE_OWNERSHIP |

---

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

*(none yet)*
