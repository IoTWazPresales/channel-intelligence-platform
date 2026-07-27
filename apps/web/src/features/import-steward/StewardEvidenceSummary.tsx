'use client';

import { Box, Chip, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';

function formatNum(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return String(n);
}

/**
 * Shared S6 drawer evidence summary — neutral props only (D-017).
 * Consumers pass domain extras (e.g. case codes) via `extras`.
 */
export function StewardEvidenceSummary({
  sampleRawValues,
  affectedRowCount,
  totalUnits,
  totalReportedValue,
  extras,
  testId = 'steward-evidence-summary',
}: {
  sampleRawValues?: string[] | null;
  affectedRowCount?: number | null;
  totalUnits?: number | null;
  totalReportedValue?: number | null;
  extras?: ReactNode;
  testId?: string;
}) {
  const samples = (sampleRawValues ?? []).map((s) => String(s).trim()).filter(Boolean);

  return (
    <Stack spacing={1} data-testid={testId}>
      <Typography variant="subtitle2">Evidence</Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        {affectedRowCount != null ? (
          <Chip
            size="small"
            variant="outlined"
            label={`${affectedRowCount} row${affectedRowCount === 1 ? '' : 's'}`}
            data-testid={`${testId}-rows`}
          />
        ) : null}
        <Chip
          size="small"
          variant="outlined"
          label={`Units ${formatNum(totalUnits)}`}
          data-testid={`${testId}-units`}
        />
        <Chip
          size="small"
          variant="outlined"
          label={`Value ${formatNum(totalReportedValue)}`}
          data-testid={`${testId}-value`}
        />
      </Stack>
      <Box>
        <Typography variant="caption" color="text.secondary" component="div">
          Sample raw values
        </Typography>
        {samples.length === 0 ? (
          <Typography variant="body2" color="text.secondary" data-testid={`${testId}-samples-empty`}>
            —
          </Typography>
        ) : (
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap data-testid={`${testId}-samples`}>
            {samples.map((s) => (
              <Chip key={s} size="small" label={s} />
            ))}
          </Stack>
        )}
      </Box>
      {extras ? <Box data-testid={`${testId}-extras`}>{extras}</Box> : null}
    </Stack>
  );
}
