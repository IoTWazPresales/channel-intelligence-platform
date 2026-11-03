# Store and DC replenishment — N-0117 definition

Definition only. Written 3 November 2026. Inception. No product code, no migration, no node stage change, no acceptance.

Checked against `.eif/CONTEXT.md`, `.eif/DECISIONS.md`, and `.eif/JOURNEYS.yaml`. A conflict is recorded here and is not silently rewritten into those files.

N-0110 (stock position against reported on-hand) and N-0108 stay dependencies, as already recorded on the node. This definition does not re-open them. N-0118 owns loading staged store rows. This module reads facts as they are.

## Accepted rules this follows

- D-0134. Store and DC sales, stock, and replenishment are in scope. A store is shown by its own name and is never aliased to its parent customer.
- D-0135. The channel chain is tenant configuration, not code. The chain is OEM, then distributor, then the customer's sites. A distribution centre, where one is confirmed, belongs to the customer, not to the distributor.
- D-0136. A customer is direct when the OEM ships to a receiving site of that customer, and indirect when it buys through a distributor. One confirmed customer DC may serve several accounts. Which sites are DCs is the DC level rule, never an account name.
- D-0137. Name patterns are tenant configuration. Stock behaviour (high stock, no consumer sales) proposes a candidate. A steward confirms each DC once. The answer is remembered. Nothing is created without that confirmation.
- D-0139. Every site has a level (distributor stock, customer DC, store, other) and an owner (distributor or customer). A distributor's warehouse or business-unit account is distributor-level stock and is never a customer DC. With no confirmed DC there is no DC level: stock sits at store or account level, supplied through the distributor. The module must not invent a DC.
- Never auto-create a customer, distributor, product, or location from import evidence.
- D-0140, accepted 3 November 2026, scope N-0117: a shipment from the OEM directly to a customer's receiving site is evidence for a candidate. It is not sufficient on its own. The steward is asked once. The answer is remembered. This closes the question D-0139 left open. It does not supersede the rest of D-0139.

D-0139 also says a shipment that names a site as a distribution or fulfilment centre can be enough, on its own, for a DC to exist. The 3 November decision narrows that clause: the shipment is a candidate, and the level becomes customer DC only after the one confirmation. The rest of D-0139 stands.

## Conflicts with the durable artifacts

- `.eif/CONTEXT.md` does not yet contain the channel chain, site levels, or the steward-once rule. No sentence in it contradicts this definition.
- `.eif/DECISIONS.md` does not contain D-0134 to D-0139. It contains D-0132 as PROPOSED. This definition does not confirm D-0132 and does not copy the ledger decisions into that register.
- `.eif/JOURNEYS.yaml` has only the skeleton `first-path` journey. The journeys below are not in the catalog.
- Ledger D-0135 and D-0139 name a vendor. This definition says OEM. The vendor name is not repeated here and is not a condition.
- `docs/memory/CURRENT.md` and the 2 November deploy note disagree on whether migration `20261102_0051` is on `cip`. Not checked in the database here, and `CURRENT.md` was not edited. Site level, confirmation, and replenishment do not use `fact_upsert_key`.
- The shipment map compiles port coordinates into code (see `.eif/audit/OVERNIGHT_20261102/CODE_SCAN.md`). That stays a finding. The store map must not copy it. No place name and no coordinate is hardcoded for a store or a DC.
- Hardcoded account names that choose behaviour are listed in that same code scan. They stay findings. This module does not add to them and does not fix them.

## Census grades, 30 October 2026

Source: `.eif/audit/STORE_DC_CENSUS_20261030/REPORT.md`. Read-only on `cip` that day. Not re-run here. Grades only. No account is named.

Store grain, among the 8 customers in the sell-through classification:

| Grade | Customers | What the grade means here |
|---|---|---|
| READY | 1 | At least 8 explicit weeks, a stable site label, reported stock on at least half of store-week rows. The one READY customer has 10 explicit weeks and reported stock on 99% of store-week rows. |
| PARTIAL | 3 | A site label exists and READY fails. Two of them have a single explicit week, with reported stock on every store row of that week. One has many weeks and reported stock on under a tenth of store-week rows. |
| NONE | 4 | Account-level sell-through only: no site label, no location id, no location master row. |

