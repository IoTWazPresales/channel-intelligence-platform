# CURRENT state

**Last updated:** 2026-08-04 (9→122 / f3 unit STOP — no PO-link carry)

**Branch:** `main`

**Alembic:** `20260802_0009` · no migration this unit

## Done / STOP

- **A2 STOP:** supersession does **not** carry `commercial_lineup_case_po` (only status + `superseded_by_case_id`). Case 9 has **28** links; 122 has **0**. Did **not** supersede 9; did **not** apply f3. D-031 recorded.
- **A6:** f3 still applicable on job 752 as `f3:NB:NB:unknown` / `period_signal_conflict`; supported path = `manual_period_label` steward override → 2025 Q4. Blocked only by unit stop gate (paired with A2).
- **Phase D (report):** 33 competing PO norms vs shipment∩lineup products → **25** multi-BU legitimate, **7** cross-period, **1** same-BU same-period (`PURMIDR26009979`). Detector does not consult shipment → BACKLOG-119. Detector **not** changed.
- Cases **7** / **90** / **9** / **122** unchanged. Case count **34**. Linked distinct still **308**.

## Next

1. **BACKLOG-118** — implement PO-link carry on supersession (blocks D2).
2. Resume: soft-supersede **9→122** with carry; apply **f3** as 2025 Q4 via manual tier.
3. Residual genuine: 7 cross-period + `PURMIDR26009979` (post-122 supersession may simplify).

**Env:** local Windows. `cip`.
