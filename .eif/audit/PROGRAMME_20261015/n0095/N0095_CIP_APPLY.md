# N-0095 cip apply: alias-seal backfill (2026-10-15)

The Amazon keeper is not changed here: Warren picks it in the panel.

- cip before: db cip, customers_real 5038, merged_real 216, customers_all 5181, global_aliases 242, seal_aliases 0, aliases_all 5729, amazon_26_into 299, amazon_299_into None, sellout_299 445, sellout_26 0, cst_299 31, cases_299 15, oc_into None
- dry run:
  ```
  current_database()=cip
  current_database()=cip
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
- apply:
  ```
  current_database()=cip
  current_database()=cip
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
- cip after apply: db cip, customers_real 5038, merged_real 216, customers_all 5181, global_aliases 354, seal_aliases 112, aliases_all 5841, amazon_26_into 299, amazon_299_into None, sellout_299 445, sellout_26 0, cst_299 31, cases_299 15, oc_into None
- dry run again (must plan nothing):
  ```
  current_database()=cip
  current_database()=cip
  {
    "dry_run": true,
    "merged_records": 216,
    "test_fixture_merges_left_untouched": 28,
    "keepers": 180,
    "minted": 0,
    "reassigned": 0,
    "conflicts": 0,
    "skipped": 328
  }
  ```
- OPEN_CHANNEL check:
  ```
  current_database()=cip
  current_database()=cip
  OPEN_CHANNEL id=1 merged_into=None
  records merged into OPEN_CHANNEL: 4
    1152 TMP-CUST-20260607200144-FECF 'Compuspeed LTD'
    4145 TMP-CUST-20260608094305-EB7E 'SYNTECH DISTRIBUTION (PTY) LTD'
    5013 TMP-CUST-20260623161157-CB7F 'SADC Open Channel'
    19 TMP-CUST-20260601135658-8D88 'Open Channel'
  OPEN_CHANNEL is the keeper; nothing to repair
  ```
