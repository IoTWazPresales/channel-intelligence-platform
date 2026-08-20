# CURRENT state

**Last updated:** 2026-08-20 (steward + CPOR queue depth)

**Branch:** `feat/steward-queue-depth`

**Last content pin:** `0a649df` (main at branch-off) — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0019` (`20260818_0019_shipping_mailer_recipient.py`)

**Alembic on cip:** `20260818_0019` (already stamped; no upgrade of cip this session)

**Alembic on cip_test:** `20260818_0018` (OWNER cip)

## On this branch

- Read-only queue script: `apps/api/scripts/ops/steward_queue_depth.py` (launcher `scripts/ops/steward_queue_depth.py`). SELECT only; refuses any DB other than `cip`.
- **RBAC program CLOSED at R1–R1d** (on main, inherited). No Role enum expansion. No `require_roles` on CPOR (R2). BACKLOG-136 / BACKLOG-141 parked.
- API test pin: `apps/api/tests/conftest.py` `setdefault("CIP_AUTH_MODE", "stub")`. Do not edit `.env` or `config.py` default.
- BACKLOG-143 amended: `cip_test` is real test infra (do not drop); shipping-mailer already on main; `.tmp_lf_rerun.txt` deleted; `cip_merged_leftover_repair` 2325 MB **not dropped**.
- BACKLOG-144: `cip_test` seed gap for lineup distributor-as-customer tests.

## Queue depth on cip (2026-08-20, read-only)

| Queue | Count |
|---|---|
| Live-job mapping candidates | customer_dealer needs_review **409**; product_identifier needs_review **455**, ignored **20** |
| Lineup `distributor_attribution_status` | NULL 2414; token_proposed 1035; steward_set 2; shipment_confirmed 3 |
| TMP-CUST open (losers excluded) | **4795** (216 merged losers excluded) |
| TMP-DIST open | **25** |
| Mint setting | 1 row (`prefix=CUST`, `next_seq=1`) — exists ≠ production mint (do not amend BACKLOG-140) |
| DSI product catalogue gap (worklist grain) | **1009** (`needs_review` 989; live jobs 475) |
| CST | 86 jobs / 92 raw files; **no stub flag** on `raw_file_metadata`; slots received=36 |
| Merged leftovers | customer **0**; distributor **0** |
| CPOR `status` | cancelled 23; draft 2; ended 76; settled 209 |
| CPOR `workflow_status` | cancelled 21; draft 3; ended 77; settled 209 |
| CPOR status≠workflow | **2** (BACKLOG-139; spec §9 said ~4) |
| Past `window_end` not settled/cancelled | **74** |
| `superseded_by_case_id` set | **0** (BACKLOG-138) |
| CPOR cases on TMP-CUST | **308** (BACKLOG-140) |
| `cpor_case_event.actor` NULL | **4** |

Hint mismatches (not missing tables): attribution lives on `commercial_lineup_line`, not the case; CST has no stub/hydrated column.

## Next

CPOR settlement / MAC / line-windows from `docs/CPOR_SETTLEMENT_SPEC.md` §8 and BACKLOG-135–140, using the queue numbers above — **74** ended-window cases and **2** status/workflow drifted rows are the live settlement load; **308** TMP-CUST cases and mint `next_seq=1` sit behind BACKLOG-140 (do not mint from a docs/queue unit). Merge `feat/steward-queue-depth` when Warren says. **`cip_test` is real test infra — do not drop.** Clone `cip_merged_leftover_repair` (2325 MB) can still be dropped when convenient.

**Env:** local Windows. Web `:3000` + API `:8001`. `cip_auth_mode` default in `config.py` is `stub`.