`customer_location`: no rows. `distributor_location`: no rows. Store identity today is the site label on the sell-through fact, not a location master.

Distributors in the classification are PARTIAL, none READY. The partial grade is a non-blank ship-to on shipments. Inventory facts have as-of dates for several distributors and no location column. Distributor stock is distributor-level, not site-level.

DC grades, over 156 customers in that count: DC stock reported 0, DC named only 5, no DC data 151. The five are named only because a shipment ship-to looks like a distribution site. None of them has stock reported at a DC. Under the 3 November rule those five are candidates, not confirmed DCs. Today the module has no confirmed DC.

Filled site keys on facts and staging are site name and site code. No coordinate key was filled. Promotion cases have no store or site column (310 cases, 657 lines at the census).

Lead-time inputs that exist: shipped lines with both a ship-confirm date and a proof-of-delivery date, per distributor (census section C10). No learned lead time is stored. There is no second date pair for DC to store.

`.eif/audit/OVERNIGHT_20261102/LOAD_PLAN.md`: four customers have store-level staging that is not fully on the facts. Loading it does not move any grade to READY. For two partial customers, a later apply collapsed site rows onto a source key with no site while the site label was still filled, so the fact units are not the staged units. N-0118 owns that repair. This module must not invent the missing units, and must not treat that chain key as a store. Where a site label is present, show the label. Where the stored units are the collapsed grain, say so.

## What the module does

The channel chain is configuration: OEM to distributor, then customer sites. Code walks the configured chain. It does not contain an account, a distributor, or a vendor.

Site levels and owners follow D-0139. A distributor-owned site cannot be saved as a customer DC. The database rejects that pair.

A customer DC exists only after one steward confirmation. Until then the site is a candidate. Candidates come from three places, all of which only propose:

1. A name pattern stored in tenant configuration. The pattern is data. A pattern match is not a DC.
2. Stock behaviour: high stock and no consumer sales, as a proposal.
3. A shipment from the OEM directly to a customer's receiving site. Evidence for a candidate. Not sufficient on its own. The steward is asked once.

Remember the answer. A later file does not ask again. Reject is remembered too. A rejected candidate is not a DC and is not asked again unless a steward reopens it.

No confirmation, no DC level. Stock stays at store grain where the customer's report has a site, otherwise at account grain. Supply is through the distributor. The screen does not show a DC block, a DC need, or a DC-to-store transfer for that customer.

A confirmed DC may serve several accounts. The link is an explicit list the steward maintains. It is not a name match and not a guess from a parent string. Each store still shows its own name.

Needs:

- Where a confirmed DC exists: what the stores need from that DC, then what that DC needs from the distributor that supplies it.
- Where no confirmed DC exists: what the store needs from the distributor. A customer with no store grain needs at account grain, from the distributor. That customer is a success case, not an error.

Which distributor supplies a site is taken from shipment history and from distributor stock at distributor grain. It is not taken from a distributor location, because that master is empty and a distributor warehouse is not a customer DC.

Lead times are learned from history, per distributor and per receiving site, from ship-confirm date to proof of delivery. Show the distribution. Do not fold one statistic into a buy number until Warren accepts that statistic. DC-to-store has no date pair in the census, so that lead time stays "not in the history" until a receipt date exists. Do not copy the OEM-to-site lead time and call it DC-to-store.

Slow and unsold stock, when a threshold is configured: a suggested path of promote, move between stores or customers, or return to the distributor. The suggestion is a label. It does not create a promotion, a transfer, or a return. Until a threshold is stored, the panel says it is not configured. It does not borrow a silent number.

The store map follows the shipment map's interaction (a site opens the lines for that site) and does not follow its hardcoded coordinates. With no coordinates, do not plot a dot. See the map decision below.

