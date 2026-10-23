'use client';

import { Box, Stack, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { useState } from 'react';

import {
  allNulls,
  coverWeeks,
  fewShort,
  longCustomers,
  oneCategory,
  pairedCustomers,
  pairedQuarters,
  pieSlices,
  podDays,
  unitSeries,
  verticalWrap,
  weeks26,
  weeks52,
} from '@/design-lab/fixtures/charts';
import type { ChartControlsState } from '@/features/workbench-ui/ChartControls';
import { CategoryBars, PairedBars, RankedBars, ShareChart, TrendChart } from '@/features/workbench-ui/charts';
import { Panel } from '@/features/workbench-ui/Panel';
import { useUiStore, type ColorMode } from '@/stores/uiStore';

/**
 * Chart grammar fixtures (N-0114). The real shared charts from `features/workbench-ui`, not the lab's
 * older primitives, on deterministic fixture data. Check each section in light and dark at
 * 1280x800 and 390x844: axis titles with units, legends, long names, top N and sort, number text.
 */

const grid = { display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'repeat(2, minmax(0, 1fr))' } } as const;

export default function DesignLabChartsPage() {
  const colorMode = useUiStore((s) => s.colorMode);
  const setColorMode = useUiStore((s) => s.setColorMode);
  // The pie's top N held here to show "5 shown of 9" without a click.
  const [pieControls, setPieControls] = useState<ChartControlsState>({ topN: 5, sort: { by: 'value', dir: 'desc' } });

  return (
    <Stack spacing={2} sx={{ p: { xs: 2, md: 3 }, minWidth: 0 }} data-testid="design-lab-charts">
      <Stack direction="row" alignItems="flex-start" justifyContent="space-between" flexWrap="wrap" useFlexGap sx={{ gap: 1.5 }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Charts
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Shared chart grammar fixtures. Check at 1280x800 and 390x844, in light and dark. Every number is fixture data and
            only its formatting is under test.
          </Typography>
        </Box>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={colorMode}
          onChange={(_e, m: ColorMode | null) => m && setColorMode(m)}
          aria-label="Colour mode"
        >
          <ToggleButton value="light">Light</ToggleButton>
          <ToggleButton value="dark">Dark</ToggleButton>
        </ToggleButtonGroup>
      </Stack>

      <Box sx={grid}>
        <Panel title="1. Long customer names, 37 categories" subtitle="RankedBars with the toolbar: top 10 of 37, names wrap, full name on hover and in the tooltip">
          <RankedBars
            data={longCustomers.map((d) => ({ label: d.customer, value: d.value }))}
            unit="zar"
            summary="Outstanding by customer"
            labelHeader="Customer"
            valueHeader="Outstanding"
            xAxisTitle="Customer"
            yAxisTitle="Outstanding (R)"
          />
        </Panel>
        <Panel title="1b. Same 37 customers as category bars" subtitle="Layout auto: many or long labels go horizontal">
          <CategoryBars data={longCustomers} x="customer" y="value" unit="zar" xAxisTitle="Customer" yAxisTitle="Outstanding (R)" />
        </Panel>

        <Panel title="2. Few short categories" subtitle="Six short labels stay vertical; no toolbar under six rows">
          <CategoryBars data={fewShort} x="channel" y="count" height={220} unit="count" xAxisTitle="Channel" yAxisTitle="Open orders" />
        </Panel>
        <Panel title="3. Vertical wrap case" subtitle="Seven labels of 15 to 24 characters, forced vertical: two-line wrap, ellipsis, full name on hover">
          <CategoryBars
            data={verticalWrap}
            x="family"
            y="units"
            height={240}
            layout="vertical"
            unit="units"
            xAxisTitle="Product family"
            yAxisTitle="Sell-out (units)"
          />
        </Panel>

        <Panel title="4. Three series over 26 weeks" subtitle="Bar, line and area; legend because there is more than one series">
          <TrendChart
            data={weeks26}
            x="week"
            height={260}
            unit="units"
            xAxisTitle="Week"
            yAxisTitle="Units per week (units)"
            series={[
              { key: 'soh', label: 'Stock on hand', kind: 'area', tone: 'muted' },
              { key: 'shipped', label: 'Shipped in', kind: 'bar' },
              { key: 'sellOut', label: 'Sell-out', kind: 'line' },
            ]}
          />
        </Panel>
        <Panel title="5. Plan vs shipped, 12 customers" subtitle="PairedBars: long names go horizontal; starts in the caller's order">
          <PairedBars
            data={pairedCustomers}
            x="customer"
            a="plan"
            b="shipped"
            aLabel="Plan"
            bLabel="Shipped"
            unit="units"
            xAxisTitle="Customer"
            yAxisTitle="Units, plan and shipped (units)"
          />
        </Panel>
        <Panel title="5b. Quarters against last year" subtitle="Time axis: stays vertical, no toolbar">
          <PairedBars
            data={pairedQuarters}
            x="label"
            a="ly"
            b="cur"
            aLabel="Last year"
            bLabel="This year"
            height={240}
            timeAxis
            unit="units"
            xAxisTitle="Quarter"
            yAxisTitle="Units sold (units)"
          />
        </Panel>

        <Panel title="6. Pie, nine slices" subtitle="Top 5 of 9 shown; shares are of the full total; legend with full names, value and share">
          <ShareChart
            data={pieSlices}
            unit="usd"
            variant="pie"
            controls={{ ...pieControls, onChange: setPieControls }}
            labelHeader="Customer"
            valueHeader="Support spend (US$)"
            summary="Support spend by customer, share of the total"
          />
        </Panel>
        <Panel title="6b. Donut, nine slices" subtitle="Nine or fewer slices start at All">
          <ShareChart
            data={pieSlices}
            unit="usd"
            variant="donut"
            labelHeader="Customer"
            valueHeader="Support spend (US$)"
            summary="Support spend by customer, share of the total"
          />
        </Panel>
      </Box>

      <Typography variant="subtitle2" sx={{ fontWeight: 600, pt: 1 }}>
        7. Each unit kind
      </Typography>
      <Box sx={grid}>
        <Panel title="Rand" subtitle="R 1.2 M on ticks, full value in the tooltip">
          <TrendChart data={unitSeries.zar} x="month" height={200} yScale="fit" unit="zar" xAxisTitle="Month" yAxisTitle="Sales value (R)" series={[{ key: 'v', label: 'Sales value', kind: 'line' }]} />
        </Panel>
        <Panel title="US dollar" subtitle="US$ on ticks and in the tooltip">
          <TrendChart data={unitSeries.usd} x="month" height={200} unit="usd" xAxisTitle="Month" yAxisTitle="Support spend (US$)" series={[{ key: 'v', label: 'Support spend', kind: 'bar' }]} />
        </Panel>
        <Panel title="Units" subtitle="Bare ticks; the title carries the unit">
          <TrendChart data={unitSeries.units} x="month" height={200} unit="units" xAxisTitle="Month" yAxisTitle="Sell-out (units)" series={[{ key: 'v', label: 'Sell-out', kind: 'area' }]} />
        </Panel>
        <Panel title="Percent" subtitle="Ratios 0.42 to 0.97, zoomed to the data">
          <TrendChart data={unitSeries.percent} x="month" height={200} yScale="fit" unit="percent" xAxisTitle="Month" yAxisTitle="Fill rate (%)" series={[{ key: 'v', label: 'Fill rate', kind: 'line' }]} lastPointLabel />
        </Panel>
        <Panel title="Count" subtitle="Plain counts">
          <TrendChart data={unitSeries.count} x="month" height={200} unit="count" xAxisTitle="Month" yAxisTitle="Shipments" series={[{ key: 'v', label: 'Shipments', kind: 'bar' }]} />
        </Panel>
        <Panel title="Weeks, with a threshold" subtitle="Bare ticks, 5.4w labels, 5.4 weeks in the tooltip">
          <RankedBars
            data={coverWeeks}
            unit="weeks"
            sort="asc"
            threshold={{ value: 4, label: '4-week threshold' }}
            summary="Weeks of cover by distributor"
            labelHeader="Distributor"
            valueHeader="Weeks of cover"
            xAxisTitle="Distributor"
            yAxisTitle="Weeks of cover"
          />
        </Panel>
        <Panel title="Days" subtitle="12d labels, 12 days in the tooltip">
          <RankedBars data={podDays} unit="days" summary="Days waiting by state" xAxisTitle="State" yAxisTitle="Waiting (days)" />
        </Panel>
      </Box>

      <Box sx={grid}>
        <Panel title="8. One series over 52 weeks" subtitle="No legend for a single series; the last point is labelled">
          <TrendChart
            data={weeks52}
            x="week"
            height={240}
            unit="units"
            xAxisTitle="Week"
            yAxisTitle="Sell-out (units)"
            lastPointLabel
            series={[{ key: 'sellOut', label: 'Sell-out', kind: 'line' }]}
          />
        </Panel>
        <Panel title="9. Edge cases" subtitle="One category; every value missing (the data table shows a dash)">
          <Stack spacing={2}>
            <CategoryBars data={oneCategory} x="customer" y="value" height={160} unit="units" xAxisTitle="Customer" yAxisTitle="Sell-out (units)" />
            <CategoryBars data={allNulls} x="customer" y="value" height={160} unit="units" xAxisTitle="Customer" yAxisTitle="Sell-out (units)" />
          </Stack>
        </Panel>
      </Box>
    </Stack>
  );
}
