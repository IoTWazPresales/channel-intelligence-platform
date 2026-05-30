'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';

export type MasterBulkDeletePreviewRow = {
  id: number;
  missing?: boolean;
  label: string | null;
  references: { label: string; count: number }[];
  blocked: boolean;
};

export type MasterBulkDeletePreview = {
  entity_type: string;
  entity_ids: number[];
  missing_entity_ids: number[];
  rows: MasterBulkDeletePreviewRow[];
  blocked_count: number;
  deletable_count: number;
  deletable_ids: number[];
};

export function MasterBulkDeleteImpactDialog({
  open,
  busy,
  preview,
  entityLabel,
  impactAcknowledged,
  onImpactAcknowledgedChange,
  onClose,
  onConfirm,
}: {
  open: boolean;
  busy: boolean;
  preview: MasterBulkDeletePreview | null;
  entityLabel: string;
  impactAcknowledged: boolean;
  onImpactAcknowledgedChange: (v: boolean) => void;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const missing = preview?.missing_entity_ids?.length ?? 0;
  const blocked = preview?.blocked_count ?? 0;
  const deletable = preview?.deletable_count ?? 0;
  const confirmDisabled = busy || !preview || missing > 0 || deletable === 0 || !impactAcknowledged;

  return (
    <Dialog
      open={open}
      onClose={busy ? undefined : onClose}
      maxWidth="sm"
      fullWidth
      data-testid="master-bulk-delete-dialog"
    >
      <DialogTitle>Delete {entityLabel} — impact preview</DialogTitle>
      <DialogContent dividers>
        {busy ? <LinearProgress sx={{ mb: 2 }} /> : null}
        {!preview ? (
          <Typography color="text.secondary">No preview loaded.</Typography>
        ) : (
          <Stack spacing={2}>
            {missing > 0 ? (
              <Alert severity="warning">
                Some ids are no longer present: {preview.missing_entity_ids.join(', ')}. Refresh the grid and try
                again.
              </Alert>
            ) : null}
            <Typography variant="subtitle2">Summary</Typography>
            <Stack component="ul" sx={{ m: 0, pl: 2 }} spacing={0.5}>
              <Typography component="li" variant="body2">
                Selected: {preview.entity_ids.length}
              </Typography>
              <Typography component="li" variant="body2">
                Can delete now: <strong>{deletable}</strong>
              </Typography>
              <Typography component="li" variant="body2">
                Blocked (still referenced): <strong>{blocked}</strong>
              </Typography>
            </Stack>
            {blocked > 0 ? (
              <>
                <Alert severity="warning" data-testid="master-bulk-blocked-alert">
                  Blocked rows will be skipped. Remove dependent data or deselect them before retrying.
                </Alert>
                <Typography variant="subtitle2">Blocked rows</Typography>
                <Stack spacing={1.5}>
                  {preview.rows
                    .filter((r) => !r.missing && r.blocked)
                    .map((r) => (
                      <Stack key={r.id} spacing={0.5}>
                        <Typography variant="body2" fontWeight={600}>
                          {r.label ?? `id ${r.id}`}
                        </Typography>
                        <Box component="ul" sx={{ m: 0, pl: 2 }}>
                          {r.references.map((ref) => (
                            <Typography key={`${r.id}-${ref.label}`} component="li" variant="caption">
                              {ref.label} ({ref.count})
                            </Typography>
                          ))}
                        </Box>
                      </Stack>
                    ))}
                </Stack>
              </>
            ) : null}
            <FormControlLabel
              control={
                <Checkbox
                  checked={impactAcknowledged}
                  onChange={(e) => onImpactAcknowledgedChange(e.target.checked)}
                  disabled={busy}
                  data-testid="master-bulk-impact-ack"
                />
              }
              label={
                deletable > 0
                  ? `I have reviewed the preview and want to permanently delete ${deletable} ${entityLabel}.`
                  : `I have reviewed the preview (no rows can be deleted).`
              }
            />
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Close
        </Button>
        <Button
          color="error"
          variant="contained"
          disabled={confirmDisabled}
          onClick={onConfirm}
          data-testid="master-bulk-confirm-delete"
        >
          Confirm delete
        </Button>
      </DialogActions>
    </Dialog>
  );
}
