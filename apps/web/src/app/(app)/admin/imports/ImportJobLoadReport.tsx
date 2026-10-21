'use client';

import { Alert, AlertTitle, Box, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

/**
 * N-0111 (Warren 2026-10-16): a load that drops rows says so. Rows read, loaded and not loaded,
 * with the reason per category, for one sell-through or distributor job.
 */
export type ImportLoadReportReason = {
  reason: string;
  label: string;
  rows: number;
  partly_loaded: boolean;
};

export type ImportLoadReport = {
  kind: string;
  rows_read: number;
  rows_loaded: number;
  rows_partly_loaded: number;
  rows_not_loaded: number;
  identical_copies_counted_once: number;
  not_loaded: ImportLoadReportReason[];
  files_not_read: Array<{ filename: string; reason: string; error?: string }>;
  files_excluded: number;
};

export type ImportLoadReportResponse = {
  job_id: number;
  status: string;
  display_status: string;
  report: ImportLoadReport | null;
};

export const importJobLoadReportQueryKey = (jobId: number) => ['import-job-load-report', jobId] as const;

export function ImportJobLoadReportView({ data }: { data: ImportLoadReportResponse }) {
  const r = data.report;
  if (!r) return null;
  const short = r.rows_not_loaded + r.rows_partly_loaded;
  const severity = short > 0 || r.files_not_read.length > 0 ? 'warning' : 'success';
  return (
    <Alert severity={severity} data-testid="import-load-report" sx={{ '& .MuiAlert-message': { width: '100%' } }}>
      <AlertTitle>{data.display_status}</AlertTitle>
      <Typography variant="body2">
        Rows read {r.rows_read.toLocaleString()} · loaded {r.rows_loaded.toLocaleString()} · not loaded{' '}
        {r.rows_not_loaded.toLocaleString()}
        {r.rows_partly_loaded > 0 ? ` · partly loaded ${r.rows_partly_loaded.toLocaleString()}` : ''}
      </Typography>
      {r.not_loaded.length > 0 ? (
        <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5 }} aria-label="Rows not loaded, by reason">
          {r.not_loaded.map((item) => (
            <li key={item.reason}>
              <Typography variant="body2">
                {item.label}: {item.rows.toLocaleString()} row{item.rows === 1 ? '' : 's'}
                {item.partly_loaded ? ' (partly loaded)' : ''}
              </Typography>
            </li>
          ))}
        </Box>
      ) : null}
      {r.files_not_read.length > 0 ? (
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          Files not read: {r.files_not_read.map((f) => f.filename).join(', ')}
        </Typography>
      ) : null}
      {r.identical_copies_counted_once > 0 ? (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
          {`${r.identical_copies_counted_once.toLocaleString()} identical ${
            r.identical_copies_counted_once === 1 ? 'copy' : 'copies'
          } of a row counted once (loaded).`}
        </Typography>
      ) : null}
      {r.files_excluded > 0 ? (
        <Typography variant="caption" color="text.secondary" display="block">
          {r.files_excluded} file{r.files_excluded === 1 ? '' : 's'} left out by choice.
        </Typography>
      ) : null}
    </Alert>
  );
}

export function useImportJobLoadReport(importJobId: number | null) {
  return useQuery({
    queryKey: importJobLoadReportQueryKey(importJobId ?? 0),
    queryFn: ({ signal }) =>
      apiGet<ImportLoadReportResponse>(`/api/v1/imports/jobs/${importJobId}/load-report`, { signal }),
    enabled: importJobId != null && importJobId > 0,
    refetchInterval: 15_000,
  });
}

export function ImportJobLoadReport({ importJobId }: { importJobId: number }) {
  const { data } = useImportJobLoadReport(importJobId);
  if (!data) return null;
  return <ImportJobLoadReportView data={data} />;
}
