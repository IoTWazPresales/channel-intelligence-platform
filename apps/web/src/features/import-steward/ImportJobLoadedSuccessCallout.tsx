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
  /** Where the loaded rows can be seen. Defaults to shipment evidence admin (the first importer to use this). */
  viewLink?: { href: string; label: string };
  /** Replaces the default sentence about applying the same file again, when it does not fit the importer. */
  description?: string;
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
  factLayerLabel = 'the records for this import',
  unresolvedNotes = [],
  onStartNewImport,
  testId = 'import-job-loaded-success',
  viewLink = { href: '/admin/shipment-evidence', label: 'Shipment evidence admin' },
  description,
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
          ) is <strong>{stage}</strong>.{' '}
          {description ??
            `Rows were written to ${factLayerLabel}. Applying the same file again updates those rows. The validation record stays on this import.`}
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
            href={viewLink.href}
            data-testid={`${testId}-shipment-evidence`}
          >
            {viewLink.label}
          </Button>
        </Stack>
      </Stack>
    </Alert>
  );
}
