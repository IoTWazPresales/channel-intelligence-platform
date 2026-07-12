# Current state

**Last updated:** 2026-07-12 (Ops grid Waves 1–3 complete — Fable PASS)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | see git (`7058822` Wave 3 tip when PASS recorded) |
| **PR** | Not opened — ready when Warren says |
| **Alembic (DB)** | **`20260710_0072`** |
| **Fable** | Waves 1–3 **PASS** (queue empty for ops grid parity) |

---

## What works (ops grid waves)

- **Wave 1:** Channel Ops cohort filters + inventory paging + sell-out `spec_search` + PVE Apply (`70aab64`)
- **Wave 2:** Products BU/line/series/spec_search; CPOR q/customer + column picker (`6609ad2`)
- **Wave 3:** CST actionable empty-states + guide; CPOR `customer_id` hydrate (`7058822`)

## Deferred (FLAG — not this PR)

- BU filter on derived stock / WoC / reporting / customers
- AG Grid swap on Channel Ops (still EnterpriseDataGrid bar)

---

## Next

1. Open PR for Waves 1–3 when Warren says (or soak / other TRIGGER)
2. Do **not** start a new ops-grid theme without explicit proceed
