# CURRENT state

**Last updated:** 2026-07-20 (CPOR H2 steward + async apply)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **HEAD** | (H2 commit pending / see git) |
| **Alembic (DB)** | **`20260720_0073` on cip** (applied + grants) |
| **Next** | Fable VERIFY H2 ? H3 export round-trip / pivot filters when prioritized |

---

## CPOR historical import

- H1 PASS (Fable): parse/validate/profile + migration
- **H2 shipped:** pipeline stage ? steward map-token ? async `imports.cpor_historical_apply`; wizard at `/commercial-planner/cpor-cases/historical-import`; shared `ImportStewardCandidateWorkspace` + `CanonicalColumnMappingPanel`
- cip smoke: job 556 case `H2-SMOKE-556` applied `origin=historical_import`, 1 line, `historical_import` event
- Locks: frozen Result; FLAG?BLOCK per case; no claim-evidence fabrication; no auto-create dims

---

## Parked ? DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`
- Resume TRIGGER: Warren asks to finish job 553 steward/apply

---

## Do not

- Push main; auto-create dims; invent waterfall rewrite of settled Results; fabricate claim-evidence from Result totals
