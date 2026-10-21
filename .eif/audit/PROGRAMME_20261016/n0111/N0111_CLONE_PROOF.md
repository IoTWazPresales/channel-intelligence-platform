# N-0111 clone proof
- cip (source, read only): db cip, rev 20261015_0040, fact_rows 3197, fact_units 12394.0000, fact_on_hand 30832.0000, superseded_rows 390, positions 701, staging_rows 46718, figure_col 0, figures_col 0, on_hand_nullable NO, status_check CHECK (((status)::text = ANY ((ARRAY['compared'::character varying, 'first_report'::character varying])::text[])))
- clone before: db cip_n0111, rev 20261015_0040, fact_rows 3197, fact_units 12394.0000, fact_on_hand 30832.0000, superseded_rows 390, positions 701, staging_rows 46718, figure_col 0, figures_col 0, on_hand_nullable NO, status_check CHECK (((status)::text = ANY (ARRAY[('compared'::character varying)::text, ('first_report'::character varying)::text])))
  alembic upgrade head on database cip_n0111 as postgres (superuser True)
- clone after upgrade: db cip_n0111, rev 20261016_0041, fact_rows 3197, fact_units 12394.0000, fact_on_hand 30832.0000, superseded_rows 390, positions 701, staging_rows 46718, figure_col 1, figures_col 1, on_hand_nullable YES, status_check CHECK (((status)::text = ANY ((ARRAY['compared'::character varying, 'first_report'::character varying, 'no_on_hand'::character varying, 'chain_restart'::character varying])::text[])))
  alembic downgrade -1 on database cip_n0111 as postgres (superuser True)
- clone after downgrade: db cip_n0111, rev 20261015_0040, fact_rows 3197, fact_units 12394.0000, fact_on_hand 30832.0000, superseded_rows 390, positions 701, staging_rows 46718, figure_col 0, figures_col 0, on_hand_nullable NO, status_check CHECK (((status)::text = ANY ((ARRAY['compared'::character varying, 'first_report'::character varying])::text[])))
  alembic upgrade head on database cip_n0111 as postgres (superuser True)
- clone after upgrade again: db cip_n0111, rev 20261016_0041, fact_rows 3197, fact_units 12394.0000, fact_on_hand 30832.0000, superseded_rows 390, positions 701, staging_rows 46718, figure_col 1, figures_col 1, on_hand_nullable YES, status_check CHECK (((status)::text = ANY ((ARRAY['compared'::character varying, 'first_report'::character varying, 'no_on_hand'::character varying, 'chain_restart'::character varying])::text[])))
- round trip keeps every count: True

## Synthetic 2-year history load on the clone

current_database()=cip_n0111
products [(2, '90NR0381-M08090'), (3, '90XB06MN-MPW000'), (4, '90NX0AD1-M00260')]; window 2023-01-02 to 2025-01-12

