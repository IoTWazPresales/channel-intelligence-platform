'use client';

import { useState } from 'react';
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
  TextField,
  Typography,
} from '@mui/material';

export type ImportJobBulkDeleteJob = {
  id: number;
  file_name?: string | null;
  template_slug?: string | null;
  status?: string | null;
  stage?: string | null;
  created_at?: string | null;
  counts: Record<string, number>;
};

export type ImportJobBulkDeletePreview = {
  job_ids: number[];
  missing_job_ids?: number[];
  /** N-0112: what each job removes, brings back and keeps. */
  jobs?: ImportJobBulkDeleteJob[];
  counts: Record<string, number>;
  risky: Record<string, number>;
  recomputed?: { customers?: number; distributors?: number; superseded_records_relinked?: number };
  storage_keys_total?: number;
  storage_keys_sample?: string[];
  max_jobs?: number;
};

export const IMPORT_JOB_DELETE_MAX = 200;

/** Plain words for each count, in the order they are listed. */
const COUNT_LABELS: [string, string][] = [
  ['sellthrough_rows_removed', 'Sell-through rows removed'],
  ['sellthrough_figures_restored', 'Sell-through figures brought back from the earlier load'],
  ['sellthrough_figures_cleared', 'Sell-through figures cleared (no earlier load had them)'],
  ['sellthrough_figures_kept_later', 'Sell-through figures a later load has replaced (the later figures stay)'],
  ['fact_sales_sellout_rows_removed', 'Distributor sales lines removed'],
  ['fact_sales_sellout_rows_restored', 'Distributor sales lines brought back from the earlier load'],
  ['fact_sales_sellout_kept_later', 'Distributor sales lines a later load has replaced (the later lines stay)'],
  ['fact_returns_rows_removed', 'Distributor returns lines removed'],
  ['fact_returns_rows_restored', 'Distributor returns lines brought back from the earlier load'],
  ['fact_returns_kept_later', 'Distributor returns lines a later load has replaced (the later lines stay)'],
  ['fact_inventory_distributor_rows_removed', 'Distributor stock rows removed'],
  ['fact_inventory_distributor_rows_restored', 'Distributor stock rows brought back from the earlier load'],
  ['fact_inbound_shipment_rows_removed', 'Shipment lines removed'],
  ['fact_inbound_shipment_rows_restored', 'Shipment lines brought back from the earlier load'],
  ['fact_competitor_price_rows', 'Competitor prices removed'],
  ['report_slots_reopened', 'Expected sell-through reports marked not received again'],
  ['superseded_records_removed', 'Records of replaced figures removed'],
  ['cst_staging_rows', 'Sell-through staged rows removed'],
  ['dsi_staging_rows', 'Distributor staged rows removed'],
  ['shipment_evidence_line_rows', 'Shipment staged rows removed'],
  ['historical_lineup_header_rows', 'Historical lineup uploads removed'],
  ['historical_lineup_line_rows', 'Historical lineup lines removed'],
  ['dsi_mapping_candidate_rows', 'Mapping candidates removed'],
  ['entity_mapping_queue_rows', 'Mapping queue items removed'],
  ['import_row_result_rows', 'Row results removed'],
  ['raw_file_metadata_rows', 'Stored files removed'],
  ['commercial_lineup_case_rows', 'Lineup cases kept (link to the job cleared)'],
  ['catalog_products_pointing_at_jobs', 'Catalogue products kept (link to the job cleared)'],
  ['cpor_claim_evidence_line_kept', 'Claim evidence lines kept (link to the job cleared)'],
  ['cpor_payment_evidence_kept', 'Payment evidence kept (link to the job cleared)'],
  ['cst_listing_seed_kept', 'Listing seeds kept (link to the job cleared)'],
  ['customer_sellthrough_layout_kept', 'Column layouts kept (link to the job cleared)'],
];
const ALIAS_KEYS = [
  'customer_source_token_aliases',
  'distributor_source_token_aliases',
  'channel_source_token_aliases',
  'region_source_token_aliases',
];

/** Job ids typed or pasted in any form: "1164, 1184 1199" or one per line. */
export function parseJobIds(raw: string): number[] {
  const seen = new Set<number>();
  for (const part of raw.split(/[^0-9]+/)) {
    if (!part) continue;
    const n = Number(part);
    if (Number.isSafeInteger(n) && n > 0) seen.add(n);
  }
  return [...seen];
}

