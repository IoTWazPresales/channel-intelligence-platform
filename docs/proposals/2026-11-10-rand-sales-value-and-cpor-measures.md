# Proposed definitions: Rand sales value and CPOR measures

**Status:** proposal only. Warren approves before any of this is built. Nothing in this note is implemented. The builder still refuses `dsi_sellout.value_ex_vat`, `cst_sellthrough.value`, `cpor.open_cases` and `cpor.value`.

Sources: `docs/DATA_MODEL_SPEC.md` §11 decisions 2 and 3; `sell_through_overview.py` (`load_observations`, VAT conversion, listing-price estimate); `cpor/lifecycle.py`; named CPOR measures already in `default.yaml` (`cpor.cases`, `cpor.support_usd`, `cpor.support_zar`, `cpor.delivery_rate`, `cpor.estimate_units`, `cpor.result_units`).

## 1. Distributor sell-out value (decision 2)

DSI has no currency column. Price is missing on many rows (the spec's count, not re-counted here: 22,546 of 58,128).

**Recommend accepting the spec as written.**

- Value = `units × unit_sellout_price_ex_tax_amount` on rows that have a price.
- Show priced-units coverage next to the value.
- Currency label: not recorded.
- Never `SUM(revenue)`.
- Rows with no price contribute nothing to the value and stay in the unpriced-units count.

## 2. Customer sell-through value (decision 3)

Each sell-through row carries `vat_basis`. The spec says: convert to the tenant sales-value VAT setting exactly as the sell-through overview does, and do not estimate a price for unpriced units.

The overview does both of these, and then does a third thing the spec forbids:

1. Priced rows: if the row is incl-VAT and the tenant setting is excl-VAT, divide by `1 + vat_rate`. The other way, multiply by `1 + vat_rate`. The rate is the tenant's, not a fixed 1.15.
2. Unpriced units: the overview fills them from the latest captured listing price for that customer and product. Listing prices are shelf prices (incl. VAT). It converts that shelf price with the same `1 + vat_rate` rule. A period comparison can then be meaningless when only one side is estimated (the overview records Warren's 2026-10-19 note of a +513% swing and suppresses the change when the estimated share differs by more than 25 points).

**Recommend the spec, not a copy of the overview's estimate.**

- On priced rows, convert `vat_basis` to the tenant sales-value VAT setting with the tenant rate (`1 + vat_rate`), the same arithmetic the overview uses for priced rows.
- Do not fill unpriced units from a listing price. Show priced units and units without a price beside the value, so a dashboard does not invent the gap the overview KPI fills.
- Do not hard-code 1.15.

If the two screens must show the same Rand figure, the alternative is to copy the overview including the listing-price estimate, and to show that the figure is partly estimated. That is the option this note does not recommend. Warren's choice decides it.

## 3. CPOR open cases and Rand case value

Lifecycle (`cpor/lifecycle.py`): draft → proposed → approved or rejected → active → ended → settled or cancelled. Rejected can be sent back to proposed. Cancelled is retained with zero payable. Ended, settled, cancelled and rejected are not open work.

Measures that already exist, and should stay the named figures:

| Id | What it already is |
|---|---|
| `cpor.cases` | Distinct cases |
| `cpor.support_zar` | Sum of `ttl_support` (Rand) for lines whose window starts in the period |
| `cpor.support_usd` | Support in USD |
| `cpor.estimate_units` / `cpor.result_units` | Estimate and result units |
| `cpor.delivery_rate` | Result units / estimate units |

**Recommend:**

- `cpor.open_cases` = distinct cases in `draft`, `proposed`, `approved` or `active`. Leave out `ended`, `settled`, `cancelled` and `rejected`.
- Do not add a second "value". Rand case value is the existing `cpor.support_zar` (`ttl_support`). Keep `cpor.value` refused so a chart cannot pick an unnamed value.
- If the wanted Rand figure is something else (estimate, result, or USD), name that column instead of building `cpor.value`.

## Not in this proposal

Restock flags stay pending. Customer weeks of cover is already built as `cst_sellthrough.stock_cover` and is not part of this approval.
