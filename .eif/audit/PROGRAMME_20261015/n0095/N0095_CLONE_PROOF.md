# N-0095 clone proof (2026-10-15)

- source cip: db cip, customers_real 5038, merged_real 216, customers_all 5181, global_aliases 242, seal_aliases 0, aliases_all 5729, amazon_26_into 299, amazon_299_into None, sellout_299 445, sellout_26 0, cst_299 31, cases_299 15, oc_into None
- clone cip_n0095 made from cip with pg_dump/pg_restore
- clone before: db cip_n0095, customers_real 5038, merged_real 216, customers_all 5181, global_aliases 242, seal_aliases 0, aliases_all 5729, amazon_26_into 299, amazon_299_into None, sellout_299 445, sellout_26 0, cst_299 31, cases_299 15, oc_into None

## Alias-seal backfill on the clone
- dry run:
  ```
  current_database()=cip_n0095
  current_database()=cip_n0095
  {
    "dry_run": true,
    "merged_records": 216,
    "test_fixture_merges_left_untouched": 28,
    "keepers": 180,
    "minted": 112,
    "reassigned": 0,
    "conflicts": 0,
    "skipped": 216
  }
  ```
- clone after dry run (unchanged): db cip_n0095, customers_real 5038, merged_real 216, customers_all 5181, global_aliases 242, seal_aliases 0, aliases_all 5729, amazon_26_into 299, amazon_299_into None, sellout_299 445, sellout_26 0, cst_299 31, cases_299 15, oc_into None
- apply:
  ```
  current_database()=cip_n0095
  current_database()=cip_n0095
  {
    "dry_run": false,
    "merged_records": 216,
    "test_fixture_merges_left_untouched": 28,
    "keepers": 180,
    "minted": 112,
    "reassigned": 0,
    "conflicts": 0,
    "skipped": 216
  }
  ```
- clone after apply: db cip_n0095, customers_real 5038, merged_real 216, customers_all 5181, global_aliases 354, seal_aliases 112, aliases_all 5841, amazon_26_into 299, amazon_299_into None, sellout_299 445, sellout_26 0, cst_299 31, cases_299 15, oc_into None
- apply again (must mint nothing):
  ```
  current_database()=cip_n0095
  current_database()=cip_n0095
  {
    "dry_run": false,
    "merged_records": 216,
    "test_fixture_merges_left_untouched": 28,
    "keepers": 180,
    "minted": 0,
    "reassigned": 0,
    "conflicts": 0,
    "skipped": 328
  }
  ```
- clone after second apply: db cip_n0095, customers_real 5038, merged_real 216, customers_all 5181, global_aliases 354, seal_aliases 112, aliases_all 5841, amazon_26_into 299, amazon_299_into None, sellout_299 445, sellout_26 0, cst_299 31, cases_299 15, oc_into None
- second apply minted nothing and alias count unchanged: True
- wrong --expect-db is refused:
  exit 2: ["refused: --apply needs --expect-db 'cip_n0095' (got 'cip')"]

## OPEN_CHANNEL repair check on the clone
  ```
  current_database()=cip_n0095
  current_database()=cip_n0095
  OPEN_CHANNEL id=1 merged_into=None
  records merged into OPEN_CHANNEL: 4
    1152 TMP-CUST-20260607200144-FECF 'Compuspeed LTD'
    4145 TMP-CUST-20260608094305-EB7E 'SYNTECH DISTRIBUTION (PTY) LTD'
    5013 TMP-CUST-20260623161157-CB7F 'SADC Open Channel'
    19 TMP-CUST-20260601135658-8D88 'Open Channel'
  OPEN_CHANNEL is the keeper; nothing to repair
  ```

## Amazon keeper change on the clone only (Warren picks on cip)
  ```
  current_database()=cip_n0095
  'Amazon' -> (299, ['customer_resolved_alias'])
  'AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)' -> (299, ['customer_resolved_alias'])
  'amazon' -> (299, ['customer_resolved_alias'])
  ```
  ```
  current_database()=cip_n0095
  current_database()=cip_n0095
  preview rows_to_move 10786 other [] seal 2 conflicts 0
  confirm rows_moved 10786 minted 2 reassigned 0 conflicts 0
  ```
- clone after 299 -> 26: db cip_n0095, customers_real 5038, merged_real 216, customers_all 5181, global_aliases 356, seal_aliases 114, aliases_all 5843, amazon_26_into None, amazon_299_into 26, sellout_299 0, sellout_26 445, cst_299 0, cases_299 0, oc_into None
  ```
  current_database()=cip_n0095
  'Amazon' -> (26, ['customer_resolved_alias'])
  'AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)' -> (26, ['customer_resolved_alias'])
  'CUST-000260' -> (26, ['customer_resolved_code'])
  ```
  ```
  current_database()=cip_n0095
  current_database()=cip_n0095
  preview rows_to_move 10788 other [] seal 0 conflicts 0
  confirm rows_moved 10788 minted 0 reassigned 0 conflicts 0
  ```
- clone after 26 -> 299: db cip_n0095, customers_real 5038, merged_real 216, customers_all 5181, global_aliases 356, seal_aliases 114, aliases_all 5843, amazon_26_into 299, amazon_299_into None, sellout_299 445, sellout_26 0, cst_299 31, cases_299 15, oc_into None
  ```
  current_database()=cip_n0095
  'Amazon' -> (299, ['customer_resolved_alias'])
  'AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)' -> (299, ['customer_resolved_alias'])
  ```
- swap moved every sell-out row to 26: True; swap back restored 299 with the same counts: True
- clone dropped; dump removed

CLONE_PROOF PASS
