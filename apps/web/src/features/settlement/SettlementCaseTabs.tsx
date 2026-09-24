'use client';

import { Box, Tab, Tabs } from '@mui/material';
import { useId, useState } from 'react';

import { CporPaymentEvidencePanel } from '@/app/(app)/commercial-planner/cpor-cases/[id]/CporPaymentEvidencePanel';
import { CporPromoLoadPanel } from '@/app/(app)/commercial-planner/cpor-cases/[id]/CporPromoLoadPanel';
import { CporEventsPanel } from '@/features/cpor/CporEventsPanel';
import { CporExportsPanel } from '@/features/cpor/CporExportsPanel';
import { CporUsdPivotPanel } from '@/features/cpor/CporUsdPivotPanel';

export type SettlementCaseTabKey = 'pivot' | 'events' | 'exports' | 'promo-load' | 'payments';

const TABS: ReadonlyArray<{ key: SettlementCaseTabKey; label: string }> = [
  { key: 'pivot', label: 'USD pivot' },
  { key: 'events', label: 'Events' },
  { key: 'exports', label: 'Exports' },
  { key: 'promo-load', label: 'Promo load' },
  { key: 'payments', label: 'Payments / recon' },
];

/**
 * Case-detail tabs under the settlement desk. These five surfaces lived only in the unmounted
 * `CporCaseWorkspace` (BACKLOG-202) — promo-load recon among them, a shipped A2 deliverable
 * (BACKLOG-093) nobody could reach. Only the active tab mounts, so each panel's query fires lazily.
 */
export function SettlementCaseTabs({
  caseId,
  roeSnapshot,
  defaultTab = 'pivot',
}: {
  caseId: number;
  roeSnapshot?: number | null;
  defaultTab?: SettlementCaseTabKey;
}) {
  const [tab, setTab] = useState<SettlementCaseTabKey>(defaultTab);
  const idBase = useId();
  const tabId = (key: SettlementCaseTabKey) => `${idBase}-tab-${key}`;
  const panelId = `${idBase}-panel`;

  return (
    <Box data-testid="settlement-case-tabs">
      <Tabs
        value={tab}
        onChange={(_e, v: SettlementCaseTabKey) => setTab(v)}
        variant="scrollable"
        allowScrollButtonsMobile
        aria-label="Case detail"
        sx={{
          borderBottom: '1px solid',
          borderColor: 'divider',
          '& .MuiTab-root.Mui-focusVisible': {
            outline: '2px solid',
            outlineColor: 'primary.main',
            outlineOffset: '-2px',
          },
        }}
      >
        {TABS.map((t) => (
          <Tab
            key={t.key}
            value={t.key}
            label={t.label}
            id={tabId(t.key)}
            aria-controls={panelId}
            data-testid={`settlement-tab-${t.key}`}
          />
        ))}
      </Tabs>
      <Box
        role="tabpanel"
        id={panelId}
        aria-labelledby={tabId(tab)}
        sx={{ pt: 2 }}
        data-testid={`settlement-tabpanel-${tab}`}
      >
        {tab === 'pivot' ? <CporUsdPivotPanel caseId={caseId} roeSnapshot={roeSnapshot} /> : null}
        {tab === 'events' ? <CporEventsPanel caseId={caseId} /> : null}
        {tab === 'exports' ? <CporExportsPanel caseId={caseId} /> : null}
        {tab === 'promo-load' ? <CporPromoLoadPanel caseId={caseId} /> : null}
        {tab === 'payments' ? <CporPaymentEvidencePanel caseId={caseId} /> : null}
      </Box>
    </Box>
  );
}
