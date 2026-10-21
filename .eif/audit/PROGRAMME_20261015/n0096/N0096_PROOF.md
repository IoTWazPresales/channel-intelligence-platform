# N-0096 proof (2026-10-15, branch feat/ns-2-brief-nav-collapse)

## Suite counts
- Full API pytest on cip_test, fresh run (current_database() printed cip_test): 2977 passed, 21 skipped, 0 failed (275 s).
  Earlier runs: 2877 passed, 20 failed, 34 errors (baseline); 2945 passed, 28 errors (after most fixes); 2973 passed, 0 failed.
- Full web vitest: run 1 was 852 passed, 8 failed (stale copy expectations, fixed in fd64d0a7). Two later full runs were stopped (memory pressure, then the session ended).
  FINAL: every test file, in 4 batches with 2 forks (vitest 2.1.9): 41 files / 248 tests, 47 / 202, 44 / 176, 51 / 234 = 183 files, 860 tests, 860 passed, 0 failed.
  The file list is git ls-files over src/**/*.test.{ts,tsx} (183 files, the same count as on disk); no file name is a substring of another.
- Web tsc --noEmit: exit 0. eslint on the 3 changed web test files: 0 errors, 1 existing warning (products/page.test.tsx:129).

## Commits (feat/ns-2-brief-nav-collapse)
4c25474e FX date = approval date (D-0093) with tests; 7d2e9f7c clone fixtures no longer leak env; 6047f6c2 stale unit tests;
70d0fc93 distributor-as-customer tests self-seed; c3dba532 RLS migration 20261015_0040 + parity test; fd64d0a7 web tests;
708e1fff Takealot week-shape test; cb989dc0 docs.

## RLS migration 20261015_0040
Clone proof on cip_n0096 (dropped): see N0096_RLS_CLONE_PROOF.md. Applied to cip (current_database() printed cip; rev 0039 -> 0040;
701 positions and 390 superseded rows unchanged) and to cip_test. Parity test passes with no exemption.
