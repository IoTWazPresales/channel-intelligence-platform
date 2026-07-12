'use client';

import {
  Autocomplete,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Tab,
  Tabs,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';

import { ChannelOpsInventoryTab } from './ChannelOpsInventoryTab';
import { ChannelOpsMovementsTab } from './ChannelOpsMovementsTab';
import { ChannelOpsOverviewTab } from './ChannelOpsOverviewTab';
import { ChannelOpsKpiCards } from './ChannelOpsKpiCards';
import { INTEL_DEPTH_OPTIONS, useIntelDepth, type PeriodGrain } from './intelDepth';
import { SellOutTab } from './SellOutTab';

type DistHit = { id: number; distributor_code: string; distributor_name: string };

export default function ChannelOperationsPage() {
  const [tab, setTab] = useState(0);
  const [depth, setDepth] = useIntelDepth();
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);
  const [periodGrain, setPeriodGrain] = useState<PeriodGrain>('quarter');
  const [weeks, setWeeks] = useState(13);
  const [businessUnit, setBusinessUnit] = useState('');

  const { data: filterOptions } = useQuery({
    queryKey: ['sellout-filter-options'],
    queryFn: ({ signal }) =>
      apiGet<{ distributors: DistHit[] }>('/api/v1/sellout/filter-options', { signal }),
  });

  const distributorId = distributorPick?.id ?? null;
  const requiresDistributor = tab === 2 || tab === 3;
  const bu = businessUnit.trim() || null;

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Commercial' }, { label: 'Channel Operations' }]}
        title="Channel Operations"
        action={
          <ToggleButtonGroup
            exclusive
            size="small"
            value={depth}
            onChange={(_e, v) => v && setDepth(v)}
            aria-label="Intelligence depth"
          >
            {INTEL_DEPTH_OPTIONS.map((o) => (
              <ToggleButton key={o.value} value={o.value}>
                {o.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        }
      />

      <ChannelOpsKpiCards
        distributorId={distributorId}
        businessUnit={bu}
        periodGrain={periodGrain}
        weeks={weeks}
      />

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <Autocomplete
          sx={{ minWidth: 280, flex: 1 }}
          size="small"
          options={filterOptions?.distributors ?? []}
          value={distributorPick}
          onChange={(_e, v) => setDistributorPick(v)}
          getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => (
            <TextField
              {...params}
              label={requiresDistributor ? 'Distributor (required for this tab)' : 'Distributor'}
              placeholder="All distributors"
              required={requiresDistributor}
              inputProps={{ ...params.inputProps, 'data-testid': 'channel-ops-distributor' }}
            />
          )}
        />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="channel-ops-period-grain-label">Period</InputLabel>
          <Select
            labelId="channel-ops-period-grain-label"
            label="Period"
            value={periodGrain}
            onChange={(e) => setPeriodGrain(e.target.value as PeriodGrain)}
            data-testid="channel-ops-period-grain"
          >
            <MenuItem value="quarter">This quarter</MenuItem>
            <MenuItem value="year">Year to date</MenuItem>
            <MenuItem value="rolling_weeks">Rolling weeks</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel id="channel-ops-weeks-label">Chart weeks</InputLabel>
          <Select
            labelId="channel-ops-weeks-label"
            label="Chart weeks"
            value={weeks}
            onChange={(e) => setWeeks(Number(e.target.value))}
            data-testid="channel-ops-weeks"
          >
            <MenuItem value={13}>13</MenuItem>
            <MenuItem value={26}>26</MenuItem>
            <MenuItem value={52}>52</MenuItem>
          </Select>
        </FormControl>
        <TextField
          size="small"
          label="Business unit"
          value={businessUnit}
          onChange={(e) => setBusinessUnit(e.target.value)}
          placeholder="All BUs"
          sx={{ minWidth: 160 }}
          inputProps={{ 'data-testid': 'channel-ops-bu' }}
        />
      </Stack>

      <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Overview" />
        <Tab label="Sell-out" />
        <Tab label="Inventory" />
        <Tab label="Movements" />
      </Tabs>

      {tab === 0 && (
        <ChannelOpsOverviewTab
          depth={depth}
          distributorId={distributorId}
          businessUnit={bu}
          weeks={weeks}
          periodGrain={periodGrain}
        />
      )}
      {tab === 1 && (
        <SellOutTab depth={depth} distributorId={distributorId} businessUnit={bu} />
      )}
      {tab === 2 && <ChannelOpsInventoryTab depth={depth} distributorId={distributorId} />}
      {tab === 3 && <ChannelOpsMovementsTab depth={depth} distributorId={distributorId} />}
    </>
  );
}
