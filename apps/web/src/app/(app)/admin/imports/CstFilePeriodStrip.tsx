'use client';

import { Alert, Chip, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';

export type CstFilePeriodRow = {
  filename: string;
  excluded?: boolean;
  period_start_date?: string | null;
  file_inferred?: string | null;
  source?: string | null;
  flags?: string[];
  error?: string | null;
};

export type CstFilePeriodStripProps = {
  files: CstFilePeriodRow[];
};

/** Read-only per-file period review after CST batch (or multi-raw) process. */
export function CstFilePeriodStrip({ files }: CstFilePeriodStripProps) {
  if (!files.length) return null;
  return (
    <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="cst-file-period-strip">
      <Typography variant="subtitle2" gutterBottom>
        File periods
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        Period comes from file content first (e.g. Transaction Week). Filename is fallback only.
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>File</TableCell>
            <TableCell>Period (Mon)</TableCell>
            <TableCell>Source</TableCell>
            <TableCell>Flags</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {files.map((f) => (
            <TableRow key={f.filename}>
              <TableCell>{f.filename}</TableCell>
              <TableCell>{f.period_start_date ?? (f.excluded ? 'excluded' : '—')}</TableCell>
              <TableCell>{f.source ?? (f.error ? 'error' : '—')}</TableCell>
              <TableCell>
                <Stack direction="row" flexWrap="wrap" gap={0.5}>
                  {(f.flags ?? []).map((flag) => (
                    <Chip
                      key={flag}
                      size="small"
                      label={flag}
                      color={flag.includes('conflict') || flag.includes('unknown') ? 'warning' : 'default'}
                      variant="outlined"
                    />
                  ))}
                  {f.error ? <Chip size="small" color="error" label="parse_error" /> : null}
                </Stack>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {files.some((f) => (f.flags ?? []).includes('period_conflict')) ? (
        <Alert severity="warning" sx={{ mt: 1 }}>
          Period conflict: steward-declared week kept; check the file strip before apply.
        </Alert>
      ) : null}
    </Paper>
  );
}
