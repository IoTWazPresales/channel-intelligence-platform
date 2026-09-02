# N-0013 operator decisions (amended package)

**Programme:** PRG-20260831T145514 · **N-0013** · revision after amendment 2026-09-02  
**Do not accept r1 D-0001** — use amended statements below.

---

## D-0001 (amended) — Core full-platform architecture

**Proposed spine:**

| Job | Label | Route (proposed) |
|---|---|---|
| Attention | Brief | `/brief` |
| Plan origination | Plan | `/plan` |
| Position & execution | **Position** | `/position?lens=*` |
| Funding & claims | Settlement | `/settlement` |
| Commercial response | Actions | `/actions` |
| Ingest & steward | **Imports** | `/imports` |

**Utilities (demonstrated in mockups):**

- **Reports** — Build · Dashboards · Inbox (`/reports/build`, `/reports/dashboards`, `/reports/inbox`)
- **Admin** — Access · Settings · Operations · Trust

**Includes:** shell convergence direction, primitive library phases, migration waves, FROZEN v1.1 as craft floor.

**Excludes:** Phase A product implementation until this decision + D-0002 + D-0003 recorded.

**Warren action:** Approve **amended D-0001**, or annotate label/route changes.

---

## D-0002 — Mapping queue UI (`/admin/mappings`)

**Facts:**

- Page and API exist; no current spine nav (reconciliation: cheapest RESTORE candidate)
- NAV_MAP marked "retired on trigger" — not proven obsolete
- Steward engine may supersede **eventually** — not demonstrated for all queue types today

**EIF recommendation:** **RESTORE** under Imports → worklists → "Legacy mappings" until steward parity TRIGGER fires.

**Options for Warren:**

| Option | Meaning |
|---|---|
| **A — RESTORE** (recommended) | Nav entry under Imports; page converges to workbench chrome in Wave C |
| **B — RETIRE UI** | Remove nav permanently; engine-only; requires written acceptance that operators reach mappings only via steward worklists |

**Warren action:** Choose A or B (or variant with explicit TRIGGER).

---

## D-0003 — Control tower landing vs KPI capability vs Brief

**Concepts (do not conflate):**

| Concept | What it is | Proposed home |
|---|---|---|
| **Landing job** | What opens after login — attention, not analytics | **Brief** (replaces `/dashboard` as landing) |
| **KPI card grid** | Analytical summary tiles (channel stock, cover means, etc.) | **Not on Brief** by default — propose **Reports → Dashboards** |
| **Signal queue** | Ranked trust/position/money work items | **Brief** |
| **Saved dashboards** | Persistent analytical views operator returns to | **Reports → Dashboards** |

**EIF recommendation:**

- **Approve Brief as landing** (MERGE control-tower landing job)
- **Restore KPI analytical capability** via Reports → Dashboards (not silent retirement)
- **Do not** restore `/dashboard` as a second landing

**Options for Warren:**

| Option | Landing | KPI tiles |
|---|---|---|
| **A** (recommended) | Brief | Dashboards under Reports |
| **B** | Brief | Optional compact KPI strip on Brief (in addition to signals) |
| **C** | Brief | Restore `/dashboard` as secondary analytical route (not landing) |

**Warren action:** Choose A, B, or C.

---

## Evidence index (amended)

| File | Purpose |
|---|---|
| `docs/design/CIP_PLATFORM_ARCHITECTURE_PROPOSAL.md` | Full architecture (amended) |
| `rendered-verification-r2.md` | Agent verification |
| `independent-rendered-review-r2.md` | Independent review |
| `index.html` | Gallery |
| `platform-shell-mobile.html` | 390px drawer |
| `reports-utility-desktop.html` | Reports architecture |
| `admin-utility-desktop.html` | Admin architecture |
