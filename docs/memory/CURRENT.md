# Current state

**Last updated:** 2026-06-24 (shipment wizard + steward DSI parity — all phases)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-async-topology` |
| **HEAD (snapshot)** | uncommitted — shipment wizard/steward parity pass |
| **PR** | None open — push then open PR |
| **Alembic (code)** | `20260623_0050` |
| **Alembic (DB)** | **`20260623_0050`** on local `cip` |

---

## What is working

### Shipment import wizard (DSI-aligned — 2026-06-24)
- **7 steps:** upload → column mapping → validate & resolve → apply (matches DSI mental model).
- **Apply step:** `ImportJobLoadedSuccessCallout` when job stage `loaded` (revisit + post-apply).
- **`shipmentWizardActiveStepFromServer`** — revisit jobs land on correct step.
- **Validate progress** — re-validate on `validated` jobs shows progress (`status=running` no longer treated as finished).
- **Steward grid** — `filterShipmentStewardCandidates` fixes empty table (`shipment_distributor` entity types).
- **`ShipmentImportJobResolutionSection`** — `DsiEntityTabsBar` parity (`ShipmentEntityTabsBar`), plan toolbar, bulk map/provisional, server re-validate, plan-driven columns.

### Plan C / D / BACKLOG-007 (prior)
- Resolution plan API, paginated candidates, bitemporal D1–D3 (flags off), post-validate re-map + orphan purge.

---

## In progress / not proven live

- Browser soak on job #147 / ACZA backfill after wizard split.
- Plan D D4–D5; bitemporal flags still off by default.

---

## Next (recommended)

1. **Smoke:** shipment wizard end-to-end on local (upload → map → validate → steward → apply).
2. **ACZA backfill** per `docs/SHIPMENT_EVIDENCE_OPERATOR.md`.
3. `git push origin feat/dsi-async-topology` + open PR when ready.

---

## Key references

| Topic | Doc |
|-------|-----|
| Import contract (shipment row updated) | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` |
| Operator | `docs/SHIPMENT_EVIDENCE_OPERATOR.md` |
| Plan D | `docs/SHIPMENT_BITEMPORAL_PLAN_D.md` |
