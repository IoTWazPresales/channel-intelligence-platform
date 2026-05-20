'use client';

import {
  Alert,
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

export type ImportJobBulkDeletePreview = {
  job_ids: number[];
  missing_job_ids?: number[];
  counts: Record<string, number>;
  risky: Record<string, number>;
  storage_keys_total?: number;
  storage_keys_sample?: string[];
};

export function ImportJobBulkDeleteImpactDialog({
  open,
  busy,
  preview,
  deleteSemanticArtifacts,
  onDeleteSemanticArtifactsChange,
  impactAcknowledged,
  onImpactAcknowledgedChange,
  onClose,
  onConfirm,
}: {
  open: boolean;
  busy: boolean;
  preview: ImportJobBulkDeletePreview | null;
  deleteSemanticArtifacts: boolean;
  onDeleteSemanticArtifactsChange: (v: boolean) => void;
  impactAcknowledged: boolean;
  onImpactAcknowledgedChange: (v: boolean) => void;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const c = preview?.counts ?? {};
  const risky = preview?.risky ?? {};
  const aliasTotal = (risky.customer_source_token_aliases ?? 0) + (risky.distributor_source_token_aliases ?? 0);
  const confirmDisabled =
    busy ||
    !preview ||
    (preview.missing_job_ids?.length ?? 0) > 0 ||
    (!deleteSemanticArtifacts && aliasTotal > 0) ||
    !impactAcknowledged;

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth data-testid="import-job-bulk-delete-dialog">
      <DialogTitle>Delete import jobs — impact preview</DialogTitle>
      <DialogContent dividers>
        {busy ? <LinearProgress sx={{ mb: 2 }} /> : null}
        {!preview ? (
          <Typography color="text.secondary">No preview loaded.</Typography>
        ) : (
          <Stack spacing={2}>
            {(preview.missing_job_ids?.length ?? 0) > 0 ? (
              <Alert severity="warning">
                Some job ids are no longer present: {preview.missing_job_ids?.join(', ')}. Refresh the grid and try again.
              </Alert>
            ) : null}
            <Typography variant="subtitle2">Directly linked artifacts (will be removed or cleared)</Typography>
            <Stack component="ul" sx={{ m: 0, pl: 2 }} spacing={0.5}>
              <Typography component="li" variant="body2">
                Import jobs (matched): {c.import_jobs ?? 0} (requested {c.import_jobs_requested ?? preview.job_ids.length})
              </Typography>
              <Typography component="li" variant="body2">
                Raw file metadata rows: {c.raw_file_metadata_rows ?? 0} (stored files: {preview.storage_keys_total ?? 0}{' '}
                object{preview.storage_keys_total === 1 ? '' : 's'})
              </Typography>
              <Typography component="li" variant="body2">
                Import row results: {c.import_row_result_rows ?? 0}
              </Typography>
              <Typography component="li" variant="body2">
                DSI staging lines: {c.dsi_staging_rows ?? 0}
              </Typography>
              <Typography component="li" variant="body2">
                DSI mapping candidates: {c.dsi_mapping_candidate_rows ?? 0}
              </Typography>
              <Typography component="li" variant="body2">
                Fact sales sell-out (source_import_job_id): {c.fact_sales_sellout_rows ?? 0}
              </Typography>
              <Typography component="li" variant="body2">
                Fact distributor inventory (source_import_job_id): {c.fact_inventory_distributor_rows ?? 0}
              </Typography>
              <Typography component="li" variant="body2">
                Other linked rows (mapping queue, historical lineup, commercial cases, catalog pointers, competitor
                prices): entity queue {c.entity_mapping_queue_rows ?? 0}, HL headers {c.historical_lineup_header_rows ?? 0},
                HL lines {c.historical_lineup_line_rows ?? 0}, commercial cases {c.commercial_lineup_case_rows ?? 0},
                catalog products {c.catalog_products_pointing_at_jobs ?? 0}, competitor prices{' '}
                {c.fact_competitor_price_rows ?? 0}
              </Typography>
            </Stack>
            <Alert severity={aliasTotal > 0 ? 'warning' : 'info'} data-testid="risky-artifacts-alert">
              <Typography variant="subtitle2" gutterBottom>
                Risky / semantic artifacts (steward aliases)
              </Typography>
              <Typography variant="body2">
                Customer token aliases: {risky.customer_source_token_aliases ?? 0}. Distributor token aliases:{' '}
                {risky.distributor_source_token_aliases ?? 0}.
              </Typography>
              {aliasTotal > 0 ? (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  These are not removed unless you opt in below. With opt-in, aliases tied to these jobs are deleted in
                  the same transaction.
                </Typography>
              ) : (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  No steward aliases reference these jobs by creation id.
                </Typography>
              )}
            </Alert>
            <FormControlLabel
              control={
                <Checkbox
                  checked={deleteSemanticArtifacts}
                  onChange={(e) => onDeleteSemanticArtifactsChange(e.target.checked)}
                  disabled={busy || aliasTotal === 0}
                  data-testid="delete-semantic-checkbox"
                />
              }
              label="Also delete steward token aliases created from these jobs"
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={impactAcknowledged}
                  onChange={(e) => onImpactAcknowledgedChange(e.target.checked)}
                  disabled={busy}
                  data-testid="impact-ack-checkbox"
                />
              }
              label="I have reviewed the counts above and want to permanently delete these jobs and linked artifacts."
            />
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Close
        </Button>
        <Button color="error" variant="contained" disabled={confirmDisabled} onClick={onConfirm} data-testid="confirm-delete">
          Confirm delete
        </Button>
      </DialogActions>
    </Dialog>
  );
}
