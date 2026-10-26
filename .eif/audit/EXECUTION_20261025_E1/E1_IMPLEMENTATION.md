# E1 — governed CPOR filter and total fidelity

Implementation run: `RUN-20261025-N0115-E1-CODEX`; starting product commit
`d069f86c9232a735b87c64bb8f3fe3c7b5916b08`. Bounded correction under N-0115,
not completion of the original node. Acceptance remains pending.

## Canonical path and contract

| Trigger | Route / task | Reader | Transaction |
|---|---|---|---|
| Dashboard/editor query | `/query/execute`, `/query/v2/execute` | a2_cpor → portfolio_intelligence | Request session; read only |
| Explain | `/query/explain`, `/query/v2/explain` | Same validation | No query execution |
| Ad-hoc/saved report export | `/reports/export`, `/reports/saved/{id}/export` | Same v1/governed-v2 engines | Read only |
| Manual/scheduled/import delivery | deliver_saved_report / existing schedule runner | Same engines | Delivery row; no fact writes |
| CPOR portfolio | Existing portfolio endpoint | Same portfolio service, no-argument contract | Existing reader |

No importer, template_slug, entity writer or competing steward buttons applies.
The original programme and existing catalog retain CPOR as all-time governed
metrics at customer, BU or promotion-type grain. Period windows and cross-tabs
remain unavailable; unsupported filters are refused. The existing v2 honours
table already lists exactly customer/BU and therefore needs no change.

The former handler filtered already-aggregated rows. BU at customer grain had no
effect; a nonexistent customer left total 100 despite zero rows. Source pinned
historical replay: `reproduce_original.py` / `reproduced-original.json`. This
replay reads the original handler from Git and mocks only portfolio I/O; it does
not overwrite the previous verifier's evidence. The regression suite was first
written and executed before product corrections: `failed-before.txt`, eight
failures. Its first database failure additionally exposed the separate-session
reader's inability to see the test request's uncommitted cohort.

## Change

Extend the canonical portfolio reader with optional case-tenant/customer and
line-BU scope before rollups. Reuse the request AsyncSession through run_sync,
so its transaction and forced product RLS apply. Preserve the owner surface's
no-argument result. Scoped calls omit the separate incremental summary because
it has a different cohort. No estimates, support amounts, FX conversions,
valuation, VAT, statuses, snapshots or refusal formulas are changed.

The handler validates unknown, malformed, list-valued and conflicting-alias
filters before explain or execution. customer/BU intersections constrain every
supported grain, totals and ratio denominators. Empty matches yield zero support,
null undefined ratios and no grouped rows. Existing row-limit behavior remains
independent of the full-cohort total.

Independent review found a second refusal bypass: blank/null inputs disappeared
from cache keys and collided with warm unfiltered results. Keys now retain those
inputs and use namespace v3, excluding stale pre-fix entries. The final matrix
includes six warmed-cache malformed-filter checks. Review also requested automatic
omission of the unfiltered incremental supplement for all scoped service callers;
that correction preserves the no-argument owner payload.

## Evidence and boundaries

- Real PostgreSQL identity before fixtures: cip_test / cip / 20261023_0048,
  read-only metadata transaction. All fictional fixture data rolls back.
- Three metrics × three advertised grains × six filter scenarios = 54 v1 cases
  and 54 governed-v2 equivalents, plus cache refusals, product-scope intersections,
  XLSX and delivery checks in the database regression.
- Real bearer HTTP integration: two tenants; admin/scoped/empty users; mixed query
  order and cache hits; both query versions; legacy and v2 saved-report XLSX and
  delivery; ad-hoc XLSX/PDF. This is API integration, not browser smoke.
- Focused final root run: 23 passed, one existing query mock warning. Related
  earlier run: 125 passed, one existing warning (before review corrections).
- Full web: 1,139 passed in 218 files. Lint: exit 0, 50 existing warnings.
  Typecheck and isolated Next build: exit 0. No frontend product source changed.
- Initial full API: 3,386 passed / 22 skipped / one known ops_logs streaming timing
  failure under concurrent web/build load. That run predates final cache/supplement
  corrections and is not a final-source full-suite pass. Final-source rerun: **3,387 passed / 22 skipped / 7 existing warnings, exit0**, 531.42 seconds (`full-api-final.txt`).
- A default-output Next build was stopped after identifying its output path;
  completed build used CIP_NEXT_DIST_DIR=.tmp/e1-build. Next's generated changes
  to next-env.d.ts and tsconfig.json were surgically reverted to their entry
  contents. No API/worker service start or restart, production connection,
  migration, deployment, database role/grant or main change occurred.
- Original ledger prefix through 2767 exactly matches the prior verifier's SHA;
  the entry prefix through 2768 is pinned in checkpoint.json. All original 89
  local-only events and inherited verification artifacts remain intact.

Separate review: `RUN-20261025-N0115-E1-VER-ASTRA`, report VERIFY_ASTRA.md and
source SHA manifest. The reviewer was interrupted at a usage limit and resumed; its final bounded verdict is
VERIFIED_WITH_LIMITATIONS, with 11 final focused tests and all ten source hashes matched. Runtime capabilities remain
unverified, and neither model invocation separation nor this bounded review
alone establishes overall R3. Original N-0115 model/calendar/configuration/
calculation/parity/performance requirements remain open. E3 must still investigate
background recipient policy and pooled tenant behavior; E1's explicit case tenant
predicate is not proof of that entire workflow.

Next executable unit after this tested, persisted checkpoint: E2 common XLSX
literal safety, then E3 background scope and E4 saved-query fidelity. Original
frontier and acceptance matrix are preserved; no scope reductions are accepted.
