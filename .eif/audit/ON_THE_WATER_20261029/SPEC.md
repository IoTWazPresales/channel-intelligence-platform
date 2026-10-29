# On the water — build spec

Approved by Warren, 28–29 October 2026. Written by Claude (claude.ai chat, Opus 5.5) from the four ACZA Shipped_Unshipped reports (29 Sep, 20 Oct, 23 Oct, 27 Oct 2026) and the code at `bbde4f95`.

Files in this folder:

- `Main.dc.html` — the approved mock-up: layout, copy, states, hover card and interaction. Its script block holds sample data computed from the 27 Oct report. The product computes the same figures from CIP data.
- `basemap.svg` — the dotted land map and lanes for the default extent. It shows only the base layer; the glow markers, labels, pulse and cards are the overlays in `Main.dc.html`.
- `generate_basemap.py` — reference tool for the projection, lanes, hubs and ports. Dev-only; the product must not depend on `global-land-mask`.

## Decisions

| # | Decision |
|---|---|
| D1 | **Placement.** Supply & Inbound › Shipments tab, in the slot of the "Arriving this week by distributor" chart, between the KPI tiles and the filter bar. A Map / By distributor toggle keeps the bar chart as the second view. Nothing else on the page moves. |
| D2 | **Match the mock-up exactly**: layout, hierarchy, copy, states, hover card and interaction. Colours come from the CIP tokens (`apps/web/src/theme/cipTokens.ts`, `packages/ui/src/tokens.ts`). Dark is the reference; light must work. This is not a redesign. |
| D3 | **Migration approved** (see Schema). Applying it to `cip` still needs Warren's "run against cip" after a clone proof. |
| D4 | **No scraping.** Port delay is a manual Administration entry until a licensed feed is chosen. |
| D5 | **Hover / focus card per vessel**: distributors with units, top 4 products with units, "+N more models", value, ETA. |
| D6 | **Positions are estimated** from on-board date and port ETA. Live AIS tracking is a later step that needs vessel name or B/L or ISO container numbers from the forwarders, and a paid provider Warren chooses. |
| D7 | **"BOM not ready" lines are open orders** (prompt 1, open-book work). |

## Facts found (VERIFIED from the reports and code)

- The reports carry `On-Board Date`, `ETA Date(Est Port Arrival)`, `ATA Date(Actual Port Arrival)`, `Shipping Method` (forwarder plus origin hub, e.g. `COSCOckg-WWP-Truck/Sea--`, `KGILsha-WWP-Sea--`, `PREMIEREnl-Sea--`, `WWPc-Sea--`), `Ship Way`, `Deliver Port` (UN/LOCODE) and `Currency` (all USD in these files).
- None of these is a column in CIP today. They live only in `raw_source_row`.
- `fact_inbound_shipment.eta_date` is **not** the port ETA. It is a coalesced delivery date (POD → est POD → promise → schedule ship → ship confirm → ERD → ex-works, `shipment_inbound_facts.py`). The new field is named `port_eta_date` so the two are never confused.
- `Container Number` in the ACZA files is a 5-digit internal number, not an ISO 6346 container number. Do not map it to `container_no`.
- On every arrived line, port ETA equals ATA within about a day. The report overwrites ETA, so only the history across reports shows a delay. Between 29 Sep and 27 Oct, 6 of 7 vessels at sea moved 5–14 days later.
- Lines with the same on-board date and port ETA are on the same ship: 11 forwarder groups collapse to 7 vessels on 27 Oct.
- The existing "ETA shifts vs prior job" tile (`services/shipping/observation_transitions.py`) compares est POD / promise against the previous observation. It is a different field and window. Reuse its LAG mechanism; do not copy its SQL.

## Schema (approved migration, one revision after the current head)

1. On `shipment_evidence_line`, `shipment_evidence_observation` and `fact_inbound_shipment`, all nullable: `on_board_date`, `port_eta_date`, `port_ata_date` (date); `shipping_method`, `forwarder_code`, `origin_hub`, `ship_way`, `deliver_port` (varchar); `vessel_name`, `voyage_no`, `bill_of_lading_no`, `container_no` (varchar, empty until forwarders supply them).
2. Add each field to `SHIPMENT_CANONICAL_TARGETS` with a description, and map the ACZA headers through the existing mapping mechanism. Header aliases go in the mapping layer, not in import code. `forwarder_code` and `origin_hub` are parsed from `shipping_method` by a tenant-config pattern (default: leading capitals = forwarder, following lower-case letters = hub).
3. Table `port_condition`, append-only (RLS like other tenant tables, no UPDATE or DELETE policy): `id`, `tenant_id`, `port_code`, `delay_days` (numeric), `note`, `entered_by`, `entered_at`. The newest row per tenant and port is current.
4. Backfill, guarded (dry run default, `--apply --expect-db`, one transaction, audit event): fill the new columns on existing evidence, observations and facts from `raw_source_row` using each job's saved mapping. Prove it on a pg_dump clone with counts per job and per field. `cip` only on "run against cip".
5. The fact writer copies the new fields from evidence. Every reader of `fact_inbound_shipment` is unaffected because the columns are new and nullable; list the readers anyway.

