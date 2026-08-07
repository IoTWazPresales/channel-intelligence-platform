# CURRENT state

**Last updated:** 2026-08-07 (PROGRAM-A Unit 6c — BACKLOG-112 steward-complete)

**Branch:** `feat/unit6c-backlog-112-closeout` (from `main` @ `81524d5`)

**Alembic:** `20260802_0009` (unchanged — no migration)

## Done

- **Unit 6c / BACKLOG-112 closed steward-complete** (D-038 / D-039): distributor-token
  classifier (exact + structured strip) dual-writes OPEN_CHANNEL + `line.distributor_id`
  in one txn; W5 ship-only never preselected; W6 product isolation; W7 audit provenance;
  free picker + `exclude_prefix=unit6b-`; worklist ~285ms (was ~2092ms baseline).
- W4 false stamps revoked+restamped on cip: `sadc - compuspeed`→OC+Compuspeed(12);
  `mitsumi distribution`→OC+Mitsumi(22). D4 also: `mitsumi`, `dcc`, `sadc - dcc`,
  `channel syntech`.
- Clone C1–C9 PASS on `cip_unit6c_smoke`; cip D1–D7 PASS (cases/links unchanged;
  protected 7/90/122/145 status+line+po counts stable; case 122 `n_dist` 43→51 expected).

## Next

1. **Free-picker residual** (not 112): `jd furn`, `pick & pay`, `sadc - superdisti`,
   `sadc homeless`, `smd`, `88` — steward free pick or BACKLOG-126 masters.
2. **BACKLOG-124** — empty_token (~962 null-customer lines scanned; empty bucket remains).
3. **BACKLOG-125** — distributor-as-customer masters (E12 / syntech→4145).
4. **BACKLOG-123** — promote/merge → ResolutionWorklist (parked; opts.target PROVEN).
5. Roadmap A1∥A2∥A3 only after Warren confirms 124 handling (ship or re-park).

**Env:** local Windows. `cip`. Disposable clone `cip_unit6c_smoke` may be dropped.