## Round 1
  Amazon history 2023.csv (job 1668, completed): units 1052.0, latest on-hand 648.0, rows 1050, superseded records 0
  Amazon history 2024.csv (job 1669, completed): units 2144.0, latest on-hand 1116.0, rows 2142, superseded records 0
  Amazon W31.csv: no year confirmed -> status completed_with_errors, stage failed, year_required [{"filename": "W31.csv", "suggested_year": null}], fact rows from this load 0
    message: W31.csv: This file has week or month numbers without a year. Enter the year of the week numbers and tick Year confirmed; nothing from this file loads until then.
  Amazon W31.csv: year 2023 confirmed -> fact rows 3, week 2023-07-31 units/on-hand (20.0, 488.0)
  Amazon sales week Z.csv (job 1671, completed): units 2182.0, latest on-hand 1116.0, rows 2148, superseded records 0
    week 2024-12-30: units 0.0 -> 18.0, on-hand 0.0 -> 0.0: sales-only file, first figure for this week
  Amazon stock week Z.csv (job 1672, completed): units 2182.0, latest on-hand 1098.0, rows 2148, superseded records 0
    week 2024-12-30: units 18.0 -> 18.0, on-hand 0.0 -> 1098.0: stock-only file, sales unchanged
  Amazon stock week Z1.csv (job 1673, completed): units 2182.0, latest on-hand 1095.0, rows 2151, superseded records 0
    week 2025-01-06: units 0.0 -> 0.0, on-hand 0.0 -> 1095.0: stock-only file, first figure for this week
  Amazon sales week Z1.csv (job 1674, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 0
    week 2025-01-06: units 0.0 -> 21.0, on-hand 1095.0 -> 1095.0: sales-only file, stock unchanged
  Amazon history 2024.csv (job 1675, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 0
  Amazon correction weeks 61-62.csv (job 1676, completed): units 2245.0, latest on-hand 1095.0, rows 2151, superseded records 42
  Takealot history 2023.csv (job 1677, completed): units 1052.0, latest on-hand 648.0, rows 1050, superseded records 0
  Takealot history 2024.csv (job 1678, completed): units 2144.0, latest on-hand 1116.0, rows 2142, superseded records 0
  Takealot W31.csv: no year confirmed -> status completed_with_errors, stage failed, year_required [{"filename": "W31.csv", "suggested_year": null}], fact rows from this load 0
    message: W31.csv: This file has week or month numbers without a year. Enter the year of the week numbers and tick Year confirmed; nothing from this file loads until then.
  Takealot W31.csv: year 2023 confirmed -> fact rows 3, week 2023-07-31 units/on-hand (20.0, 488.0)
  Takealot sales week Z.csv (job 1680, completed): units 2182.0, latest on-hand 1116.0, rows 2148, superseded records 0
    week 2024-12-30: units 0.0 -> 18.0, on-hand 0.0 -> 0.0: sales-only file, first figure for this week
  Takealot stock week Z.csv (job 1681, completed): units 2182.0, latest on-hand 1098.0, rows 2148, superseded records 0
    week 2024-12-30: units 18.0 -> 18.0, on-hand 0.0 -> 1098.0: stock-only file, sales unchanged
  Takealot stock week Z1.csv (job 1682, completed): units 2182.0, latest on-hand 1095.0, rows 2151, superseded records 0
    week 2025-01-06: units 0.0 -> 0.0, on-hand 0.0 -> 1095.0: stock-only file, first figure for this week
  Takealot sales week Z1.csv (job 1683, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 0
    week 2025-01-06: units 0.0 -> 21.0, on-hand 1095.0 -> 1095.0: sales-only file, stock unchanged
  Takealot history 2024.csv (job 1684, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 0
  Takealot correction weeks 61-62.csv (job 1685, completed): units 2245.0, latest on-hand 1095.0, rows 2151, superseded records 42
  Pinnacle history 2023 (job 1686): applied sell/ret/inv 526/0/150 -> units 1052.0, latest on-hand 69.0, sellout rows 526, inventory rows 151
  Pinnacle history 2024 (job 1687): applied sell/ret/inv 546/0/156 -> units 2144.0, latest on-hand 17.0, sellout rows 1072, inventory rows 307
  Pinnacle week-number only (no date) (job 1688): applied sell/ret/inv 0/0/0 -> units 2144.0, latest on-hand 17.0, sellout rows 1072, inventory rows 307
  Pinnacle sales-only week Z (job 1689): applied sell/ret/inv 3/0/0 -> units 2159.0, latest on-hand 17.0, sellout rows 1075, inventory rows 307
    inventory rows 307 -> 307, latest on-hand 17.0 -> 17.0: sales-only left stock unchanged
  Pinnacle stock-only week Z (job 1690): applied sell/ret/inv 0/0/3 -> units 2159.0, latest on-hand 101.0, sellout rows 1075, inventory rows 310
    sell-out units 2159.0 -> 2159.0: stock-only left sales unchanged
  Pinnacle history 2024 re-upload (job 1691): applied sell/ret/inv 546/0/156 -> units 2159.0, latest on-hand 101.0, sellout rows 1075, inventory rows 310
  Pinnacle correction weeks 61-62 (same invoices) (job 1692): applied sell/ret/inv 42/0/6 -> units 2201.0, latest on-hand 101.0, sellout rows 1095, inventory rows 310
  Pinnacle correction week 61 (new invoice numbers) (job 1693): applied sell/ret/inv 1/0/0 -> units 2203.0, latest on-hand 101.0, sellout rows 1096, inventory rows 310

## Round 2 (re-run of the whole set)
  Amazon history 2023.csv (job 1694, completed): units 2245.0, latest on-hand 1095.0, rows 2151, superseded records 42
  Amazon history 2024.csv (job 1695, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
  Amazon W31.csv (job 1696, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
  Amazon sales week Z.csv (job 1697, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
    week 2024-12-30: units 18.0 -> 18.0, on-hand 1098.0 -> 1098.0: sales-only file, stock unchanged
  Amazon stock week Z.csv (job 1698, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
    week 2024-12-30: units 18.0 -> 18.0, on-hand 1098.0 -> 1098.0: stock-only file, sales unchanged
  Amazon stock week Z1.csv (job 1699, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
    week 2025-01-06: units 21.0 -> 21.0, on-hand 1095.0 -> 1095.0: stock-only file, sales unchanged
  Amazon sales week Z1.csv (job 1700, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
    week 2025-01-06: units 21.0 -> 21.0, on-hand 1095.0 -> 1095.0: sales-only file, stock unchanged
  Amazon history 2024.csv (job 1701, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
  Amazon correction weeks 61-62.csv (job 1702, completed): units 2245.0, latest on-hand 1095.0, rows 2151, superseded records 126
  Takealot history 2023.csv (job 1703, completed): units 2245.0, latest on-hand 1095.0, rows 2151, superseded records 42
  Takealot history 2024.csv (job 1704, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
  Takealot W31.csv (job 1705, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
  Takealot sales week Z.csv (job 1706, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
    week 2024-12-30: units 18.0 -> 18.0, on-hand 1098.0 -> 1098.0: sales-only file, stock unchanged
  Takealot stock week Z.csv (job 1707, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
    week 2024-12-30: units 18.0 -> 18.0, on-hand 1098.0 -> 1098.0: stock-only file, sales unchanged
  Takealot stock week Z1.csv (job 1708, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
    week 2025-01-06: units 21.0 -> 21.0, on-hand 1095.0 -> 1095.0: stock-only file, sales unchanged
  Takealot sales week Z1.csv (job 1709, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
    week 2025-01-06: units 21.0 -> 21.0, on-hand 1095.0 -> 1095.0: sales-only file, stock unchanged
  Takealot history 2024.csv (job 1710, completed): units 2203.0, latest on-hand 1095.0, rows 2151, superseded records 84
  Takealot correction weeks 61-62.csv (job 1711, completed): units 2245.0, latest on-hand 1095.0, rows 2151, superseded records 126
  Pinnacle history 2023 (job 1712): applied sell/ret/inv 526/0/150 -> units 2203.0, latest on-hand 101.0, sellout rows 1096, inventory rows 310
  Pinnacle history 2024 (job 1713): applied sell/ret/inv 546/0/156 -> units 2181.0, latest on-hand 101.0, sellout rows 1096, inventory rows 310
  Pinnacle week-number only (no date) (job 1714): applied sell/ret/inv 0/0/0 -> units 2181.0, latest on-hand 101.0, sellout rows 1096, inventory rows 310
  Pinnacle sales-only week Z (job 1715): applied sell/ret/inv 3/0/0 -> units 2181.0, latest on-hand 101.0, sellout rows 1096, inventory rows 310
    inventory rows 310 -> 310, latest on-hand 101.0 -> 101.0: sales-only left stock unchanged
  Pinnacle stock-only week Z (job 1716): applied sell/ret/inv 0/0/3 -> units 2181.0, latest on-hand 101.0, sellout rows 1096, inventory rows 310
    sell-out units 2181.0 -> 2181.0: stock-only left sales unchanged
  Pinnacle history 2024 re-upload (job 1717): applied sell/ret/inv 546/0/156 -> units 2181.0, latest on-hand 101.0, sellout rows 1096, inventory rows 310
  Pinnacle correction weeks 61-62 (same invoices) (job 1718): applied sell/ret/inv 42/0/6 -> units 2203.0, latest on-hand 101.0, sellout rows 1096, inventory rows 310
  Pinnacle correction week 61 (new invoice numbers) (job 1719): applied sell/ret/inv 1/0/0 -> units 2203.0, latest on-hand 101.0, sellout rows 1096, inventory rows 310

## Per source: before / after / after re-running the whole set
  Amazon (299) before: units 0.0, latest on-hand 0.0, on-hand rows sum 0.0, rows 0, positions {}, customer all units 415.0
  Amazon (299) round1: units 2245.0, latest on-hand 1095.0, on-hand rows sum 509851.0, rows 2151, positions {'chain_restart': 3, 'compared': 2145, 'first_report': 3, 'no_on_hand': 3}, customer all units 2660.0
  Amazon (299) round2: units 2245.0, latest on-hand 1095.0, on-hand rows sum 509851.0, rows 2151, positions {'first_report': 3, 'chain_restart': 3, 'no_on_hand': 3, 'compared': 2145}, customer all units 2660.0
  Amazon: re-run changed nothing: True
  Takealot (20) before: units 0.0, latest on-hand 0.0, on-hand rows sum 0.0, rows 0, positions {}, customer all units 1253.0
  Takealot (20) round1: units 2245.0, latest on-hand 1095.0, on-hand rows sum 509851.0, rows 2151, positions {'chain_restart': 3, 'compared': 2145, 'first_report': 3, 'no_on_hand': 3}, customer all units 3498.0
  Takealot (20) round2: units 2245.0, latest on-hand 1095.0, on-hand rows sum 509851.0, rows 2151, positions {'first_report': 3, 'chain_restart': 3, 'no_on_hand': 3, 'compared': 2145}, customer all units 3498.0
  Takealot: re-run changed nothing: True
  Pinnacle (29) before: {'sellout_rows': 0, 'units': 0.0, 'inventory_rows': 1, 'latest_on_hand': 1.0}
  Pinnacle (29) round1: {'sellout_rows': 1096, 'units': 2203.0, 'inventory_rows': 310, 'latest_on_hand': 101.0}
  Pinnacle (29) round2: {'sellout_rows': 1096, 'units': 2203.0, 'inventory_rows': 310, 'latest_on_hand': 101.0}
  Pinnacle: re-run changed nothing: True

  alembic downgrade -1 on database cip_n0111 as postgres (superuser True)
- clone after downgrade with N-0111 positions present: db cip_n0111, rev 20261015_0040, fact_rows 7499, fact_units 16884.0000, fact_on_hand 1050534.0000, superseded_rows 642, positions 4997, staging_rows 59882, figure_col 0, figures_col 0, on_hand_nullable NO, status_check CHECK (((status)::text = ANY ((ARRAY['compared'::character varying, 'first_report'::character varying])::text[])))
- clone cip_n0111 dropped
- cip after (unchanged): db cip, rev 20261015_0040, fact_rows 3197, fact_units 12394.0000, fact_on_hand 30832.0000, superseded_rows 390, positions 701, staging_rows 46718, figure_col 0, figures_col 0, on_hand_nullable NO, status_check CHECK (((status)::text = ANY ((ARRAY['compared'::character varying, 'first_report'::character varying])::text[])))
- cip unchanged by the clone proof: True
