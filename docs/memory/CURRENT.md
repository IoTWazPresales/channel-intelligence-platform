# Current state

**Last updated:** 2026-07-12 (Wave 2 Products+CPOR — pending Fable VERIFY)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | see git (Wave 2 commit) |
| **PR** | Not opened |
| **Alembic (DB)** | **`20260710_0072`** on cip — no new migrations |
| **Fable** | Wave 1 PASS; Wave 2 VERIFY pending |

---

## Wave 2 (Products richer filters + CPOR list parity)

| Item | Status |
|------|--------|
| Products: BU / product line / series / spec_search + retired dates | implemented |
| Products: `product_spec_*` on list rows | implemented |
| CPOR: wire `q` + `customer_id` | implemented |
| CPOR: standalone MasterColumnPickerDialog | implemented |
| No MasterDataGridShell on CPOR | honored |

Wave 1 remain PASS @ `70aab64` / docs `d54639b`.

---

## Next

1. Fable VERIFY Wave 2
2. On PASS: Wave 3 CST empty-state copy (separate unit)
