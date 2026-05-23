'use client';

import CloseIcon from '@mui/icons-material/Close';
import { Box, IconButton, Stack, Typography } from '@mui/material';

import { DsiMappingStewardPanel, type DsiCandidateRow } from './dsi-mapping-steward-panel';

export function DsiCandidateStewardDrawer({
  importJobId,
  candidate,
  planRow,
  onClose,
  onRowActionStart,
  onRowActionEnd,
  onDone,
  onPlanRefresh,
  lookupPeerCandidate,
  onOpenPeerByNormalizedKey,
}: {
  importJobId: number;
  candidate: DsiCandidateRow;
  planRow?: Record<string, unknown> | null;
  onClose: () => void;
  onRowActionStart: (candidateId: number) => void;
  onRowActionEnd: () => void;
  onDone: () => void;
  onPlanRefresh?: () => void | Promise<void>;
  lookupPeerCandidate?: (normalizedKey: string) => DsiCandidateRow | null;
  onOpenPeerByNormalizedKey?: (normalizedKey: string) => void;
}) {
  const title =
    candidate.entity_type === 'distributor_token'
      ? 'Distributor steward'
      : candidate.entity_type === 'product_identifier'
        ? 'Product steward'
        : 'Customer steward';

  return (
    <Box
      component="aside"
      role="complementary"
      aria-label="Candidate steward"
      data-testid="dsi-candidate-steward-drawer"
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
        maxHeight: { xs: 'none', md: '72vh' },
        overflow: 'hidden',
      }}
    >
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ px: 2, py: 1.25, borderBottom: 1, borderColor: 'divider', flexShrink: 0 }}
      >
        <Typography variant="subtitle1">{title}</Typography>
        <IconButton size="small" aria-label="Close steward drawer" onClick={onClose} data-testid="dsi-steward-drawer-close">
          <CloseIcon fontSize="small" />
        </IconButton>
      </Stack>
      <Box sx={{ flex: 1, overflow: 'auto', px: 2, py: 1.5 }}>
        <DsiMappingStewardPanel
          importJobId={importJobId}
          candidate={candidate}
          planRow={planRow}
          onRowActionStart={onRowActionStart}
          onRowActionEnd={onRowActionEnd}
          onDone={onDone}
          onPlanRefresh={onPlanRefresh}
          lookupPeerCandidate={lookupPeerCandidate}
          onOpenPeerByNormalizedKey={onOpenPeerByNormalizedKey}
        />
      </Box>
    </Box>
  );
}
