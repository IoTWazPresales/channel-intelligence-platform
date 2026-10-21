# N-0111 repair proof (2026-10-16)

Runs: RUN-20261016-N0111-REPAIR (build), RUN-20261016-N0111-VER2 (self-verification, same session, same model).
Warren's decisions recorded first: D-0107 (Date column), D-0108 (dropped rows say so), D-0109 (week 52 -> 1),
D-0110 (distributor same-invoice reload), D-0111 (un-merge Compuspeed/Syntech).

## Built
1. **"Date" is a sale-date column.** Customer sell-through: "date" joins the built-in sale-date aliases (template and mapped
   columns still win; a Week column wins over a Date column). Distributor files already mapped "Date" to the transaction date;
   a test now pins it. CST has no upload-time column-mapping screen (columns come from the source mapping/template);
   the distributor mapping step lets the uploader pick any column as Date. Read-only on cip: no past CST staging row had a
   plain "Date" column, so no earlier load reads differently.
2. **Every load reports rows read / loaded / not loaded by reason.** `import_load_report` (CST and DSI) on the job list
   (`display_status`, counts), the job detail (`load_report`) and `GET /api/v1/imports/jobs/{id}/load-report`. A job with any
   row not loaded (or, for Pinnacle, partly loaded) reads **"Completed with rows not loaded (N)"**. Import Center: the jobs grid
   Status column and a panel above the CST file strip / DSI resolution section list each reason with its rows. The CST parser
   now records rows it could not stage and files it refused (year not confirmed, units without on-hand, on-hand without units).
3. **Week 52/53 -> 1 rolls the year.** Each product and site is read in file order from the confirmed year and moves on one
   year where its week number drops back; a product first seen in week 1 takes the year the others placed week 1 in; a full
   year per product sorted by product never rolls.
4. **Distributor reload of the same invoice keeps the replaced figures.** `20261016_0042` adds the append-only
   `fact_distributor_line_superseded`; the DSI apply writes the stored row and the changed figures before the upsert (sell-out
   and returns). New invoice numbers add rows as before. Same figures write nothing; re-applying a load writes nothing.
5. **Compuspeed/Syntech un-merge: NOT done.** The rows cannot be traced exactly (see `N0111_UNMERGE_TRACE.md`). Stopped for Warren.
6. **Stock positions recomputed on cip once** (`recompute_stock_gap_output.txt`).

## Clone proof (`N0111R_CLONE_PROOF.md`, clone `cip_n0111r`, dropped)
- 0042: upgrade, downgrade, upgrade with every count equal (sell-out 35582, units 178195.85, returns 3176, inventory 47411,
  DSI staging 183463, CST facts 3197, CST units 12394).
- CST Amazon (299), real pipeline: "Date" file -> 9 day rows, "Completed"; W51, W52, W1, W2 with 2024 confirmed -> 2024-W51,
  2024-W52, 2025-W1 (starts 2024-12-30), 2025-W2, "Completed"; dropped-rows file -> "Completed with rows not loaded (2)":
  missing product code or units 1, product not matched 1. Same three files again: totals unchanged (rows 22, units 69).
- Pinnacle (29), real DSI fact apply: load 10 invoices + 1 credit (units 30, returned 1, superseded 0); reload of the same
  invoices with 4 lines and the credit changed (units 38, returned 2, superseded sell-out 4, returns 1); correction of 2 lines
  plus new invoice N111R-INV-11 (11 rows, units 38, superseded sell-out 6, returns 1); re-applying the correction changed nothing
  (totals and superseded counts). Re-running the whole set ends at the same totals; the trail grows (sell-out 6 -> 10, returns 1 -> 2)
  because re-applying an older load replaces the newer figures again and keeps them.
- cip unchanged by the clone proof.

## cip
- `20261016_0042` applied as the migration role: every count unchanged (`N0111R_CIP_APPLY.md`).
- Stock positions recomputed once (derived table): before compared 314, first report 387 (701). After 4158: no_on_hand 3457,
  chain_restart 298, first_report 387, compared 16 (Game; all 16 flagged, first cause no prior on-hand). Per customer in
  `probe_positions_cip.txt` (Computer Mania 2426 no-on-hand weeks over 56 products).

## Tests
- Full API pytest on cip_test: see `pytest_full.txt`.
- Full web vitest (2 workers): see `vitest_full.txt`.

## Limits and findings
- Item 5 un-merge not done; Warren chooses (partial un-merge of the traceable rows, or names the other rows).
- Not rendered in a browser (sign-in).
- Pinnacle proof through the fact upsert from resolved staging lines, not the DSI file parser.
- The year roll reads row-level week labels; wide week-column files and month labels do not roll.
- Distributor lines of one load with the same key replace each other (kept and named); summing them is Warren's call.
- After the recompute most positions do not compare (D-0105 chain rule with weekly gaps in on-hand).
