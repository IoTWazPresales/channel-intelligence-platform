# N-0095 baseline (observed 2026-10-15, tree 0506c9ed)

- `confirm_customer_full_merge_sync` repointed every FK from each loser to the keeper and set
  `merged_into_customer_id`; it minted no alias, wrote no audit event, and accepted only
  name-similarity keys. The July 2026 seal (`467bc89e`) and related-name worklist (`792a9db4`)
  were parked off-tree (BACKLOG-081 / 083); `alias_seal` was absent from the tree.
- Resolvers already chase `merged_into_customer_id`: DSI DB path (`_resolve_customer`,
  `_alias_customer_id`) and cache (`_build_resolution_cache`), shipment
  (`resolve_shipment_customer_id_from_token`, `apply_resolved_entities_to_line`), lineup
  (`index_by_code_and_name`, alias map with redirect), sell-through (`resolve_customer_id_for_job`).
  Covered only by unit tests with stand-in objects (`test_merge_redirect.py`), not on a database.
- cip: 5,181 customers (5,038 with real codes), 244 merged (216 real, 28 test fixtures),
  242 approved global aliases, 0 rows noted as merge seals. OPEN_CHANNEL id 1 is the keeper;
  4 records are merged into it (19 "Open Channel", 5013 "SADC Open Channel", 1152 "Compuspeed LTD",
  4145 "SYNTECH DISTRIBUTION (PTY) LTD").
- Amazon: 26 "Amazon" (TMP-CUST, from shipment job 34) was merged into 299 "AMAZON COMMERCIAL
  SERVICES (SOUTH AFRICA)" (CUST-000260) on 2026-07-11 (`key=related:amazon`, note "11"). All rows
  are on 299 (sell-out 445, sell-through 31, cases 15, shipments 235, aliases 6 incl. global
  `amazon` -> 299). Which rows came from 26 was not recorded.
- cip_test: `customer_source_token_alias` has only its primary-key index; cip also has the
  approved-scope unique index and five lookup indexes (schema drift on the test database).
- Customer merge preview/confirm endpoints have no role gate beyond sign-in.
