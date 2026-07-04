# Current state

**Last updated:** 2026-07-04 (invoice-line mint graduation + cip repair)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/unit-6-unified-lineup-import-centre` |
| **HEAD** | *(pending commit — invoice-line graduation)* |
| **PR** | None open |
| **Alembic (code)** | `20260702_0066` (head) |
| **Alembic (DB)** | **`20260702_0066`** on local `cip` |

---

## Database and environment

| Field | Value |
|-------|--------|
| **Active DB** | Local Postgres `cip` @ `127.0.0.1:5432` (topology B) |
| **Bitemporal flags** | `CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE` / `_READ` — **default ON** |
| **Observation store** | View `shipment_evidence_current` **14,673** rows (post graduation repair; was 14,847) |
| **Invoice-line graduation** | **174** lineages quantity-graduated on cip; **432** blank observation versions superseded; audit `invoice_line_graduation_gap` = **0** |
| **Legacy supersede** | 35,134 + graduated blank corpus lines `corpus_superseded_at` |
| **Celery dispatch** | `broker` (apps/api/.env) |

---

## Invoice-line mint graduation — DONE (2026-07-04)

| Step | Status |
|------|--------|
| Write path (dual-write hook) | Quantity-gated supersede / `invoice_partial_graduation` flag |
| One-time repair | Preview 174 full / 0 partial; **13,685** double-count units; clone + cip green |
| Integrity audit | `invoice_line_graduation_gap` check added |
| Change events | `graduated` + `graduation_kind: invoice_mint` on lineage thread |

**Preview impact (pre-repair):** 174 lineages · top double-count 26Q2 Open Channel 5,581 units.

**Sample invoice_mint event:** order `151126051002768` line `1.1` item `90NR0NG1-M00C30` → `ship:15260187716|…|8883|1`.

---

## Plan D cutover — DONE (2026-07-02)

| Phase | Commit | Gate |
|-------|--------|------|
| 1 Identity + clone proof | `9109664` | `cip_planD_smoke` green; 0 split collapse |
| 2 cip cutover | `1b77efc` | Migration 0066; jobs 153/154 backfilled; dual-write ON |
| 3 Consumers + supersede | `6de21b8` | Audit **5b=0**; 35,134 superseded; parity **184** fact-mismatch worklist |
| 4 Change events v1 | `91f227e` | API + CLI; unit tests green; real chain spot-check jobs 32/40 |

**Integrity audit (cip):** `evidence_true_dupes` (5b) = **0** · `evidence_fact_parity` = **184** (genuine fact_qty / single_line_undercount steward worklist) · `duplicate_qty_inflation_groups` = **0**.

**Open→shipped fact double-count (diagnostic only, BACKLOG-062):** 104 matching pairs; open qty 5,752 / shipped qty 7,224 — remediation deferred.

**Sample change event (jobs 32→40):** `order:151126031011047|1.1|90NR0KS1-M00EW0` — `est_pod` slip −1 day, `erd` slip −1 day.

---

## Consumer read sources (after Plan D)

| Consumer | Read source |
|----------|-------------|
| DSI corroboration (cache + per-row) | `shipment_evidence_current` |
| DSI receipt disambiguation | `shipment_evidence_current` |
| DSI product tiebreak | via corroboration (current view) |
| Lineup PO reconciliation / suggested POs / BU resolution | `shipment_evidence_current` |
| Shipment evidence API list/get | `shipment_evidence_current` |
| Shipping ETA LAG metrics | `shipment_evidence_observation` partitioned by `line_identity_key` |
| Channel ops, usage counters | `shipment_evidence_current` |
| Steward writes / import apply | `shipment_evidence_line` (unchanged) |

---

## Dev topology

Local desktop (no Docker): `pnpm dev:api` :8001 · `pnpm dev:web` :3000 · `pnpm dev:worker` (Redis :6379) or `CIP_DEV_CELERY_DISPATCH=in_process_thread`.

---

## Next

- **BACKLOG-062:** Warren decision on open→shipped fact remediation (104 pairs measured).
- **BACKLOG-057/058:** D4/D5 legacy column deprecation after soak.
- **Unit 6 browser soak** (unified lineup import centre) — unchanged from prior CURRENT.
- **Spec C Step C:** archive lineup backfill + link-apply.

---

## Prior session context (abbreviated)

Unified lineup import Units 1–8 backend done; Unit 6 frontend wired. Spec C Step A/B done (`20260701_0064`/`0065`). Distributor full merge on `cip`. PO coverage compound match (`80b864a`/`daac5f6`). Data integrity audit tool (`10fd3ea`).
