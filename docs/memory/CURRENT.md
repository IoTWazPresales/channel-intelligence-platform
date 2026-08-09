# CURRENT state

**Last updated:** 2026-08-09 (wide-week unpivot + PR #26 + intel backlog)

**Branch:** `feat/p4-cst-six-customer-shapes` → **PR #26** (not merged — wait for promote)

**Alembic on cip:** `20260808_0011` (head)

## Locked rules

- CST unmappable → Ignore → catalogue gaps (`source=cst`). Never auto-create PM.
- Game 2026 ≠ new structure_type — steward column map + header fix only.
- P5: enable live fetch now; ≥2 weeks obs gate is for **intelligence v1** only (BACKLOG-130).

## Proven this branch

| Item | Proof |
|---|---|
| P4 / Unit E / Game headers | prior commits |
| Game wide-week unpivot | dual-header `Sales U TY`×N → one staging row per product×week (unit tests) |
| P5 auto-finder + live fetch + Amazon soak | 51 listings / 52 obs |
| Takealot/Evetech listing_seed | `layout_family` defaults in `cst_d1` + cip `customer_report_config` patched; **re-ingest blocked** (upload files missing locally) |
| Intelligence v1 | **not started** — BACKLOG-130 TRIGGER (≥14d obs) |

## Next

1. Warren: review/merge **PR #26** when ready to promote
2. Re-upload Takealot/Evetech CST → confirm-suggested (Evetech URLs still human-paste)
3. Accrue listing obs (optional worker/beat) until BACKLOG-130 fires
4. Optional Lane X when TRIGGER fires

**Env:** local Windows. `cip` @ `20260808_0011`.
