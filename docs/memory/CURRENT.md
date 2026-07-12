# Current state

**Last updated:** 2026-07-12 (Wave 1 Fable VERIFY **PASS** @ `70aab64`)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | `70aab64` pushed |
| **PR** | Not opened |
| **Alembic (DB)** | **`20260710_0072`** on cip — no new migrations |
| **Fable** | Wave 1 **VERDICT: PASS** |

---

## Wave 1 (ops grid parity — Channel Ops + PVE Apply) — PASS

| Item | Status |
|------|--------|
| Page cohort filters ? summary + weekly chart | shipped `70aab64` |
| Inventory page/page_size + empty UX | shipped |
| Movements date filters | shipped |
| Sell-out: `spec_search` + spec display columns | shipped |
| PVE draft From/To/BU + Apply | shipped |
| D1–D5 CONSULT defects | fixed + verified |

**FLAG (deferred):** BU filter on derived channel stock / WoC / reporting / customers.

Audit-gap tip before Wave 1: `b621a99`.

---

## Next

1. **Wave 2** (separate unit/PR after you say proceed): Products richer filters + CPOR search/customer + column picker — prompt in `.tmp/ops_grid_wave1_consult_fable_response.md` / VERIFY response
2. Wave 3: CST empty-state copy
3. Manual browser soak of Wave 1 when convenient
