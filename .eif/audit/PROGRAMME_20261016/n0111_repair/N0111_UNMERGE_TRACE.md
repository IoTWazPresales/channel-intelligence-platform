# N-0111 repair item 5: Compuspeed LTD (1152) / SYNTECH DISTRIBUTION (PTY) LTD (4145) un-merge — traceability (read-only, cip)

Decision D-0111 (Warren 2026-10-16): un-merge both from OPEN_CHANNEL (id 1) on cip.
Rule given: un-merge only if the old merge recorded exactly which rows belonged to 1152 and 4145; otherwise stop for Warren.

**Verdict: NOT traceable exactly. No un-merge was made. No cip write.**

Probes (all read-only, `current_database() = cip`): `probe_unmerge.py`, `probe_unmerge2.py`, `probe_unmerge3.py`, `probe_unmerge4.py`; output beside them (`*_cip.txt`).

## What the merge recorded
- Both records still exist: 1152 `TMP-CUST-20260607200144-FECF` "Compuspeed LTD" and 4145 `TMP-CUST-20260608094305-EB7E`
  "SYNTECH DISTRIBUTION (PTY) LTD", `customer_status = merged`, `merged_into_customer_id = 1`, both last updated 2026-08-08 17:17.
- OPEN_CHANNEL `notes_summary`: `[open-channel absorb 2026-08-08T15:17:20Z] survivor=1; losers=[1152, 4145]; by=backlog-125`.
  Loser ids only, no row list (the note is cut at 512 characters).
- `platform_audit_event`: no merge event (the absorb predates the N-0095 `customer_merge` audit).
- `steward_audit_event` 58-61: aliases 1406, 4400, 4740, 5439 revoked (unwound 0 rows); 63: 16 lineup lines stamped
  from 4145 to OPEN_CHANNEL with `prior_customer_ids` recorded.
- The change-keeper service (`customer_merge_keeper.py`) says itself that a full merge leaves no record of which rows came from
  which side, never moves the keeper off OPEN_CHANNEL, and moves every row of a keeper (it cannot split rows).

## Traceable
| Rows on OPEN_CHANNEL | How | Count |
|---|---|---|
| `fact_sales_sellout` | `staging_line_id` -> job 96 staging line whose raw customer is "Compuspeed LTD"/"COMPUSPEED LTD" | 26 facts, 544 units |
| `fact_sales_sellout` | same, raw customer "Syntech Distribution Pty Ltd" | 5 facts, 26 units |
| (all OPEN_CHANNEL sell-out) | 31 of 31 facts link to those lines | 31 / 31 |
| `import_distributor_si_staging_line` | raw customer names the company (job 96) | 211 lines |
| `commercial_lineup_line` | steward audit 63 `prior_customer_ids` = 4145 | 16 lines |

The sell-out link is through the source token (the alias that pointed at 1152/4145), not a recorded pre-merge owner.

## Not traceable (no record of a prior owner)
| Table on OPEN_CHANNEL | Rows now |
|---|---|
| `fact_inbound_shipment` (customer_id / resolved_customer_id) | 5451 / 5499 (none carries the company names; the "Q1 Compuspeed", "SADC - Compuspeed", "Open Channel Syntech" tokens were Open Channel's own aliases from job 32) |
| `shipment_evidence_line` | 31829 / 31975 |
| `shipment_evidence_observation` | 16093 |
| `commercial_lineup_line` (other than the 16) | 76 |
| `cpor_case` (174), `cpor_payment_evidence`, CPOR staging | 1, 3, 11 + 3 |
| `fact_inventory_reconciliation` (distributor 29), `fact_customer_velocity`, `fact_returns` | 12, 2, 4 |
| `customer_source_token_alias` | 83 |

## For Warren
To un-merge, one of these is needed:
1. Accept a partial un-merge: move only the traceable rows (31 sell-out facts and their 211 staging lines by source token; the 16
   lineup lines by the audit record) back to revived 1152/4145, and leave everything else on OPEN_CHANNEL; or
2. Say which other rows (shipments, CPOR case 174, lineup lines) belong to Compuspeed or Syntech.
No service exists for an un-merge from OPEN_CHANNEL; either option needs a new, reviewed un-merge path (clone first).
