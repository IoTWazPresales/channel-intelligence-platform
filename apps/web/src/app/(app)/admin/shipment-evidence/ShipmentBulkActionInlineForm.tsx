'use client';

import {
  Alert,
  Button,
  Stack,
  TextField,
  Typography,
} from '@mui/material';

import { safeDisplayError } from '@/lib/api';

import { StewardPendingButton } from '@/features/import-steward/StewardPendingButton';
import type { StewardBulkTestIds } from '@/features/import-steward/stewardEngine.types';
import type { useStewardBulkSteward } from '@/features/import-steward/useStewardBulkSteward';

type BulkSteward = ReturnType<typeof useStewardBulkSteward>;

export function ShipmentBulkActionInlineForm({
  bulk,
  selectedIds,
  bulkProvNamesById,
  setBulkProvName,
  onCancel,
  testIds,
}: {
  bulk: BulkSteward;
  selectedIds: number[];
  bulkProvNamesById: Record<number, string>;
  setBulkProvName: (id: number, name: string) => void;
  onCancel: () => void;
  testIds: StewardBulkTestIds;
}) {
  const {
    bulkAction,
    setBulkAction,
    bulkCustomerId,
    setBulkCustomerId,
    bulkDistributorId,
    setBulkDistributorId,
    bulkPreview,
    bulkApply,
    bulkFormReady,
    applyReady,
  } = bulk;

  return (
    <Stack
      spacing={2}
      data-testid={testIds.actionForm}
      sx={{
        p: 2,
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        bgcolor: 'action.hover',
      }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
        <Typography variant="subtitle2">Bulk steward</Typography>
        <Button size="small" onClick={onCancel} data-testid={testIds.formCancel}>
          Cancel
        </Button>
      </Stack>
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
          <Typography variant="caption" color="text.secondary" data-testid={testIds.provCustomerHint}>
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
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <StewardPendingButton
          variant="outlined"
          pending={bulkPreview.isPending}
          pendingLabel="Previewing…"
          disabled={!bulkFormReady || bulkApply.isPending}
          onClick={() => void bulkPreview.mutateAsync().catch(() => {})}
          data-testid={testIds.previewInline}
        >
          Preview bulk steward
        </StewardPendingButton>
        <StewardPendingButton
          variant="contained"
          pending={bulkApply.isPending}
          pendingLabel="Applying…"
          disabled={!applyReady || !bulkFormReady || bulkPreview.isPending}
          onClick={() => void bulkApply.mutateAsync().catch(() => {})}
          data-testid={testIds.apply}
        >
          Apply bulk steward
        </StewardPendingButton>
      </Stack>
      {bulkPreview.isError ? (
        <Alert severity="error" data-testid={testIds.previewError}>
          {safeDisplayError(bulkPreview.error)}
        </Alert>
      ) : null}
      {bulkApply.isError ? (
        <Alert severity="error" data-testid={testIds.applyError}>
          {safeDisplayError(bulkApply.error)}
        </Alert>
      ) : null}
    </Stack>
  );
}
