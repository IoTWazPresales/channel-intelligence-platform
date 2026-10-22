'use client';

import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';

import { JobIdEntry } from './ImportJobBulkDeleteImpactDialog';

export type ImportJobArchiveAction = 'archive' | 'unarchive';

export type ImportJobArchivePreviewJob = {
  id: number;
  file_name?: string | null;
  template_slug?: string | null;
  status?: string | null;
  stage?: string | null;
  created_at?: string | null;
  archived_at?: string | null;
  will_change: boolean;
};

export type ImportJobArchivePreview = {
  action: ImportJobArchiveAction;
  job_ids: number[];
  missing_job_ids: number[];
  jobs: ImportJobArchivePreviewJob[];
  to_change: number;
  unchanged: number;
};

function day(iso?: string | null): string {
  return iso ? iso.slice(0, 10) : '';
}

/** N-0113: archive or unarchive import jobs by id. Only the archived date changes; no data row does. */
export function ImportJobArchiveDialog({
  open,
  action,
  busy,
  preview,
  initialIds = [],
  onPreviewIds,
  onClose,
  onConfirm,
}: {
  open: boolean;
  action: ImportJobArchiveAction;
  busy: boolean;
  preview: ImportJobArchivePreview | null;
  /** Ids selected in the grid, shown in the box so they can be edited before previewing. */
  initialIds?: number[];
  onPreviewIds: (ids: number[]) => void;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const verb = action === 'archive' ? 'Archive' : 'Unarchive';
  const jobs = preview?.jobs ?? [];
  const missing = preview?.missing_job_ids ?? [];
  const toChange = preview?.to_change ?? 0;
  const confirmDisabled = busy || !preview || missing.length > 0 || toChange === 0;

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="md" fullWidth data-testid="import-job-archive-dialog">
      <DialogTitle>{verb} import jobs</DialogTitle>
      <DialogContent dividers>
        {busy ? <LinearProgress sx={{ mb: 2 }} /> : null}
        <Stack spacing={2}>
          <Typography variant="body2">
            {action === 'archive'
              ? 'Archiving hides a job from the import list and from the failed-import counts. Its status and the data it loaded stay as they are, and you can unarchive it.'
              : 'Unarchiving shows the job in the import list again, and in the failed-import counts if it failed. Nothing else changes.'}
          </Typography>
          <JobIdEntry
            key={initialIds.join(',')}
            busy={busy}
            onPreview={onPreviewIds}
            initialText={initialIds.join(', ')}
            ariaLabel={`Job ids to ${action}`}
            testId="archive-job-id-entry"
            previewTestId="preview-archive-job-ids"
          />
          {preview ? (
            <>
              {missing.length > 0 ? (
                <Alert severity="warning">
                  These job ids do not exist: {missing.join(', ')}. Remove them and preview again.
                </Alert>
              ) : null}
              <Typography variant="body2" data-testid="archive-summary">
                {toChange} job{toChange === 1 ? '' : 's'} will be {action === 'archive' ? 'archived' : 'unarchived'}
                {preview.unchanged > 0
                  ? `; ${preview.unchanged} ${preview.unchanged === 1 ? 'is' : 'are'} already ${action === 'archive' ? 'archived' : 'not archived'} and stay${preview.unchanged === 1 ? 's' : ''} as ${preview.unchanged === 1 ? 'it is' : 'they are'}.`
                  : '.'}
              </Typography>
              <Stack spacing={0.75} data-testid="archive-jobs">
                {jobs.map((job) => (
                  <Box key={job.id} sx={{ borderLeft: 3, borderColor: job.will_change ? 'primary.main' : 'divider', pl: 1.5 }}>
                    <Typography variant="subtitle2">
                      Job {job.id}
                      {job.file_name ? ` — ${job.file_name}` : ''}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {[job.template_slug, [job.status, job.stage].filter(Boolean).join(' / '), day(job.created_at)]
                        .filter(Boolean)
                        .join(' · ')}
                      {job.archived_at ? ` · archived ${day(job.archived_at)}` : ''}
                      {job.will_change ? '' : action === 'archive' ? ' · already archived' : ' · not archived'}
                    </Typography>
                  </Box>
                ))}
              </Stack>
            </>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Close
        </Button>
        <Button variant="contained" disabled={confirmDisabled} onClick={onConfirm} data-testid="confirm-archive">
          {verb} {toChange} job{toChange === 1 ? '' : 's'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
