'use client';

import {
  Alert,
  Button,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';

import { DsiPendingButton } from './DsiPendingButton';
import type { useShipmentBulkSteward } from './useShipmentBulkSteward';

type BulkSteward = ReturnType<typeof useShipmentBulkSteward>;

export function ShipmentBulkStewardSection({
  bulkMode,
  selectedIds,
  bulk,
  stewardOverlayBusy,
}: {
  bulkMode: BulkTableSelectionMode;
  selectedIds: number[];
  bulk: BulkSteward;
  stewardOverlayBusy: boolean;
}) {
  if (bulkMode !== 'selecting' || selectedIds.length === 0) return null;

  const {
    bulkAction,
    setBulkAction,
    bulkCustomerId,
    setBulkCustomerId,
    bulkDistributorId,
    setBulkDistributorId,
    bulkProvNamesById,
    setBulkProvName,
    bulkApplySummary,
    bulkFormReady,
    bulkApply,
  } = bulk;

  return (
    <Stack spacing={1.5} data-testid="shipment-bulk-steward-section">
      {bulkApplySummary ? (
        <Alert severity="info" onClose={() => bulk.setBulkApplySummary(null)}>
          {bulkApplySummary}
        </Alert>
      ) : null}
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button
          size="small"
          variant={bulkAction === 'map_customer' ? 'contained' : 'outlined'}
          onClick={() => setBulkAction('map_customer')}
        >
          Map channel partners
        </Button>
        <Button
          size="small"
          variant={bulkAction === 'create_provisional_customer' ? 'contained' : 'outlined'}
          onClick={() => setBulkAction('create_provisional_customer')}
        >
          Provisional channel partners
        </Button>
        <Button
          size="small"
          variant={bulkAction === 'map_distributor' ? 'contained' : 'outlined'}
          onClick={() => setBulkAction('map_distributor')}
        >
          Map distributors
        </Button>
        <Button
          size="small"
          variant={bulkAction === 'ignore' ? 'contained' : 'outlined'}
          onClick={() => setBulkAction('ignore')}
        >
          Reject / ignore
        </Button>
      </Stack>
      {bulkAction === 'map_customer' ? (
        <TextField
          size="small"
          label="Customer ID"
          value={bulkCustomerId}
          onChange={(e) => setBulkCustomerId(e.target.value)}
          sx={{ maxWidth: 280 }}
        />
      ) : null}
      {bulkAction === 'map_distributor' ? (
        <TextField
          size="small"
          label="Distributor ID"
          value={bulkDistributorId}
          onChange={(e) => setBulkDistributorId(e.target.value)}
          sx={{ maxWidth: 280 }}
        />
      ) : null}
      {bulkAction === 'create_provisional_customer' ? (
        <Stack spacing={1}>
          <Typography variant="caption" color="text.secondary">
            Display name per selected candidate
          </Typography>
          {selectedIds.map((id) => (
            <TextField
              key={id}
              size="small"
              label={`Candidate #${id}`}
              value={bulkProvNamesById[id] ?? ''}
              onChange={(e) => setBulkProvName(id, e.target.value)}
            />
          ))}
        </Stack>
      ) : null}
      <DsiPendingButton
        variant="contained"
        size="small"
        pending={bulkApply.isPending}
        pendingLabel="Applying…"
        disabled={!bulkFormReady || stewardOverlayBusy || bulkApply.isPending}
        onClick={() => void bulkApply.mutateAsync().catch(() => {})}
        data-testid="shipment-bulk-apply"
      >
        Apply bulk action ({selectedIds.length})
      </DsiPendingButton>
    </Stack>
  );
}
