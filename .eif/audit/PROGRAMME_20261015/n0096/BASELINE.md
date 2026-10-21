# N-0096 baseline (HEAD ebf6f9ea, before this session's test fixes)

- Full API pytest on cip_test: 20 failed, 34 errors, 2877 passed, 57 skipped (run 1).
- Cause of most errors: test_cpor_settle_confirm_clone.py and test_lineup_bulk_backfill_apply_integration.py set DATABASE_URL* in os.environ for
  databases that no longer exist (cip_ns4_settle_clone, cip_bulk_smoke) and never restored them; later DB tests then failed to connect.
- Failures by class: stale test (promo plan builder x4, column grain, lineup x2, product usage delete count, open channel x2, resolved entities,
  mailer, RBAC x3, lineage and parity head pins); named database missing (settle clone, bulk smoke, 0064 smoke, distributor-as-customer x3,
  po-link); product inconsistency (RLS policy form on two N-0110 tables).
- Full web vitest: 8 failed in 3 files of 183 (copy changes).
