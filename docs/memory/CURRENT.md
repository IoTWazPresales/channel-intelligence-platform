# CURRENT state

**Last updated:** 2026-08-10 (BACKLOG-010 PAV truncate on cip)

**Branch:** `ops/backlog-010-drop-pav` (from `main` @ `5e4a84c`)

**Alembic on cip:** `20260808_0011` (head)

## Locked rules

- CST unmappable → Ignore → catalogue gaps (`source=cst`). Never auto-create PM.
- Game ≠ new structure_type — dual_header + wide-week unpivot.
- Listing↔CPOR activation = point-in-time vs `cpor_case_line.srp`; `no_case_detected` when none.
- B2 export sheet titles = **tenant profile** (not OEM hardcoding).
- A2-X incremental unit cost = baseline FLAG-first (not A2-06 rename).
- Specs canonical on `dim_product.specs_json`; PAV legacy off (`PM_WRITE_LEGACY_EAV` default false).

## Just done

- **BACKLOG-010:** `cip.product_attribute_value` count was already **0**; snapshot + idempotent `TRUNCATE` via `scripts/ops/drop_legacy_product_attribute_value.py`. Schema kept for escape hatch.

## Warren decisions still required

- **Q-013** — PURMIDR25005866: pick case 90 vs 127.
- **Q-014** — PURMIDR26009979: pick among 121 / 122 / 128.

## Next (TRIGGER-ready)

1. **P5 residual** — upload CPOR → re-poll activation; Takealot SPA/API fetch.
2. CST historical backfill (after forward soak trusted).
3. **BACKLOG-094** — MAC + price-delta once formulas locked.
4. Demo gate / P2 second-user landing; backup restore soak.
5. **BACKLOG-068** landed-quarter lens when Shipping prioritizes.
6. PO residual triage after Q-013/Q-014 answers.
7. P6 second-tenant config-only onboard.

**Env:** local Windows. `cip` @ `20260808_0011`.
