# Current state

**Last updated:** 2026-06-23 (Plan C shipment steward parity — cloud agent)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `cursor/cloud-agent-1782231728131-em82n` (from `feat/dsi-async-topology`) |
| **HEAD (snapshot)** | pending push — Plan C shipment steward parity |
| **PR** | Open after push |
| **Alembic (code)** | `20260609_0049` (`task_run` ledger) |
| **Alembic (DB)** | `20260609_0049` (cloud Docker `cip`) |

---

## What is working (Plan C shipment)

- **ShipmentImportJobResolutionSection** — shared `ImportStewardCandidateWorkspace`, entity tabs, paginated list, resolution plan toolbar (refresh / apply all ready / apply selected).
- **Shipment resolution plan API** — `POST .../resolution-plan/compute-async`, `/effective`, `/apply-async` on `/api/v1/shipment-evidence/` (not `/mappings/`).
- **Paginated candidates** — `GET .../mapping-candidates/paginated` + `tab-counts`.
- **Alias scope** — `shipment_customer_alias_scope.py` (0048 ON CONFLICT DO NOTHING) wired into steward customer map.
- **Legacy retained** — full `ShipmentEntityStewardPanelLegacy` via dialog + all existing `/shipment-evidence/` bulk/single-row endpoints.
- **Operator docs** — `docs/SHIPMENT_EVIDENCE_OPERATOR.md`; **Plan D design** — `docs/SHIPMENT_BITEMPORAL_PLAN_D.md` (BACKLOG-033, no migration).

---

## In progress / not proven live

- Plan C browser soak on large ACZA jobs (paginated list + plan apply).
- BACKLOG-007 post-validate re-map spike (notes only — not implemented).

---

## Next (recommended)

1. Merge PR after review; Warren smoke on shipment import wizard + `/admin/shipment-evidence`.
2. BACKLOG-033 bitemporal program when weekly shipment cadence triggers.
3. DSI job #96 / Res Q IT soak on local `cip`.

---

## Blockers requiring Warren

- Promotion to `main` — explicit instruction only.
- **Do not commit** `.env`, dumps, `celerybeat-schedule.*`.

---

## Key references

| Topic | Doc |
|-------|-----|
| Operator (evidence vs fact) | `docs/SHIPMENT_EVIDENCE_OPERATOR.md` |
| Plan D (bitemporal) | `docs/SHIPMENT_BITEMPORAL_PLAN_D.md` |
| BACKLOG-044 | `docs/BACKLOG.md` |
| Roadmap | `docs/memory/ROADMAP.md` |
