# N-0111 finding: DSI upload read the wrong header row (job 1669)

## 1. Cause (proved, read-only on cip; one SELECT-only session, `SET TRANSACTION READ ONLY`)

The suspected cause (banner default `header_row=19` in `dsi_file_stamp.py`) is **disproved**. That value only sets how many
leading rows the banner sniff reads for the distributor name and period. It is not the header row.

Job 1669 (`import_job`, cip), `Asus Sales and Inventory - 2026-10-12T095628.702.xlsx`, source 12, template `distributor_inventory`:

| What | Value |
| --- | --- |
| `staged_metadata.dsi_workbook.sheets[0].header_row` | `1` (0-based, i.e. row 2). The mapping step DID detect the headers. |
| headers it read | Invoice Number, Invoice Date, Debtor Acc Code, Debtor Name, Sales Rep Code, Sales Rep Name, WRH, Category, Product Code, Product Description, QTY, LOT ID (plus `Unnamed: 0` for the blank column A) |
| saved `field_mapping` | Product Code → product_identifier, QTY → quantity_sold, Invoice Date → transaction_date, Debtor Name → dealer_group_token, Invoice Number → invoice_no |
| `import_row_result` | row 0, error, `missing_product_identifier_mapping` |
| timeline | created 17:02:39; validate ran 17:05:33 to 17:05:40; job row updated again 17:21:18 |

Why the load failed although the mapping held the product column: for a single-file job the validate pipeline
(`apps/api/app/ingestion/pipeline.py`) did **not** use the mapping step's frame. It re-read the file with
`read_tabular` (a plain `header=0` read), then ran `sanitize_dsi_field_mapping` against those columns and wrote the
result back to `job.field_mapping`.

Reproduced on the stored upload of job 1669 (read with `python -I`):

- `read_tabular(header=0)` columns: `Unnamed: 0` … `Unnamed: 12`, 36,276 rows.
- `load_dsi_workbook_sheet_frames` (the mapping step): sheet `Sales`, header_row 1, real headers.
- `sanitize_dsi_field_mapping(Unnamed cols, saved mapping)` → `({}, [])`: the whole mapping erased, so
  `product_identifier` was gone and the load stopped at the first gate with 0 rows read.

Any single-file DSI upload whose headers are not on the first row failed this way (blank leading row, or a banner form).

## 2. Fix

- `dsi_workbook.py`: header row detection per file and sheet (existing hint-word detection kept; when row 1 is blank and no
  row has the hint words, falls back to `cst_layouts._fallback_header_row`, the fullest of the first rows); empty
  leading/stray columns with no header and no values are dropped (no more `Unnamed: 0` from a blank column A); the row is
  stored per sheet in `staged_metadata.dsi_workbook.sheets[].header_row`; an uploader-set row is stored in
  `staged_metadata.dsi_header_row_overrides` (`<file>::<sheet>` → 0-based row) and wins over detection.
- `pipeline.py`: single-file DSI jobs load the sheet through the same header-aware loader as the mapping step. If none of
  the saved columns match, the saved mapping is kept (not erased).
- `POST /api/v1/imports/jobs/{id}/dsi-header-row` (steward write): sets the row (1-based as shown in the sheet), re-reads
  that file, other files' saved mappings stay.
- Web mapping step: "Headers found on row N" with a field and "Re-read headers".
- A load that reads nothing says why in plain words: `dsi_no_header_row` ("No header row found in …"),
  `missing_product_identifier_mapping` and `dsi_no_mapped_sheets` now append "Headers read from row N of <file>
  (found automatically / set by you): <headers>", and `dsi_no_data_rows`.
- Banner-layout distributors (headers on row 20) still detect row 20: existing tests
  `test_asus_weekly_sellout_form_header_at_row_19` / `..._csv_header_at_row_19` (0-based 19) plus the new
  `test_banner_layout_header_still_detected_on_row_20` ("Headers read from row 20") and the web test "banner layout reads as row 20".
- `header_row_for_file` no longer turns a stored `0` into the banner default 19 (`or` bug).

## 3. Proof on cip_test (synthetic file of the exact shape)

`apps/api/tests/test_dsi_header_row.py::test_pinnacle_shape_maps_loads_nets_credit_notes_and_reupload_changes_nothing`:
sheet "Sales", row 1 empty, column A empty, headers B2:M2, 8 sales lines (36 units) and 3 credit notes (-6 units).

- mapping step: `file_headers` = the 12 real headers, `header_row` 1.
- apply: status `completed`; fact_sales_sellout 8 rows / 36 units; fact_returns 3 rows / 6 units; net 30.
- re-upload as a new job: same totals, same row counts (8 / 3). Changes nothing.
- The same test against the OLD `pipeline.py` fails with `completed_with_errors`, "1 rows require attention" (the
  reported symptom); with the fix it passes.
