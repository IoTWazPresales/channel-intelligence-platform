# 2b: Product lines with no match on the 27 October shipment job (read-only)

**Result.** Job 1697 has 479 evidence lines, 40,695 units, with `product_resolution_status = 'no_match'`. Every one of those lines carries an item code. None of those item codes, sales models, barcodes or approved product aliases is on Product Master, including after stripping punctuation and leading zeros. The gap is a missing catalogue row for that item. It is not a format problem and it is not an alias that already exists under another spelling.

Labels. **VERIFIED (this session)** means `confirm_headlines.py` was run against `cip` with `default_transaction_read_only=on` and a refused write probe. **VERIFIED (script)** means the named read-only script's output was inspected and its totals re-added; it was not executed again this session. **ASSERTED** means taken from a report and not re-run.

## What was counted

The 479 are evidence lines of import job 1697, not a second population. VERIFIED (this session): 479 lines, 40,695 units. VERIFIED (script `2b_breakdowns.py`): open order 228 / 18,134 and shipped 251 / 22,561; sheets Shipped 254 / 23,146, Unship 223 / 17,226, BOM not ready 2 / 323. Resolution detail is `unresolved_product` on all 479. A separate 12 lines / 374 units are `inactive_only` and are not inside the 479.

Product Master at the time of the dump: 18,157 rows, all `is_active`, last created 2026-06-18 (VERIFIED script `2b_crosscheck.py`). Approved product aliases: 172 `source_import_token` / `steward_approved`. Customer article aliases were not used: these lines have no customer-item value (0 distinct).

Same item codes are unmatched on earlier shipment jobs as well: 149 of the 151 item codes, 2,223 lines, 13 jobs, earliest job 32 (VERIFIED script `2b_crosscheck.py`). The catalogue has not gained these items since June.

## How a line was classed

Offline, over the dump in `2b_dump_lines.out.json`, using the same token key the loader uses (strip, lower, drop a trailing `.0` on digits). Script `2b_analyse.py`.

1. Exact item code, sales model, EAN, UPC or MPOR against Product Master fields and against approved `product_alias` values.
2. If that misses: the same values with punctuation removed, edge separators removed, and leading zeros removed. Barcodes also compared as digits only.
3. If that misses: a family neighbour only (the item-code prefix and the sales-model stem both exist on other master rows, or the sales model without its last hyphen segment exists). A neighbour is not a match. The loader does not alias by prefix.

| Cause | Lines | Units | What it means | Label |
|---|---|---|---|---|
| Exact or format hit that the loader still left unmatched | 0 | 0 | Not an alias gap and not a format problem | VERIFIED (script) |
| Family neighbour only | 321 | 29,722 | The family is in the catalogue. This item code, model and barcode are not | VERIFIED (script) |
| No neighbour | 158 | 10,973 | Nothing in the catalogue shares that item family and model stem | VERIFIED (script) |
| **Total** | **479** | **40,695** | | |

Six sales-model values have a trailing separator or space. Trimming them still does not hit a master row, so they stay in the table above (`token_oddities`).

No master was created and no alias was written.

## By distributor (data rows)

VERIFIED (script `2b_breakdowns.py`). Every distributor on these lines is already resolved.

| Distributor | Lines | Units |
|---|---|---|
| Mustek | 99 | 16,202 |
| Pepkor | 84 | 6,102 |
| Pinnacle | 69 | 5,004 |
| Rectron | 59 | 4,495 |
| Compuspeed | 69 | 3,309 |
| DCC | 36 | 3,253 |
| ACZA | 29 | 871 |
| HV | 9 | 678 |
| Superdist | 6 | 304 |
| Firsttech | 8 | 132 |
| Brandhouse | 2 | 129 |
| Dgstore | 6 | 90 |
| Three | 1 | 76 |
| NITI | 1 | 35 |
| Syntech | 1 | 15 |

## By product family (from the item-code letters)

The letter group is the leading letters of the item code. On Product Master that rule matches `product_line` on 17,914 of 18,157 rows and disagrees on 243 (VERIFIED script). Master rows in the same letter group are shown so a family with master rows is not read as an empty family.