function jobLines(counts: Record<string, number>): string[] {
  const lines = COUNT_LABELS.filter(([k]) => (counts[k] ?? 0) > 0).map(([k, label]) => `${label}: ${counts[k]}`);
  const aliases = ALIAS_KEYS.reduce((n, k) => n + (counts[k] ?? 0), 0);
  if (aliases > 0) lines.push(`Learned aliases: ${aliases}`);
  return lines;
}

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
  onPreviewIds,
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
  /** When given, the dialog offers a box to preview jobs by id (any job, not only the newest 100). */
  onPreviewIds?: (ids: number[]) => void;
}) {
  const [idText, setIdText] = useState('');
  const typedIds = parseJobIds(idText);
  const tooMany = typedIds.length > IMPORT_JOB_DELETE_MAX;
  const c = preview?.counts ?? {};
  const risky = preview?.risky ?? {};
  const aliasTotal = ALIAS_KEYS.reduce((n, k) => n + (risky[k] ?? 0), 0);
  const keptLater =
    (c.sellthrough_figures_kept_later ?? 0) +
    (c.fact_sales_sellout_kept_later ?? 0) +
    (c.fact_returns_kept_later ?? 0);
  const jobs = preview?.jobs ?? [];
  const confirmDisabled =
    busy || !preview || jobs.length === 0 || (preview.missing_job_ids?.length ?? 0) > 0 || !impactAcknowledged;

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="md" fullWidth data-testid="import-job-bulk-delete-dialog">
      <DialogTitle>Delete import jobs — impact preview</DialogTitle>
      <DialogContent dividers>
        {busy ? <LinearProgress sx={{ mb: 2 }} /> : null}
        <Stack spacing={2}>
          {onPreviewIds ? (
            <Stack spacing={1} data-testid="job-id-entry">
              <TextField
                label="Job ids"
                placeholder="1164, 1184, 1199 or one per line"
                value={idText}
                onChange={(e) => setIdText(e.target.value)}
                multiline
                minRows={2}
                maxRows={6}
                size="small"
                disabled={busy}
                error={tooMany}
                helperText={
                  tooMany
                    ? `${typedIds.length} ids: preview up to ${IMPORT_JOB_DELETE_MAX} at a time.`
                    : `${typedIds.length} job id${typedIds.length === 1 ? '' : 's'}. Any job, not only the newest 100 in the list. Up to ${IMPORT_JOB_DELETE_MAX} at a time.`
                }
                inputProps={{ 'aria-label': 'Job ids to delete' }}
              />
              <Box>
                <Button
                  variant="outlined"
                  onClick={() => onPreviewIds(typedIds)}
                  disabled={busy || typedIds.length === 0 || tooMany}
                  data-testid="preview-job-ids"
                >
                  Preview these jobs
                </Button>
              </Box>
            </Stack>
          ) : null}
          {!preview ? (
            onPreviewIds ? null : <Typography color="text.secondary">No preview loaded.</Typography>
          ) : (
            <>
              {(preview.missing_job_ids?.length ?? 0) > 0 ? (
                <Alert severity="warning">
                  These job ids do not exist: {preview.missing_job_ids?.join(', ')}. Remove them and preview again.
                </Alert>
              ) : null}
              <Typography variant="body2">
                Deleting a job removes the data it loaded. Where it replaced figures from an earlier load, the earlier
                figures come back. Everything happens together or not at all.
              </Typography>
              {keptLater > 0 ? (
                <Alert severity="info" data-testid="kept-later-alert">
                  A later load has since replaced some of these figures ({keptLater}). The later figures stay; only
                  the record of what they replaced is moved back to the earlier load.
                </Alert>
              ) : null}
              <Stack spacing={1.5} data-testid="per-job-counts">
                {jobs.map((job) => {
                  const lines = jobLines(job.counts);
                  return (
                    <Box key={job.id} sx={{ borderLeft: 3, borderColor: 'divider', pl: 1.5 }}>
                      <Typography variant="subtitle2">
                        Job {job.id}
                        {job.file_name ? ` — ${job.file_name}` : ''}
                      </Typography>
                      {lines.length ? (
                        <Stack component="ul" sx={{ m: 0, pl: 2 }} spacing={0.25}>
                          {lines.map((line) => (
                            <Typography key={line} component="li" variant="body2">
                              {line}
                            </Typography>
                          ))}
                        </Stack>
                      ) : (
                        <Typography variant="body2" color="text.secondary">
                          Only the job itself (it loaded nothing).
                        </Typography>
                      )}
                    </Box>
                  );
                })}
              </Stack>
              {preview.recomputed && ((preview.recomputed.customers ?? 0) > 0 || (preview.recomputed.distributors ?? 0) > 0) ? (
                <Typography variant="body2" color="text.secondary">
                  Afterwards stock positions are recomputed for {preview.recomputed.customers ?? 0} customer
                  {(preview.recomputed.customers ?? 0) === 1 ? '' : 's'}, and velocity, forecasts and stock checks for{' '}
                  {preview.recomputed.distributors ?? 0} distributor{(preview.recomputed.distributors ?? 0) === 1 ? '' : 's'}.
                </Typography>
              ) : null}
              <Alert severity="info" data-testid="risky-artifacts-alert">
                <Typography variant="body2">
                  {aliasTotal > 0
                    ? `${aliasTotal} learned alias${aliasTotal === 1 ? '' : 'es'} came from these jobs. They are kept, so the names stay matched, unless you tick the box below.`
                    : 'No learned aliases came from these jobs.'}
                </Typography>
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
                label="Also delete the learned aliases that came from these jobs"
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
                label={`I have read the counts above and want to delete ${jobs.length} job${jobs.length === 1 ? '' : 's'} and the data ${jobs.length === 1 ? 'it' : 'they'} loaded.`}
              />
            </>
          )}
        </Stack>
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
