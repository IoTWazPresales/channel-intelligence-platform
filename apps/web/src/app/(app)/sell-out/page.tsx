'use client';

import { Tab, Tabs, ToggleButton, ToggleButtonGroup } from '@mui/material';
import { useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';

import { ChannelOpsInventoryTab } from './ChannelOpsInventoryTab';
import { ChannelOpsMovementsTab } from './ChannelOpsMovementsTab';
import { ChannelOpsOverviewTab } from './ChannelOpsOverviewTab';
import { ChannelOpsKpiCards } from './ChannelOpsKpiCards';
import { INTEL_DEPTH_OPTIONS, useIntelDepth } from './intelDepth';
import { SellOutTab } from './SellOutTab';

export default function ChannelOperationsPage() {
  const [tab, setTab] = useState(0);
  const [depth, setDepth] = useIntelDepth();

  return (
    <>
      <PageHeader
        {...navPageChrome('/sell-out')}
        actions={
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
        }
      />

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
    </>
  );
}
