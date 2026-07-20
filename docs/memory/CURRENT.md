# CURRENT state

**Last updated:** 2026-07-20 (CPOR H2 steward UX parity)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **HEAD** | `995a418` ? CPOR historical steward/progress UX parity |
| **Alembic (DB)** | **`20260720_0073` on cip** (applied + grants) |
| **Next** | Fable VERIFY H2 steward UX ? H3 export round-trip / pivot filters when prioritized |

---

## CPOR historical import

- H1 PASS (Fable): parse/validate/profile + migration
- **H2 API:** pipeline stage ? steward map-token / bulk-map-token ? async apply + progress
- **H2 web UX (`995a418`):** shipment-shaped `CporHistoricalImportJobResolutionSection` (entity tabs, selection, bulk map, drawer, 300ms search); wizard Upload ? async validate progress ? Resolve ? Apply; `cpor_historical_import` progress kind
- cip smoke: job 556 case `H2-SMOKE-556` applied `origin=historical_import`
- Locks: frozen Result; FLAG?BLOCK per case; no claim-evidence fabrication; no auto-create dims

---

## Parked ? DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`
- Resume TRIGGER: Warren asks to finish job 553 steward/apply

---

## Do not

- Push main; auto-create dims; invent waterfall rewrite of settled Results; fabricate claim-evidence from Result totals
