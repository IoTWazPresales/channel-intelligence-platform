# On the water — path map (step 6)

Read-only map of where each piece of SPEC.md lives today, taken from the code at `4be3698c` (branch
`feat/ns-2-brief-nav-collapse`). Line numbers are for that commit. FACT = read in the file. Nothing here
changes a decision in the SPEC; contradictions are in the last section.

## Shipments tab

| What | Where |
|---|---|
| Route and tab | `/supply/shipments` → `apps/web/src/app/(app)/supply/shipments/page.tsx`; tab list `apps/web/src/features/supply-inbound/supplyPaths.ts:1-10` |
| Page body | `apps/web/src/features/supply-inbound/InboundShipmentsWorkspace.tsx` (988 lines). Render order from line 561: info alert, PO-filter banner, `ShippingCommercialSummary` (line 589), lineup quarter summary, then the filter bar (`ScopeBar` chips from line 626) and the grid |
| KPI tiles **and** the "Arriving this week by distributor" chart | `apps/web/src/app/(app)/shipping/ShippingCommercialSummary.tsx` (268 lines). Tiles 5: Pipeline value, Arriving this week, Delivered this week, Overdue shipments, ETA shifts vs prior job (`HeadlineStrip` + `HeadlineFigure`). The chart is the `CategoryBars` at line 225, caption "Arriving this week by distributor", rendered only when `arrivingData` has rows |
| Where the map goes (D1) | In place of that `CategoryBars` block (ShippingCommercialSummary.tsx:222-239), under the tile strip and above the filter bar. The chart stays as the "By distributor" view |
| Tile click → grid filter | `applySmartPreset` (InboundShipmentsWorkspace) sets `smartPreset`; the filter params carry `cohort` (`current_incoming`, `overdue`, `arriving_week`, `landed_week`). Vessel click can reuse the same route: a new filter param, appended in `appendShippingFilterParams` |
| URL builders (one list shared by `/lines`, `/commercial-summary`, `/eta-shifts`) | `apps/web/src/app/(app)/shipping/buildShippingLinesUrl.ts:1-100` (`ShippingFilterParams`, `appendShippingFilterParams`) |

## KPI tiles and grid filters (API)

| What | Where |
|---|---|
| Endpoints | `apps/api/app/api/v1/endpoints/shipping.py`: `GET /shipping/commercial-summary` (line 808), `/eta-shifts` (1080), `/lines` (1401), filter options (783) |
| One filter builder for lines and tiles ("must stay aligned") | `_build_shipping_fact_filters` (≈ line 300-352), `_shipping_filters_active` (356) |
| Tile predicates (cohorts) | `apps/api/app/services/shipping_commercial_kpis.py:18-110`: `predicate_current_incoming`, `predicate_overdue`, `predicate_arriving_week`, `predicate_landed_week`; contract `docs/SHIPPING_COMMERCIAL_KPI_CONTRACT.md` |
| Date filter field list | `DATE_FIELD_MAP` `shipping.py:63-74` (no on-board / port ETA / port ATA yet) |
| Line payload (grid row) | `shipping.py:680` and `:1823` (`est_pod_date` is serialised in both; add the new fields beside it); evidence endpoint `shipment_evidence.py:148` |
| Admin grid optional columns | `apps/web/src/app/(app)/admin/shipment-evidence/shipmentEvidenceOptionalFields.ts` (picker list; `est_pod_date` at line 18) |

## `observation_transitions.py` (the LAG mechanism to reuse)

`apps/api/app/services/shipping/observation_transitions.py`: `observation_field_lag` (line 41) wraps one column in
`LAG(...) OVER (PARTITION BY line_identity_key ORDER BY valid_from, id)`; `observation_lag_window` (93) builds the
windowed select; `compute_eta_shifts` (257) uses the map at line 272 (`"est_pod": ShipmentEvidenceObservation.est_pod_date`,
plus promise). The new fields are columns on `ShipmentEvidenceObservation` after migration 0049, so the same lag
can read `port_eta_date` and `on_board_date`. FACT: it compares the previous observation, not the earliest one, so
SPEC "Slip = earliest `port_eta_date` observed" needs a `FIRST_VALUE` (or a min per identity), not only a lag.

## `shipment_change_events.py`

`apps/api/app/services/imports/shipment_change_events.py`: `_DATE_SLIP_FIELDS` (line 33-40) is a tuple of
`(observation column, label)`; `_diff_consecutive_pair` (120) compares consecutive observations with `getattr`.
BACKLOG-218 is adding `("port_eta_date", "port_eta")` and `("on_board_date", "on_board")`. Not done in step 8: it
would add events for every existing observation pair the day the backfill lands, and the SPEC orders the backfill
after the proof.

## Field mapping catalogue