Reported on-hand stays a checkpoint. Calculated stock is not stored as a fact. N-0110 remains the stock-position rule.

## Tenant configuration, data, and code

| Kind | What |
|---|---|
| Code | Level enum and owner enum. A distributor owner cannot be level customer DC. Candidate versus confirmed. Steward asked once. No auto-create. A store keeps its own name. No DC section without a confirmed DC. Suggestions are not executions. The filter and the read model. |
| Tenant configuration | The channel chain. DC name patterns. Cover weeks, if a tenant sets them. Slow and unsold thresholds. The lead-time statistic used in a need, once chosen. Nothing in this list is a constant in code for one account. |
| Data | Customers, distributors, sites, confirmations, the accounts a DC serves, site labels, sales, reported stock, shipments, ship-confirm and proof-of-delivery dates, learned samples. |

Already in code, at account grain, not at store grain: `customer_report_config.replen_min_weeks_of_cover` and `replen_target_weeks_of_cover`. When they are empty, the account-level screen uses 4 and 6 weeks (`DEFAULT_REPLEN_MIN_WEEKS_OF_COVER`, `DEFAULT_REPLEN_TARGET_WEEKS_OF_COVER` in `customer_report_config.py`). Whether store and DC needs reuse those settings is the planning decision below. This definition does not extend 4 and 6 to stores.

Location masters today: customer location types are `hq`, `store`, `warehouse`, `branch`, `online`, `other`. There is no DC type. Distributor location types include `warehouse`, which stays on the distributor. Add a level field. Do not overload location type, and do not treat a customer warehouse type as a confirmed DC.

## Acceptance criteria

Hold for any customer, including one added later, and including one with no DC and one with no stores.

1. A customer with no site label and no confirmed DC sees account-level sales and stock, supplied through the distributor, and no DC section.
2. A customer with site labels and no confirmed DC sees one row per site, each under that site's own label, never under the parent account's name. Needs are store from distributor.
3. A confirmed DC that serves two accounts shows DC stock once, and each store under its own name. Needs are store from DC, then DC from distributor.
4. A distributor warehouse or business-unit account cannot be saved as a customer DC.
5. A direct OEM shipment to a customer receiving site creates a candidate and does not set the level. A second shipment does not ask again after confirm or reject.
6. A tenant pattern match, or high stock with no consumer sales, creates a candidate only.
7. No import creates a customer, a distributor, a product, or a location.
8. Lead time per distributor and receiving site is computed from ship-confirm to proof of delivery. A site with no such pair says there is no history. DC-to-store is not given that pair's number.
9. Slow and unsold, once configured, suggest promote, move, or return, and do not post those movements. With no configuration, the panel says not configured.
10. The store map does not contain a place name or a coordinate. A site with no coordinates is not given a dot.
11. No customer, distributor, retailer, store, DC, product, or vendor name in a rule, a default, a pattern, or a test.

## Journeys

Not in the catalog yet:

1. Open a customer that has stores and no confirmed DC. See stores by their own labels, a distributor supply line, and no DC heading.
2. Open a customer that has no sites. See account grain and no empty DC.
3. A steward opens a candidate that came from a direct shipment, confirms it once, and a later shipment does not ask again. The site then appears as a customer DC.
4. A steward is offered a distributor warehouse as a candidate and cannot confirm it as a customer DC.
5. Slow stock, after thresholds exist, shows a suggestion and does not create a promotion, a move, or a return.

## Risks

- Treating the five "named only" shipment ship-tos as confirmed DCs. They are candidates.
- Plotting stores with invented coordinates, or copying the port table.
- Aliasing a store to its parent in a total, a map label, or a need.
- Using the collapsed chain-key units as if they were store units (N-0118).
- Extending the 4 and 6 week fallback to stores without a decision.
- A second confirmation prompt after the steward has answered.
- Auto-creating `customer_location` from a site label. The master is empty on purpose until a steward creates a row.
- A name pattern in code. Patterns belong in tenant configuration.

## Migration

Not run, and not authorised here. First schema unit, when Warren gives the usual migration go:

