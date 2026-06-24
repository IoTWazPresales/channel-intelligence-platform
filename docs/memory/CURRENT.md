# Current state

**Last updated:** 2026-06-24 (Plan D bitemporal shipment evidence — cloud agent)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `cursor/cloud-agent-1782231728131-em82n` (from `feat/dsi-async-topology`) |
| **HEAD (snapshot)** | Plan D bitemporal (D1–D3) after Plan C |
| **PR** | Open — Plan C + Plan D |
| **Alembic (code)** | `20260623_0050` (`shipment_evidence_observation` + `shipment_evidence_current` view) |
| **Alembic (DB)** | `20260623_0050` (cloud Docker `cip`) |

---

## What is working

### Plan C (shipment steward parity)
- **ShipmentImportJobResolutionSection** — shared workspace, entity tabs, paginated list, resolution plan toolbar.
- **Shipment resolution plan API** — compute/effective/apply-async on `/api/v1/shipment-evidence/`.
- **Paginated candidates** — `mapping-candidates/paginated` + `tab-counts`.
- **Legacy retained** — `ShipmentEntityStewardPanelLegacy` dialog + all existing bulk endpoints.

### Plan D (bitemporal evidence — D1–D3)
- **Migration 0050** — `shipment_evidence_observation` append-only table + backfill from legacy lines + `shipment_evidence_current` view.
- **Dual-write (D2)** — `CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE=1` appends observations after validate (`sync_job_observations_after_validate`).
- **Read switch (D3)** — `CIP_SHIPMENT_BITEMPORAL_READ=1` routes DSI corroboration SQL to `shipment_evidence_current`.
- **Line identity** — `shipment_evidence_line_identity.py` (`order:` / `ship:` / `digest:` keys).

**Flags default OFF** — legacy `shipment_evidence_line` path unchanged until Warren enables.

---

## In progress / not proven live

- Plan C browser soak on large ACZA jobs.
- Plan D D4–D5 (deprecate legacy columns, cleanup) — not started.
- Steward resolution updates do not yet append new observations (only validate dual-write).

---

## Next (recommended)

1. Merge PR after review; Warren smoke shipment wizard + enable flags on staging.
2. BACKLOG-007 post-validate re-map spike.
3. Plan D D4 when weekly shipment cadence goes live.

---

## Blockers requiring Warren

- Promotion to `main` — explicit instruction only.
- Enable bitemporal flags in staging/prod when ready.

---

## Key references

| Topic | Doc |
|-------|-----|
| Operator (evidence vs fact) | `docs/SHIPMENT_EVIDENCE_OPERATOR.md` |
| Plan D (bitemporal) | `docs/SHIPMENT_BITEMPORAL_PLAN_D.md` |
| BACKLOG-033 / BACKLOG-044 | `docs/BACKLOG.md` |
