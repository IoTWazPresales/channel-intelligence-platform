# N-0079 ledger proof — 2026-10-12

Clone `cip_n0079` was created from template `cip`. Migration `20261012_0033` was applied on the clone first.

Historical settled load on the clone: written 435, skipped because already present 0, skipped because `ttl_result_usd` is null 4. A second load wrote 0 and skipped 435. Update and delete, run as the table owner, raised append-only. The row count stayed 435.

The same migration was then applied on `cip`. `current_database()` was `cip`. Revision `20261012_0033`. The historical load wrote 435, skipped 4 with no result, and a second load wrote 0.

The Budgets page, signed in as Local Admin, shows product line by quarter. NB 2023Q2 consumed 39171.3026. Remaining is negative because these historical consume rows have no reserve. Clicking that quarter opens entries of type consume, source `historical_import`.

The page does not show a pending column or a cap column. The node stays open for that, and for the rest of D-0059 (campaign and non-campaign view, unplanned-spend and unknown-quarter buckets, an admin cap control). Caps already flag and do not block a case approval.
