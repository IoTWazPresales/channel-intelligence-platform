# Current state

**Last updated:** 2026-07-02 (Plan D bitemporal shipment evidence cutover complete)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/unit-6-unified-lineup-import-centre` |
| **HEAD** | `91f227e` — Plan D phases 1–4 (bitemporal cutover + change events v1) |
| **PR** | None open |
| **Alembic (code)** | `20260702_0066` (head) |
| **Alembic (DB)** | **`20260702_0066`** on local `cip` |

---

## Database and environment

| Field | Value |
|-------|--------|
| **Active DB** | Local Postgres `cip` @ `127.0.0.1:5432` (topology B) |
| **Bitemporal flags** | `CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE` / `_READ` — **default ON** (env = emergency off-switch) |
| **Observation store** | 49,981 observations = 49,981 evidence lines; view `shipment_evidence_current` 14,847 rows |
| **Legacy supersede** | 35,134 `shipment_evidence_line` rows marked `corpus_superseded_at` (soft; no deletes) |
| **Celery dispatch** | `broker` (apps/api/.env) |

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
