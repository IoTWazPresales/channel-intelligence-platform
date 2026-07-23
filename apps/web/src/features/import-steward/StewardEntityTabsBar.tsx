'use client';

import { Box, Chip, Stack, Tab, Tabs, Typography } from '@mui/material';

export type StewardEntityTabDef<TId extends string = string> = {
  id: TId;
  label: string;
  testId: string;
};

export type StewardEntityTabCounts<TId extends string = string> = Record<
  TId,
  { total: number | null; needsWork: number | null }
>;

function StewardEntityTabLabel({
  tabId,
  tabLabel,
  total,
  needsWork,
  selected,
  testIdPrefix,
}: {
  tabId: string;
  tabLabel: string;
  total: number | null;
  needsWork: number | null;
  selected: boolean;
  testIdPrefix: string;
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
        data-testid={`${testIdPrefix}-tab-count-${tabId}`}
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
          data-testid={`${testIdPrefix}-tab-needs-work-${tabId}`}
        />
      ) : null}
    </Stack>
  );
}

/**
 * Shared entity-resolution tabs bar (DSI / shipment / CPOR).
 * Call sites keep their own tab-def configs; this component owns the chrome only.
 */
export function StewardEntityTabsBar<TId extends string>({
  tabs,
  activeTab,
  onChange,
  counts,
  busy,
  testIdPrefix,
  ariaLabel,
  formatTabAriaLabel,
}: {
  tabs: readonly StewardEntityTabDef<TId>[];
  activeTab: TId;
  onChange: (tab: TId) => void;
  counts: StewardEntityTabCounts<TId>;
  busy?: boolean;
  /** Prefix for root + count/needs-work test ids (e.g. `dsi`, `shipment`, `cpor-historical`). */
  testIdPrefix: string;
  ariaLabel: string;
  formatTabAriaLabel: (
    tab: StewardEntityTabDef<TId>,
    total: number | null,
    needsWork: number | null
  ) => string;
}) {
  return (
    <Box
      data-testid={`${testIdPrefix}-entity-tabs`}
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
        onChange={(_, value) => onChange(value as TId)}
        variant="scrollable"
        scrollButtons="auto"
        indicatorColor="primary"
        textColor="primary"
        aria-label={ariaLabel}
        sx={{
          minHeight: 52,
          px: { xs: 0, sm: 0.5 },
          '& .MuiTabs-flexContainer': {
            gap: { xs: 0, sm: 1 },
          },
          '& .MuiTab-root': {
            minHeight: 52,
            px: { xs: 1.5, sm: 2.5 },
            py: 1.25,
            textTransform: 'none',
            opacity: 0.72,
            transition: 'opacity 0.15s ease, color 0.15s ease',
            '&:hover': {
              opacity: 0.92,
            },
            '&.Mui-selected': {
              opacity: 1,
            },
          },
          '& .MuiTabs-indicator': {
            height: 3,
            borderRadius: '3px 3px 0 0',
          },
        }}
      >
        {tabs.map((tab) => {
          const { total, needsWork } = counts[tab.id];
          const selected = activeTab === tab.id;
          return (
            <Tab
              key={tab.id}
              value={tab.id}
              disabled={busy}
              aria-label={formatTabAriaLabel(tab, total, needsWork)}
              label={
                <StewardEntityTabLabel
                  tabId={tab.id}
                  tabLabel={tab.label}
                  total={total}
                  needsWork={needsWork}
                  selected={selected}
                  testIdPrefix={testIdPrefix}
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
