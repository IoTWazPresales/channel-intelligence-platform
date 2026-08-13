# CURRENT state

**Last updated:** 2026-08-13 (Unit 13 BACKLOG-092 — Opus VERIFY PASS after D-01)

**Branch:** `feat/unit13-cpor-payment-recon` (from `feat/p5-residual` @ `53361c3`) 

**Alembic on cip:** `20260812_0014`

## Arc progress

| Unit | Status |
|---|---|
| 8 Demo/P2 | **Merged** PR #36 → `main` |
| 11 Import parity | **Merged** PR #37 → `main` (`4aa538a`) |
| 12 P6 light | Export sheet Settings shipped in PR #37 |
| P5 residual | **Pushed** `feat/p5-residual` @ `53361c3` — not yet merged to `main` |
| **13** | **VERIFY PASS** (Opus) — BACKLOG-092 paid vs owed recon; D-01 superseded_by_case_id |
| **14** | Queued — BACKLOG-131 P3 widget canvas |
| **15** | Queued — B1 history forecast + BACKLOG-094 intake-weighted MAC + editable planner |
| P2 hosting | Stay local |
| P6 | Wait for a second company |

Plan: `.tmp/ARC_UNITS_13_15_PLAN.md`

## This branch

- Recon service `payment_recon.py`: owed = Σ line `ttl_support` (never qty×support); paid = evidence status paid/processed/closed; FX FLAG not converted
- `GET /cpor/cases/{id}/payment-recon`; Cases list owed/paid/outstanding/recon columns
- Case tab **Payments / recon** summary chips + evidence grid
- Optional mapped `owed_amount_file` in profile (shown vs CIP owed)

- Case 293 `C26649381`: owed 68421.48 ZAR; paid 0 ZAR; USD CNs 116.96 FLAG `currency_mismatch` / `fx_undeclared` (not converted)

## Locks 2026-08-13

- 094 MAC = SOH + in-window intake, weighted; units = history benchmark; all planner fields editable
- Target cover = **weeks per customer**
- No forecast file — CIP computes from history
- Generic lineup export OK if required column layout via profile
- 092 owed (interim) = approved `ttl_support`; paid = mapped evidence; never invent owed from qty×support

## Next

1. Unit 14 BACKLOG-131 P3 widget canvas — **new chat / new branch** (do not start here)
2. Warren: merge/promote `feat/p5-residual` or this stacked Unit 13 branch
3. Do not re-ingest job 978 / do not re-audit Takealot REST fetch

**Env:** local Windows. Web `:3000` + API `:8001`.
