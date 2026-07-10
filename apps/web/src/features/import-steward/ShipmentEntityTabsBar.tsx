'use client';

import { Box, Chip, Stack, Tab, Tabs, Typography } from '@mui/material';

import {
  formatShipmentEntityTabLabel,
  SHIPMENT_ENTITY_TAB_DEFS,
  type ShipmentEntityTabId,
} from './shipmentEntityTabs';

export type ShipmentEntityTabCounts = Record<
  ShipmentEntityTabId,
  { total: number | null; needsWork: number | null }
>;

function ShipmentEntityTabLabel({
  tabId,
  tabLabel,
  total,
  needsWork,
  selected,
}: {
  tabId: ShipmentEntityTabId;
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
        data-testid={`shipment-tab-count-${tabId}`}
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
          data-testid={`shipment-tab-needs-work-${tabId}`}
        />
      ) : null}
    </Stack>
  );
}

export function ShipmentEntityTabsBar({
  activeTab,
  onChange,
  counts,
  busy,
}: {
  activeTab: ShipmentEntityTabId;
  onChange: (tab: ShipmentEntityTabId) => void;
  counts: ShipmentEntityTabCounts;
  busy?: boolean;
}) {
  return (
    <Box
      data-testid="shipment-entity-tabs"
      sx={{
        bgcolor: 'background.paper',
        borderBottom: 2,
        borderColor: 'divider',
        boxShadow: (theme) =>
          theme.palette.mode === 'dark' ? 'inset 0 -1px 0 rgba(255,255,255,0.06)' : 'inset 0 -1px 0 rgba(0,0,0,0.06)',
      }}
    >
      <Tabs
        value={activeTab}
        onChange={(_, value) => onChange(value as ShipmentEntityTabId)}
        variant="scrollable"
        scrollButtons="auto"
        indicatorColor="primary"
        textColor="primary"
        aria-label="Shipment entity resolution"
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
        {SHIPMENT_ENTITY_TAB_DEFS.map((tab) => {
          const { total, needsWork } = counts[tab.id];
          const selected = activeTab === tab.id;
          return (
            <Tab
              key={tab.id}
              value={tab.id}
              disabled={busy}
              aria-label={formatShipmentEntityTabLabel(tab, total, needsWork)}
              label={
                <ShipmentEntityTabLabel
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