| What | Where |
|---|---|
| Canonical targets | `apps/api/app/services/imports/shipment_field_mapping.py:32` `SHIPMENT_CANONICAL_TARGETS` (now +12) and help text `SHIPMENT_FIELD_TARGET_DESCRIPTIONS` |
| Header aliases | the heuristics in `build_initial_shipment_field_mapping` (same file, ≈ line 240-420) and the `inbound_shipments` template, `apps/api/app/services/imports/template_definitions.py` ≈ line 612-760 (`expected_columns`) |
| Saved mapping | `source.column_mapping_memory["by_header_norm"]` (`merge_shipment_mapping_memory`, line 146); `headers_match_saved_shipment_mapping` (196) decides whether the mapping step is skipped |
| Extraction | `_extract_common` in `apps/api/app/services/imports/shipment_evidence_import.py:172` (by mapped header) → `row_values` (≈ 1460) → line upsert `_shipment_line_conflict_set` (≈ 915) |
| Evidence → observation | `_LINE_TO_OBSERVATION_COLS` in `shipment_evidence_observations.py:29`; hash columns `_OBSERVATION_HASH_COLS` in `shipment_evidence_line_identity.py:180` (the new columns are deliberately outside it) |
| Evidence → fact | `_UPSERT_REFRESH_COLUMNS` and `_row_values_from_evidence` in `shipment_inbound_facts.py:55,100` |

## Tenant profile overrides

`apps/api/app/services/commercial_tenant_profile.py`: file-backed JSON per tenant
(`{local_storage_path}/tenant_profiles/{tenant}.json`). A key must be listed in `TENANT_PROFILE_OVERRIDE_KEYS`
(line 149) and handled in `load_tenant_profile_overrides` (758, loose) and `save_tenant_profile_overrides` (804,
strict, ValueError → 400). Pattern to copy: `open_book` (679-755). Endpoints: `auth.py:388-420`. The SPEC's tenant
config for lanes, hubs, extent, size, stale-report days and needs-a-look days has no home yet; only
`shipping_method_pattern` was added in step 8 (the backfill needs it).

## workbench-ui and the existing chart kit

`apps/web/src/features/workbench-ui/`: `HeadlineFigure.tsx` (KPI tile, `HeadlineStrip`), `Panel.tsx`, `charts.tsx`
(`CategoryBars`, `TrendChart`, formatters, `formatChartValue`, `useChartTheme` colours from tokens),
`ChartControls.tsx` (top-N and sort), `controls.tsx` (`ScopeBar`), `displayName.ts` (party display names).
Tokens: `apps/web/src/theme/cipTokens.ts`, `packages/ui/src/tokens.ts`. No map or SVG helper exists; the basemap is a
new inline-SVG component per SPEC. The distributor display rule the SPEC names (`resolve_distributor_display`) is in
`apps/api/app/services/shipping_distributor_display.py`.

## Readers of `fact_inbound_shipment` (SPEC schema item 5)

The new columns are nullable and new, so a reader that names its columns is unaffected. 57 modules mention the
table or its model (grep `FactInboundShipment|fact_inbound_shipment` under `apps/api/app`); the ones that read
whole rows: `import_job_delete_figures.py:809` (`SELECT *` into a dict, then reads named keys; its restore path goes
through `_row_values_from_evidence`, which now carries the new fields) and `shipment_open_book.py:583` (builds a
dict from named attributes). `shipment_evidence_current` (a VIEW, baseline 0001 / 0009 / 0026 / 0027) lists its
columns explicitly, so it does **not** expose the new columns; nothing in step 8 needs it to, and recreating it is
a separate DDL change that is not in the approved migration.

## Contradictions and open points (SPEC not re-decided)

1. **`ship_way` vs the existing `shipway`.** The mapping already has a `shipway` target (kept on the raw row only,
   23 666 raw rows carry a stamped `shipway` key), and saved mappings send the header "Ship Way" there. Both now
   fill `ship_way`: the importer reads `ship_way`, then falls back to the value mapped as `shipway`. New mappings map
   the header to `ship_way`. The old target stays so saved mappings keep working.
2. **Forwarder and hub pattern.** The SPEC default reads "leading capitals" as the forwarder. On cip (60 distinct
   values), 3 834 of the 110 832 lines with a method lead with a Chinese forwarder name (`凌凱ckg-Air--`,
   `廣盈c-Sea--`), and 267 have capitals and no hub (`PDHL-GS-Express--`, `WWP-Air--`). A capitals-only pattern would leave those without forwarder and hub, and the hub
   decides the lane. The default is the SPEC rule widened to "capitals or non-Latin letters" with the hub optional;
   it gives the same answer on every ASCII value. One regex (`DEFAULT_SHIPPING_METHOD_PATTERN` in
   `shipment_voyage.py`) to revert; a tenant can override it.
3. **RLS "like other tenant tables".** There is no tenant setting in the database: tenant scoping is the `tenant_id`
   column, applied by the API, and the only row-level security in the repo is product-line based (needs a
   `product_id`; `port_condition` has none). `port_condition` has FORCE row security with permissive SELECT and
   INSERT policies and **no** UPDATE or DELETE policy, plus SELECT and INSERT grants only. That is the append-only
   part of the SPEC; tenant filtering stays in the API.
4. **Saved mappings ask once more.** `headers_match_saved_shipment_mapping` returns false when a header has a mapped
   target but no saved one. After this change, the first ACZA file per source shows the mapping step once so the new
   headers can be confirmed; after that the next files skip it again.
5. **Evidence-line and observation columns are filled by update.** SPEC step 4 asks for existing observations to be
   backfilled. Observations are append-only by convention, not by trigger or policy (no triggers on the three tables;
   `cip_pl_update` exists). The backfill only fills NULL columns outside the observation hash.
6. **Slip needs "earliest", not "previous".** See `observation_transitions.py` above.
