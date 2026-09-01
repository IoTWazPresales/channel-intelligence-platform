'use client';

import { Tab, Tabs, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { useState } from 'react';

import { ChannelOpsInventoryTab } from '@/app/(app)/sell-out/ChannelOpsInventoryTab';
import { ChannelOpsKpiCards } from '@/app/(app)/sell-out/ChannelOpsKpiCards';
import { ChannelOpsMovementsTab } from '@/app/(app)/sell-out/ChannelOpsMovementsTab';
import { ChannelOpsOverviewTab } from '@/app/(app)/sell-out/ChannelOpsOverviewTab';
import { INTEL_DEPTH_OPTIONS, useIntelDepth } from '@/app/(app)/sell-out/intelDepth';
import { SellOutTab } from '@/app/(app)/sell-out/SellOutTab';

/** Sell-out / movement lens body — mounted inside Stock container without duplicate chrome. */
export function ChannelOpsStockWorkspace() {
  const [tab, setTab] = useState(0);
  const [depth, setDepth] = useIntelDepth();

  return (
    <div data-testid="stock-movement-lens">
      <ToggleButtonGroup
        exclusive
        size="small"
        value={depth}
        onChange={(_e, v) => v && setDepth(v)}
        aria-label="Intelligence depth"
        sx={{ mb: 2 }}
      >
        {INTEL_DEPTH_OPTIONS.map((o) => (
          <ToggleButton key={o.value} value={o.value}>
            {o.label}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      <ChannelOpsKpiCards />

      <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Overview" />
        <Tab label="Sell-out" />
        <Tab label="Inventory" />
        <Tab label="Movements" />
      </Tabs>

      {tab === 0 && <ChannelOpsOverviewTab depth={depth} />}
      {tab === 1 && <SellOutTab depth={depth} />}
      {tab === 2 && <ChannelOpsInventoryTab depth={depth} />}
      {tab === 3 && <ChannelOpsMovementsTab depth={depth} />}
    </div>
  );
}
