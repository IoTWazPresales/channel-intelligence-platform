# CURRENT state

**Last updated:** 2026-08-12 (CPOR payment evidence + Cases shell)

**Branch:** `feat/cpor-payment-evidence` (from main after #30/#31)

**Alembic on cip:** `20260811_0012` — **code head `20260812_0013` (NOT applied — await Warren upgrade)**

## Arc progress

| Unit | Status |
|---|---|
| 0–3 | Done on main |
| 5 CST hist | **Merged** #30 → main |
| 7 BACKLOG-068 | **Merged** onto main (PR #31 retarget miss; fixed via merge commit `0cf0c6c`) |
| 8 Demo/P2 | Pending after payment evidence |
| P5 payment/CN | **In progress** — generic evidence model + Cases shell |
| 9–10 | Blocked (094 / 092 full recon) |

## This unit (locks)

- Generic `cpor_payment_evidence` (not Ken-shaped schema); ASUS Pending Report = one profile
- Canonical: case ID, CN ID, case_status_raw (evidence-only), payment status/date, amount+currency, customer, distributor, description
- Steward may create shell cases; file case status never overwrites CIP workflow
- CPOR Cases list → `MasterDataGridShell` (BACKLOG-079 fold-in)

## Next

1. **Warren approve** `alembic upgrade` → `20260812_0013` on `cip`
2. Browser smoke: Cases shell + payment import Ken file + case Payments tab
3. Unit 8 Demo/P2 gate

**Env:** local Windows.
