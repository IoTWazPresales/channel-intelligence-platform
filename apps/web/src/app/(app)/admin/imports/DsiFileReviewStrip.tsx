'use client';

import {
  Alert,
  Checkbox,
  FormControlLabel,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useMutation } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { apiPost, safeDisplayError } from '@/lib/api';

export type DsiFileReviewStripProps = {
  jobId: number;
  filenames: string[];
  rowSubtotals?: Record<string, number> | null;
  excludedFiles?: string[] | null;
  jobLoaded?: boolean;
  onChanged?: () => void;
};

export function DsiFileReviewStrip({
  jobId,
  filenames,
  rowSubtotals,
  excludedFiles,
  jobLoaded = false,
  onChanged,
}: DsiFileReviewStripProps) {
  const initial = useMemo(() => new Set(excludedFiles ?? []), [excludedFiles]);
  const [excluded, setExcluded] = useState<Set<string>>(initial);

  const mutation = useMutation({
    mutationFn: async (next: string[]) => {
      await apiPost(`/api/v1/imports/jobs/${jobId}/dsi-file-exclusions`, {
        excluded_filenames: next,
      });
    },
    onSuccess: () => onChanged?.(),
  });

  if (!filenames.length) return null;

  const toggle = (name: string) => {
    if (jobLoaded) return;
    const next = new Set(excluded);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    setExcluded(next);
    void mutation.mutateAsync([...next]);
  };

  return (
    <Paper variant="outlined" sx={{ p: 2 }} data-testid="dsi-file-review-strip">
      <Stack spacing={1}>
        <Typography variant="subtitle2">Batch files in this job</Typography>
        <Typography variant="caption" color="text.secondary">
          Exclude a file to drop it before re-validate (clears staging). Does not block apply for remaining files.
        </Typography>
        {mutation.isError ? <Alert severity="error">{safeDisplayError(mutation.error)}</Alert> : null}
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Include</TableCell>
              <TableCell>File</TableCell>
              <TableCell align="right">Rows</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filenames.map((name) => (
              <TableRow key={name}>
                <TableCell padding="checkbox">
                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={!excluded.has(name)}
                        disabled={jobLoaded || mutation.isPending}
                        onChange={() => toggle(name)}
                        inputProps={{ 'aria-label': `include ${name}` }}
                      />
                    }
                    label=""
                  />
                </TableCell>
                <TableCell>{name}</TableCell>
                <TableCell align="right">{rowSubtotals?.[name] ?? '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Stack>
    </Paper>
  );
}