| Family | Lines | Units | Distinct item codes | Master rows in that letter group |
|---|---|---|---|---|
| NX | 107 | 16,763 | 54 | 5,173 |
| NB | 204 | 15,241 | 28 | 6,735 |
| PT | 29 | 3,657 | 12 | 1,310 |
| PF | 32 | 1,402 | 19 | 2,049 |
| NR | 35 | 1,227 | 6 | 1,908 |
| GM | 23 | 722 | 21 | 0 |
| NV | 35 | 690 | 2 | 10 |
| XB | 7 | 569 | 5 | 141 |
| LC | 5 | 280 | 2 | 0 |
| GI | 2 | 144 | 2 | 0 |

GM, LC and GI have no master row in that letter group: those 30 lines / 1,146 units are a catalogue gap with no sibling. The other families are sibling-present, item-absent.

## Top 25 groups

Group = distributor, identifier pattern, family. 50 groups in all. The top 25 hold 38,968 of 40,695 units. Full rows are in `queries/2b_analyse.out.json`. Pattern `item+model+barcode` is 448 lines / 39,501 units. Pattern `item+mpor` (no model, no barcode) is 24 lines / 723 units, all family GM, all on distributor ACZA, all catalogue gap. Pattern `item+model` with no barcode is 2 lines / 323 units (the BOM sheet).

| Distributor | Family | Lines | Units | Reading |
|---|---|---|---|---|
| Mustek | NX | 23 | 9,741 | Mixed: 13 lines have a family neighbour, 10 do not |
| Pepkor | NB | 56 | 4,686 | Family neighbour only. Same item codes also appear under Pinnacle |
| Pinnacle | NB | 52 | 4,655 | Family neighbour only, except 1 line / 14 units with no neighbour |
| Mustek | PT | 13 | 3,457 | Family neighbour only |
| Rectron | NB | 41 | 3,012 | 32 neighbour, 9 no neighbour |
| DCC | NX | 21 | 2,689 | 19 no neighbour, 2 neighbour |
| Mustek | NB | 41 | 2,019 | 30 neighbour, 11 no neighbour |
| Compuspeed | NX | 33 | 1,932 | 27 neighbour, 6 no neighbour |
| Rectron | NX | 10 | 1,129 | 8 no neighbour, 2 neighbour |
| Pepkor | NR | 17 | 888 | 14 no neighbour, 3 neighbour |
| ACZA | GM | 23 | 722 | No neighbour. Item plus MPOR only, no sales model and no barcode |
| Compuspeed | NB | 6 | 648 | Family neighbour only |
| HV | NX | 8 | 570 | 5 neighbour, 3 no neighbour |
| Compuspeed | PF | 15 | 508 | Family neighbour only |
| Mustek | PF | 2 | 323 | Family neighbour only. No barcode |
| Superdist | NX | 6 | 304 | Family neighbour only |
| DCC | XB | 3 | 240 | No neighbour |
| Pinnacle | NV | 11 | 219 | No neighbour |
| Rectron | XB | 2 | 219 | No neighbour |
| Pepkor | NV | 7 | 216 | No neighbour |
| Pepkor | NX | 2 | 192 | No neighbour |
| Mustek | PF | 3 | 170 | Family neighbour only |
| DCC | PF | 6 | 144 | Family neighbour only |
| ACZA | GI | 2 | 144 | No neighbour |
| Mustek | NV | 8 | 141 | No neighbour |

Customer names on these lines are in `2b_breakdowns.out.json` (`by_customer`). The largest are Open Channel 191 lines / 13,885 units, then a distributor's own deal account, then retail accounts. Customer identity does not change the product cause: the same item code is unmatched under several distributors.

## What this does not explain

62 shipped evidence lines / 4,940 units of this unmatched set have no fact row (VERIFIED script `2b_inactive.out.json`, `fact_vs_evidence_gap`). The 479 figure itself is the evidence count and is fully classed. Nothing in the 479 is left as an unknown cause.
