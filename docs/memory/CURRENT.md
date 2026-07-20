# CURRENT state

**Last updated:** 2026-07-20 (Date-chip parity + layout-coalesce U6 + browser smoke mid-steward)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-unified-multifile` |
| **HEAD** | uncommitted: date-chip + layout-coalesce + sheet exclude |
| **Alembic (DB)** | **`20260710_0072`** |
| **Consultant** | Fable CONSULT READY U6 (layout-coalesce); Cursor implementing + browser smoke |

---

## Shipped / in flight

- **Date chip:** `dsiMappingRequiredGroupsFromDraft` — inventory Date shows `OK (file stamp)` when SOH + period stamps (parity with Dist)
- **U6 layout-coalesce:** presentation tabs by `layout_signature`; fan-out edits; detach/map separately; storage stays per `file::sheet`
- **Sheet exclude:** `dsi_excluded_mapping_keys` on same exclusions endpoint (undateable sheets without killing whole file)
- **Smoke job 553:** 9-file weekly batch validated — Dist stamps OK (0 distributor candidates); layout tabs collapsed; steward in progress (customers/products)

---

## Smoke proven (job 553)

- Preview: 9 files → 1 job
- After stamps: Dist ✓ · Period ✓ all files
- Layouts: ~4 tabs (MUSTEK+some PINNACLE sellout merged; inventaries; PINNACLE sellout pair; SOH)
- Excluded: `Inventory-PINNACLE-…::Sell out` (no date columns)
- Validate: 2187 rows; 1532 steward-map; 184 blank-product; 358 customers / 276 products open
- Date chip: `OK (file stamp)` on SOH layout

---

## Next

- Finish steward on job 553 (customers then products → revalidate → apply)
- UI: Exclude sheet control on layout tab (API already accepts keys)
- BACKLOG: cross-batch layout templates; fuzzy layouts; per-member stamp chips in group
- Commit + push when Warren asks (or after steward soak)
