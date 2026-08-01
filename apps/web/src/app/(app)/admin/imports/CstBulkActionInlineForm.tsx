'use client';

import { Alert, Button, Stack, TextField, Typography } from '@mui/material';

import { safeDisplayError } from '@/lib/api';

import { StewardPendingButton } from '@/features/import-steward/StewardPendingButton';
import type { StewardBulkTestIds } from '@/features/import-steward/stewardEngine.types';
import type { useStewardBulkSteward } from '@/features/import-steward/useStewardBulkSteward';

import type { CstEntityTabId } from './cstImportSteward.config';

type BulkSteward = ReturnType<typeof useStewardBulkSteward>;

export function CstBulkActionInlineForm({
  bulk,
  entityTab,
  onCancel,
  testIds,
}: {
  bulk: BulkSteward;
  entityTab: CstEntityTabId;
  onCancel: () => void;
  testIds: StewardBulkTestIds;
}) {
  const {
    bulkAction,
    setBulkAction,
    bulkProductId,
    setBulkProductId,
    bulkPreview,
    bulkApply,
    bulkFormReady,
    applyReady,
  } = bulk;

  const targetLabel = entityTab === 'location' ? 'Location entity id' : 'Product entity id';

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
          variant={bulkAction === 'resolve_product' ? 'contained' : 'outlined'}
          onClick={() => setBulkAction('resolve_product')}
          data-testid="cst-bulk-action-map"
        >
          Map to master
        </Button>
        <Button
          size="small"
          variant={bulkAction === 'ignore' ? 'contained' : 'outlined'}
          onClick={() => setBulkAction('ignore')}
          data-testid="cst-bulk-action-ignore"
        >
          Ignore
        </Button>
      </Stack>
      {bulkAction === 'resolve_product' ? (
        <TextField
          size="small"
          label={targetLabel}
          value={bulkProductId}
          onChange={(e) => setBulkProductId(e.target.value)}
          sx={{ maxWidth: 280 }}
          data-testid="cst-bulk-entity-id"
        />
      ) : null}
      <Typography variant="caption" color="text.secondary">
        Preview shows per-row ok/skip, then Apply. Map uses one shared target for all selected tokens.
      </Typography>
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
