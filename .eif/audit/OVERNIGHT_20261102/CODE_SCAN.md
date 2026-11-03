# Code scan: hardcoded account names, and distributor sites treated as a DC

Scan script `queries/scan_names.py`. Output `queries/scan_names.tsv`. Roots: `apps/api/app`, `apps/api/alembic`, `apps/api/scripts`, `scripts`, `apps/web/src`, `packages`. The pattern is account, marketplace, distributor, port and city names plus a few fixture codes. This session ran it. 573 hit lines: 337 in product or script code, 235 in tests and fixtures, 1 in a migration. Tests are listed in the TSV and are not repeated here. Nothing was edited.

A name in a comment, a port coordinate table, or a one-off ops script is still a hit. The rows below are the ones that choose behaviour.

## Names that choose behaviour (file:line)

| File | Lines | What is hardcoded |
|---|---|---|
| `apps/api/app/services/imports/cst_article_alias_import.py` | 31–39 | A dict from display name to a preferred customer name |
| `apps/api/app/services/imports/cst_p4_customer_bootstrap.py` | 26–36 | Fixed customer ids and names for a placeholder report config. One id is excluded by name |
| `apps/api/app/services/imports/distributor_sales_inventory.py` | 151–158 | Substrings treated as strategic-channel hints |
| `apps/api/app/services/imports/cst_d1.py` | 27–29, 107, 149, 183–184, 205 | Customer names in sell-through rules |
| `apps/api/app/services/commercial_planner/lineup_distributor_as_customer_remediation.py` | 4–6, 39, 181, 192, 211, 214 | Named distributors in a remediation path |
| `apps/api/app/services/commercial_planner/lineup_bulk_rederivation.py` | 302–306, 330–331 | A customer name inside rederivation |
| `apps/api/app/services/customer_leftover_repair.py` | 27, 30–31, 100, 189 | Named customers in a repair list |
| `apps/api/app/services/listing_capture/registry.py` | 32–35 and the takealot block | A marketplace adapter bound to one retailer name |
| `apps/api/app/services/listing_capture/takealot_fetch.py` | 1, 8, 24–25, 56, 63, 102, 107 | Fetch path for one marketplace |
| `apps/api/app/services/shipping/on_the_water.py` | 51–63 | Port names and coordinates, including a destination port, compiled into the map |
| `apps/web/src/features/supply-inbound/onTheWater/layout.ts` | 34, 37–38, 42, 60, 89 | The same port names on the client |
| `apps/web/src/app/(app)/admin/port-conditions/page.tsx` | 17, 19, 22 | Example port names in the admin page |

The full product list, one line per hit, is the TSV. Ops scripts under `apps/api/scripts/ops/` account for a large share of the 337 and are one-off repairs, not the loader.

## Distributor site treated as a customer DC

No product path sets a distributor location to a customer distribution centre.

- Customer location types are `hq`, `store`, `warehouse`, `branch`, `online`, `other` (`apps/api/app/api/v1/endpoints/customers.py:53`). There is no DC type.
- Distributor location types are `hq`, `branch`, `warehouse`, `office`, `store`, `other` (`apps/api/app/api/v1/endpoints/distributors.py:35`). Warehouse stays on the distributor.

The adjacent path is the shipment loader treating ship-to text as the distributor when bill-to is empty:

- `apps/api/app/services/imports/shipment_evidence_import.py:529-534` buckets an unresolved line on ship-to when bill-to is blank, and the candidate entity is the distributor.
- `apps/api/app/services/imports/shipment_evidence_import.py:1107-1120` calls distributor resolution with bill-to and ship-to, and the AI fallback token is bill-to or else ship-to.

That is a distributor identity, not a customer DC. It is also how a customer receiving site would be stored if it arrived only in ship-to. It does not confirm a DC and it does not create a location.