- Level, owner, candidate-or-confirmed, confirmed-at, and confirmed-by on customer locations and on distributor locations. A check constraint: owner distributor cannot have level customer DC.
- A candidate table that is not a master. It can name a site label and the evidence kind (pattern, stock behaviour, direct shipment) without inserting a location.
- A link from a confirmed customer DC to the customer accounts it serves.
- No row created by an importer.

Read models, the lead-time distribution, and the suggestion panel do not need their own tables. Learned samples are queries. Do not store a calculated on-hand as a fact.

## Build order

One implementation session each. Units 1–4 and 6 do not need a new commercial decision. The node blockers are about units 5, 7, and 8. The engine blocks the whole node anyway; Warren says if 1–4 and 6 may start while those blockers are open.

1. Level, owner, confirmation, and the distributor-owner constraint. Steward action on an existing location. Fictional tests. No import changes.
2. Candidate queue from tenant patterns, stock behaviour, and a direct OEM shipment. Ask once. Remember confirm and reject. Do not create a location.
3. Read model: site label where present, account grain where not, no DC section without a confirmed DC. A customer with no DC is the test, not an edge.
4. Explicit "DC serves these accounts" link. Stores keep their own names.
5. Needs. Blocked on the planning decision. DC-to-store where a confirmed DC exists; store-from-distributor where it does not.
6. Lead-time panel: the distribution of ship-confirm to proof of delivery, per distributor and receiving site. No single number fed into a need. Can ship before the planning decision.
7. Slow and unsold suggestions. Blocked on the planning decision. Labels only.
8. Store map. Blocked on the map decision.

## Tests and renders

Fictional tenants only. No production account names.

- Customer with no site and no DC: account grain, no DC section.
- Customer with two sites and no DC: two labels, neither equal to the parent name, needs from the distributor.
- Confirmed DC serving two accounts: one DC stock figure, two store names.
- Distributor-owned site rejected as a customer DC.
- Direct shipment inserts a candidate row and no location row. Second event does not insert a second question.
- Pattern match stays a candidate.
- Lead time uses only rows that have both dates. A site without them renders "no history".
- Suggestion click does not write a promotion, a transfer, or a return.

Renders, light and dark, 1280 and 390, after the read model exists:

- The no-DC customer and the no-store customer.
- A candidate list with Confirm and Reject.
- The lead-time panel with history and with no history.
- The map only after the map decision. Until then, a site list, not a map with guessed dots.

## Planning decision (D-0142, proposed)

Question: what number may a need or a slow-stock label use?

Options:

1. Reuse the customer's existing cover settings, including the account-level fallback of 4 and 6 weeks when the settings are empty. Slow and unsold stay unconfigured until the tenant stores a threshold. The lead time shown is the distribution only; no statistic is subtracted inside a need.
2. Same cover reuse, and Warren names the slow threshold, the unsold threshold, and the lead-time statistic (for example a median with a minimum sample) before those labels ship.
3. No fallback. Cover, slow, unsold, and the lead-time statistic are all empty until the tenant sets them. Needs say "not configured."

Evidence: the 4 and 6 week fallback is already shipped for account-level cover. The census has ship-confirm and proof-of-delivery pairs and no DC-to-store pair. No slow-stock threshold is in this definition's sources as a store-grain rule.

Assumptions: account-level cover and store-level cover are the same commercial idea until Warren says a site can differ. A suggestion that fires on a code constant will be wrong for the next tenant.

Impact: option 1 ships needs sooner and extends 4 and 6 to stores. Option 3 ships no buy number until configuration exists. Option 2 is option 1 plus an explicit threshold list.

Reversibility: high if the number is read from configuration at request time and not stored on the fact.

Recommendation, not a decision: option 3 for any new threshold, and do not extend 4 and 6 to stores until Warren says so. The lead-time panel in unit 6 does not need this decision.

## Map decision (D-0143, proposed)

Question: what does the store map show when a site has no coordinates? The census filled site name and site code only.

Options:

