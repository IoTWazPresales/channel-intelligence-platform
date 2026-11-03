# 2c: Would the existing decision-reuse rule clear the old needs_review rows? (read-only)

**Result.** There are 3,264 `needs_review` candidates. The only reuse rule in the importer is the shipment one, and it runs only when the stored candidate is already tagged as an approved alias. On the stored rows that admits 47 customer candidates. It admits none of the 52 distributor candidates, and it does not run at all on the other 3,049. A rescore (what a fresh validate does before that rule) would see an approved alias for 161 customer candidates and all 52 distributor candidates. The customer apply path would accept those 161. The distributor apply path would refuse all 52, because an approved alias for that token and source is already stored and a second insert hits the unique index. Nothing was applied.

## The count

VERIFIED (this session, `confirm_headlines.py`, `default_transaction_read_only=on`, write probe refused, database `cip`):

| Kind | needs_review |
|---|---|
| cst_location_token | 1,119 |
| product_identifier | 989 |
| cst_product_token | 531 |
| customer_dealer_token | 410 |
| shipment_customer_token | 163 |
| shipment_distributor | 52 |
| **Total** | **3,264** |

Job state of those rows (VERIFIED script `2c_count.py`): shipment rows sit on completed, loaded, not-archived jobs. Sell-through location and product rows are split between loaded jobs and archived jobs still at stage `validated`. Dealer tokens and about half the product identifiers sit on `completed_with_errors` jobs at stage `validated`.

## What the rule actually matches

Read from `apps/api/app/services/imports/shipment_evidence_import.py`.

- Customer: `_reuse_earlier_customer_alias_decisions` at line 679. A `needs_review` `shipment_customer_token` is reused only when `suggested_action` is `map_customer`, `match_reason` is `approved_customer_source_token_alias`, and `suggested_entity_id` is set. Apply then runs. A special-category row is included on purpose (the comment at line 682).
- Distributor: `_reuse_earlier_distributor_alias_decisions` at line 466. Same shape, with `map_distributor` and `approved_distributor_source_token_alias`.

Grep of `apps/api/app/services` found no `_reuse_earlier_*` for sell-through location, sell-through product, dealer token, or product identifier. Those kinds are outside the rule. A fresh validate can still apply an approved alias while it rebuilds candidates. That is a different pass. It was not simulated, and it was not run.

Approved alias stock (VERIFIED script `2c_ship_sim.py`): 6,458 approved customer aliases, 6 revoked; 57 approved distributor aliases.

## Shipment simulation

`queries/2c_ship_sim.py` is a read-only copy of the scorer, the reuse gate, and the apply preconditions. It does not call the application and it writes nothing. Output `2c_ship_sim.out.json`.

Two readings, because they are not the same number:

| Reading | Customer | Distributor |
|---|---|---|
| Stored reason is already the approved-alias tag the function requires | 47 | 0 |
| Rescored against current approved aliases, then the apply preconditions | 161 would clear, 2 would not | 0 would clear, 52 would not |

The 47 are inside the 161. The other 114 customer candidates are stored as `no_alias_or_exact_dim_match` (97) or `partial_customer_alias_coverage_across_source_tokens` (17). The function, as written, skips them until a validate rebuilds the candidate and sets the approved-alias reason. The 2 that stay out fail the scorer (`alias_partial_coverage_across_tokens`): an earlier resolved candidate exists for the same key (7 resolved rows, one target) but the tokens on the candidate are not all covered.

All 52 distributor candidates are stored as `no_alias_or_exact_dim_match`, so the function skips them. Rescored, all 52 are `alias_map`. Apply would still not clear them: an approved distributor alias for that normalised token and source already exists, and the insert hits `uq_dist_src_token_alias_approved_scope`. The decision is remembered. The old candidate was left at `needs_review`. There is no earlier candidate decision on those keys in any job (the alias row is the decision, not another candidate).

Of the 161 rescored customer clears, 47 are tagged noise-only and 8 internal-note. The function's own comment says those are meant to be reused. The simulation's apply preconditions accepted them.

Lines behind the shipment candidates are already unresolved (`lines_already_resolved` is false for all 215). Reuse would be acting on real unresolved lines, not on an empty candidate.

## By kind: would the rule clear it?

| Kind | Rows | Would the existing rule clear them? | Why |
|---|---|---|---|
| shipment_customer_token | 163 | 47 on the stored tag. 161 only after a rebuild. 2 no. | Reason gate, then partial token coverage |
| shipment_distributor | 52 | No | Stored reason is not the approved-alias tag. After a rescore the unique alias index refuses the insert |
| cst_location_token | 1,119 | No | No reuse function for this kind |
| product_identifier | 989 | No | No reuse function for this kind |
| cst_product_token | 531 | No | No reuse function for this kind |
| customer_dealer_token | 410 | No | No reuse function for this kind |

The handover line that a re-run "would likely clear most" of the 3,264 is not what this rule does. On a fresh shipment validate, cip_test did clear a new file's customer and distributor queues (CONTEXT, 30 Oct, ASSERTED). That is a rebuild plus reuse on a new job. It is not a pass over these stored rows, and it does not cover sell-through or dealer candidates.

Nothing was mapped, ignored, or applied.
