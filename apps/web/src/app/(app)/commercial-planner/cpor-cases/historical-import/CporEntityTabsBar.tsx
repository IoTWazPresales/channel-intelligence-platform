'use client';

import { Box, Chip, Stack, Tab, Tabs, Typography } from '@mui/material';

import {
  CPOR_ENTITY_TAB_DEFS,
  formatCporEntityTabLabel,
  type CporEntityTabId,
} from './cporHistoricalSteward.config';

export type CporEntityTabCounts = Record<
  CporEntityTabId,
  { total: number | null; needsWork: number | null }
>;

function CporEntityTabLabel({
  tabId,
  tabLabel,
  total,
  needsWork,
  selected,
}: {
  tabId: CporEntityTabId;
  tabLabel: string;
  total: number | null;
  needsWork: number | null;
  selected: boolean;
}) {
  const countText = total == null ? '…' : String(total);
  const showNeedsWork = needsWork != null && needsWork > 0;

  return (
    <Stack direction="row" spacing={1} alignItems="center" component="span" sx={{ py: 0.25 }}>
      <Typography
        component="span"
        variant="body2"
        sx={{
          fontWeight: selected ? 700 : 500,
          color: selected ? 'text.primary' : 'text.secondary',
          lineHeight: 1.3,
        }}
      >
        {tabLabel}
      </Typography>
      <Typography
        component="span"
        variant="body2"
        sx={{
          fontWeight: 600,
          color: selected ? 'primary.main' : 'text.secondary',
          fontVariantNumeric: 'tabular-nums',
        }}
        data-testid={`cpor-historical-tab-count-${tabId}`}
      >
        ({countText})
      </Typography>
      {showNeedsWork ? (
        <Chip
          size="small"
          label={needsWork === 1 ? '1 needs work' : `${needsWork} needs work`}
          color="warning"
          variant={selected ? 'filled' : 'outlined'}
          sx={{ height: 22, '& .MuiChip-label': { px: 1, fontSize: '0.7rem', fontWeight: 600 } }}
          data-testid={`cpor-historical-tab-needs-work-${tabId}`}
        />
      ) : null}
    </Stack>
  );
}

export function CporEntityTabsBar({
  activeTab,
  onChange,
  counts,
  busy,
}: {
  activeTab: CporEntityTabId;
  onChange: (tab: CporEntityTabId) => void;
  counts: CporEntityTabCounts;
  busy?: boolean;
}) {
  return (
    <Box
      data-testid="cpor-historical-entity-tabs"
      sx={{
        bgcolor: 'background.paper',
        borderBottom: 2,
        borderColor: 'divider',
        boxShadow: (theme) =>
          theme.palette.mode === 'dark'
            ? 'inset 0 -1px 0 rgba(255,255,255,0.06)'
            : 'inset 0 -1px 0 rgba(0,0,0,0.06)',
      }}
    >
      <Tabs
        value={activeTab}
        onChange={(_, value) => onChange(value as CporEntityTabId)}
        variant="scrollable"
        scrollButtons="auto"
        indicatorColor="primary"
        textColor="primary"
        aria-label="CPOR historical entity resolution"
        sx={{
          minHeight: 52,
          px: { xs: 0, sm: 0.5 },
          '& .MuiTabs-flexContainer': { gap: { xs: 0, sm: 1 } },
          '& .MuiTab-root': {
            minHeight: 52,
            px: { xs: 1.5, sm: 2.5 },
            py: 1.25,
            textTransform: 'none',
            opacity: 0.72,
            '&.Mui-selected': { opacity: 1 },
          },
          '& .MuiTabs-indicator': { height: 3, borderRadius: '3px 3px 0 0' },
        }}
      >
        {CPOR_ENTITY_TAB_DEFS.map((tab) => {
          const { total, needsWork } = counts[tab.id];
          const selected = activeTab === tab.id;
          return (
            <Tab
              key={tab.id}
              value={tab.id}
              disabled={busy}
              aria-label={formatCporEntityTabLabel(tab, total, needsWork)}
              label={
                <CporEntityTabLabel
                  tabId={tab.id}
                  tabLabel={tab.label}
                  total={total}
                  needsWork={needsWork}
                  selected={selected}
                />
              }
              data-testid={tab.testId}
            />
          );
        })}
      </Tabs>
    </Box>
  );
}
