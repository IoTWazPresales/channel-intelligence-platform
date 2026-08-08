# CURRENT state

**Last updated:** 2026-08-08 (CI alembic tip tracks ScriptDirectory head)

**Branch:** `fix/ci-alembic-tip-0010`

**Alembic:** `20260807_0010`

## Done

- PR #23/#24 on main (B2 + B4)
- CI tip assert no longer hardcodes `20260802_0009` — equals sole script head; also asserts `distributor_attribution_status` column

## Outstanding (priority order — see chat)

1. Soft data gaps for B-lane usefulness (assumptions seed, CST load)
2. Lane X / steward retrofit continuous
3. Parked TRIGGERs only when fired (068, 089, 092, 123, …)
4. Full ASUS workbook parity only if tenant rejects XLSX on-ramp

## Next

Merge this CI fix → main, then soft data / Lane X.

**Env:** local Windows. `cip` @ `20260807_0010`.
