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
| **Why it matters** | Lineup schema, CPOR linkage, budget consumption, and fill-rate attribution all depend on the answer — settle before A1 ships |
| **Interim assumption** | At P1 lineup load, discovery handles both: capture explicit reservation/split column if present; otherwise derive from PM bottom vs planned price |
| **What would change** | Schema columns, import mapping, and A1 support-bias metric inputs |
| **Blocking?** | **Yes for A1 ship**; discovery is P1 work |
| **Blocks** | Lineup schema |
| **Owner** | **P1 discovery** |
| **Raise by** | P1 lineup load |
| **Source** | Domain rules Still open #2 |

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

*(none yet)*
