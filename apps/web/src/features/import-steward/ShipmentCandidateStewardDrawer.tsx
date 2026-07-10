'use client';

import CloseIcon from '@mui/icons-material/Close';
import { Box, IconButton, Stack, Typography } from '@mui/material';

import type { ShipmentMappingCandidateRow } from './shipmentMappingCandidateDisplay';
import { shipmentEntityChipLabel } from './shipmentMappingCandidateDisplay';
import { ShipmentMappingStewardPanel } from './ShipmentMappingStewardPanel';

/** Shipment steward drawer — layout parity with {@link DsiCandidateStewardDrawer}. */
export function ShipmentCandidateStewardDrawer({
  candidate,
  planRow,
  onClose,
  applyPlanPending,
  onApplyPlanRow,
  rowActionPending,
}: {
  candidate: ShipmentMappingCandidateRow;
  planRow?: Record<string, unknown> | null;
  onClose: () => void;
  applyPlanPending?: boolean;
  onApplyPlanRow?: (candidateId: number) => void;
  rowActionPending?: boolean;
}) {
  return (
    <Box
      component="aside"
      role="complementary"
      aria-label="Shipment candidate steward"
      data-testid="shipment-candidate-steward-drawer"
      sx={{
        width: { xs: '100%', md: '40%' },
        minWidth: { md: 320 },
        maxWidth: '100%',
        flexShrink: 0,
        borderLeft: { md: 1 },
        borderColor: 'divider',
        bgcolor: 'background.paper',
        display: 'flex',
        flexDirection: 'column',
        maxHeight: { xs: 'none', md: 'min(72vh, calc(100vh - 96px))' },
        overflow: 'hidden',
        position: { md: 'sticky' },
        top: { md: 80 },
        alignSelf: { md: 'flex-start' },
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: 2, py: 1.25, borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}
      >
        <Typography variant="subtitle1">
          {shipmentEntityChipLabel(candidate.entity_type)} steward
        </Typography>
        <IconButton
          size="small"
          aria-label="Close steward drawer"
          onClick={onClose}
          data-testid="shipment-steward-drawer-close"
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>
      <Box sx={{ flex: 1, overflow: 'auto', px: 2, py: 1.5 }}>
        <ShipmentMappingStewardPanel
          candidate={candidate}
          planRow={planRow}
          applyPlanPending={applyPlanPending}
          onApplyPlanRow={onApplyPlanRow}
          rowActionPending={rowActionPending}
        />
      </Box>
    </Box>
  );
}