1. A site list, in the shipment map's selection pattern, and no dots until a steward stores a coordinate. No geocoding.
2. Geocode the site label through an external service and store the result.
3. The steward drops a pin. No external call.

Evidence: no coordinate key was filled in the census. The shipment map's coordinates are hardcoded place names, which this module is not allowed to copy.

Assumptions: a site label is not a reliable address. An external geocoder sends site labels off the machine.

Impact: option 1 ships a usable list and an honest empty map. Option 2 needs a vendor, a retention rule, and a failure state. Option 3 is accurate and slow to fill.

Reversibility: option 1 is a screen. Option 2 stores derived coordinates that would have to be deleted to undo. Option 3 is steward data and is reversible by clearing the pin.

Recommendation, not a decision: option 1, then option 3 if Warren wants dots. Not option 2 in this inception.

## M5c — mapping memory and aliases, tenant scope (D-0144, proposed)

Separate from N-0117. Does not block units 1–8. One tenant is the situation described in `.eif/audit/REVIEW_20261102/BATCH2_REPORT.md` (Needs Warren, item 1). Not re-counted in the database here.

Question: how should header mappings, remembered sheets, cleared tokens, and approved aliases be scoped to a tenant?

What the code does now:

- `source_definition.column_mapping_memory` holds header mappings, `selected_sheet_names`, `seen_sheet_names`, and cleared tokens. `source_definition` has no `tenant_id`. `import_job` has `tenant_id` and points at a source. Two tenants that shared a source would share one memory. The read and write are in `shipment_field_mapping.py`, by source, with no tenant key.
- These alias tables have no `tenant_id`: `customer_source_token_alias`, `distributor_source_token_alias`, `channel_source_token_alias`, `region_source_token_alias`, `product_alias`, `customer_article_alias`. The customer, distributor, and product masters do have `tenant_id`. A lookup that matches the token and does not join the master's tenant can reuse another tenant's alias. `lineup_customer_token_stamp.py` loads approved customer aliases by normalised token and status, and its own comment calls that alias global.

Options:

1. Add `tenant_id` to `source_definition` and to each alias table above. Backfill from the related master's tenant, or `default` where there is no master. Put `tenant_id` on the unique keys. Every read and write filters the job's tenant. One migration, then the lookup call sites. Size: one migration and a pass over those resolvers. Larger than option 2, and it covers aliases, which option 2 does not.
2. Namespace the JSON inside `column_mapping_memory` by tenant, and keep reading the current un-namespaced keys for `default`. No migration if the column stays JSON. Does not touch alias tables. Size: the mapping read and write only. Incomplete.
3. Do nothing until a second tenant exists. Size: none. The day a second tenant is added, it inherits the first tenant's sheets, headers, cleared tokens, and aliases.

Evidence: the models and the two call sites above; BATCH2 item 1; one tenant on `cip` as stated there, not re-queried.

Assumptions: a source is not already split by tenant in data. Backfill to `default` is safe only while that stays true.

Impact: option 1 is the one that stops a cross-tenant alias. Option 2 stops a cross-tenant sheet memory and leaves aliases global. Option 3 is safe only while a single tenant is a hard rule.

Reversibility: high while one tenant has the only rows; a column can be dropped. Low after two tenants have diverged, because dropping the column merges their memory again.

Recommendation, not a decision: option 1. Do not implement it in this session. Warren picks. This does not confirm D-0132 and does not depend on migration `20261102_0051`.

## Choices left for Warren

1. D-0142. Planning numbers: cover at store and DC grain, slow and unsold thresholds, and whether any lead-time statistic enters a need. Proposed. Blocks units 5 and 7.
2. D-0143. Store map when a site has no coordinates. Proposed. Blocks unit 8.
3. D-0144. M5c option 1, 2, or 3. Proposed. Does not block N-0117.
4. Whether units 1–4 and 6 may be built while the node is blocked on items 1 and 2. The engine has no unit-level blocker.
5. Whether `20261102_0051` is on `cip`. This module does not need it.
6. D-0132 stays unconfirmed.
