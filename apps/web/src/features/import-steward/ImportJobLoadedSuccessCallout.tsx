'use client';

import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import { Alert, Button, Stack, Typography } from '@mui/material';
import Link from 'next/link';

export type ImportJobLoadedSuccessCalloutProps = {
  importJobId: number;
  templateLabel: string;
  fileName?: string | null;
  status: string;
  stage: string;
  /** Human label for the fact table / layer written on apply (e.g. inbound shipment facts). */
  factLayerLabel?: string;
  unresolvedNotes?: string[];
  onStartNewImport?: () => void;
  testId?: string;
};

/** Job finished apply and promoted to terminal `loaded` stage. */
export function importJobApplyIsLoaded(stage: string, status: string): boolean {
  const st = (stage || '').trim();
  const sts = (status || '').trim().toLowerCase();
  return st === 'loaded' && (sts === 'completed' || sts === 'completed_with_errors');
}

/**
 * Success callout when an import job has already applied and reached `loaded`.
 * Shared across importers — shipment uses it today; DSI/historical lineup can adopt later.
 */
export function ImportJobLoadedSuccessCallout({
  importJobId,
  templateLabel,
  fileName,
  status,
  stage,
  factLayerLabel = 'canonical fact tables',
  unresolvedNotes = [],
  onStartNewImport,
  testId = 'import-job-loaded-success',
}: ImportJobLoadedSuccessCalloutProps) {
  if (!importJobApplyIsLoaded(stage, status)) return null;

  const sts = (status || '').trim().toLowerCase();
  const severity = sts === 'completed_with_errors' ? 'warning' : 'success';
  const title =
    sts === 'completed_with_errors' ? 'Apply finished with warnings' : 'Apply complete — job loaded';

  return (
    <Alert
      severity={severity}
      icon={<CheckCircleOutlineIcon fontSize="inherit" />}
      data-testid={testId}
      sx={{ alignItems: 'flex-start' }}
    >
      <Stack spacing={1}>
        <Typography variant="subtitle2" component="div">
          {title}
        </Typography>
        <Typography variant="body2">
          Import job <strong>#{importJobId}</strong> ({templateLabel}
          {fileName ? (
            <>
              {' '}
              · <em>{fileName}</em>
            </>
          ) : null}
          ) reached stage <strong>{stage}</strong>. Facts were upserted into {factLayerLabel} using each row&apos;s{' '}
          <strong>source_key</strong> (latest apply wins). Evidence from validate is still preserved on the import job.
        </Typography>
        {unresolvedNotes.length > 0 ? (
          <Typography variant="body2" component="div">
            {unresolvedNotes.map((note) => (
              <span key={note}>
                {note}
                <br />
              </span>
            ))}
          </Typography>
        ) : null}
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {onStartNewImport ? (
            <Button size="small" variant="outlined" onClick={onStartNewImport} data-testid={`${testId}-start-new`}>
              Start new import
            </Button>
          ) : (
            <Button
              size="small"
              variant="outlined"
              component={Link}
              href="/admin/imports"
              data-testid={`${testId}-start-new-link`}
            >
              Start new import
            </Button>
          )}
          <Button
            size="small"
            variant="text"
            component={Link}
            href={`/admin/shipment-evidence`}
            data-testid={`${testId}-shipment-evidence`}
          >
            Shipment evidence admin
          </Button>
        </Stack>
      </Stack>
    </Alert>
  );
}