## Data rules (one API, filtered by the same page scope as the KPI tiles)

- **As of** = today. The header shows "Data as of <newest applied report date>". If that is more than 7 days old, show an amber "Report is N days old" note (threshold is tenant config).
- **Sea only on the map**: `ship_way` contains SEA. Air and express in transit are counted in the At-sea tile's sub-line ("+N units by air") and not drawn.
- **At sea**: line state shipped, `on_board_date` ≤ as-of, `port_ata_date` null.
- **Overdue arrival**: at sea with `port_eta_date` < as-of. Draw it at the discharge port with an "Arrival overdue" state.
- **Arrived, not delivered**: `port_ata_date` set, `pod_date` null, split by `deliver_port`.
- **Booked, not on board**: `on_board_date` > as-of, state shipped or open.
- **Value**: show per currency. Prefix US$ only when every line in the figure is USD; otherwise list each currency. Never sum across currencies (the query model already refuses `shipments.amount` for this reason).
- **Vessel key**: `vessel_name` + `voyage_no` when present; otherwise inferred from (tenant, `on_board_date`, `port_eta_date`, `deliver_port`, lane), labelled "inferred".
- **Lane**: `origin_hub` → lane via tenant config (`commercial_tenant_profile` overrides). Defaults are in `generate_basemap.py` (`LANES`, `HUB_LANE`). An unknown hub uses the default lane, labelled "route assumed".
- **Position**: the fraction of `on_board_date` → `port_eta_date` elapsed, placed along the lane polyline, equirectangular projection. Extent and size are tenant config (defaults in `generate_basemap.py`).
- **Slip**: per line, the earliest `port_eta_date` observed in any report against the current one. Vessel slip = the largest line slip. Add `port_eta_date` and `on_board_date` to `_DATE_SLIP_FIELDS` in `shipment_change_events.py` (closes BACKLOG-218). Badge "+N days" or "On time"; detail shows "<first ETA> on <first report date> → <current ETA> on <latest report date>".
- **Distributors**: the same display the grid's Distributor column uses (`resolve_distributor_display`). Products: `sales_model_name`, top 4 by units, "+N more models".
- **Needs a look**: open lines from a Shipped sheet (no confirm date) whose ex-works date is more than 7 days old (tenant config). Show count, units and distributor split, with a link that filters the grid. Add the same signal to Attention (closes BACKLOG-219).
- **Port conditions**: the newest `port_condition` per port, e.g. "15 days · entered by Warren, 29 Oct". With no entry, "No figure entered" and Planned. Entry form under Administration, admin role, append-only.

## Interaction and layout

- **Click** a vessel (marker or list row) to select it and filter the grid below to its lines, the way the KPI tiles filter. **Hover or focus** shows the card (D5).
- Vessels within about 4% of each other on the map collapse into one cluster chip ("3 vessels at or near Durban · units · ETA range"). Labels show for the selected vessel and up to 4 others, never overlapping.
- Markers and rows are real buttons with labels. The tooltip opens on focus as well as hover. Reduced motion stops the Durban pulse.
- At 390 px wide the list stacks under the map and the KPI tiles wrap.
- Render the land dots and lanes as an inline React SVG from the `basemap.svg` path data, coloured by tokens, so light mode works.
- Use MUI, Recharts and workbench-ui. No new UI, chart or map library.

## Acceptance

1. Migration and backfill proven on a clone with per-field counts; cip only after "run against cip"; services restarted only after that.
2. cip_test value tests: vessel grouping, position fraction, slip from observations, at sea / arrived / booked / overdue totals, sea-only, currency rule, needs-a-look, port condition current row, grid filter by vessel.
3. Vitest for the component, the toggle, the hover card and the grid link.
4. Browser renders at 1280x800 and 390x844, dark and light, saved in this folder, with an enumerated difference list against `Main.dc.html`. Every difference is classified MIGRATE / CORRECT / BLOCKED, and every MIGRATE is closed.
5. Full web and API suites, tsc and lint. One commit, explicit paths, pushed.
