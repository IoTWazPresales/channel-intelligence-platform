'use client';

import {
  Alert,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';
import { safeDisplayError } from '@/lib/api';

export type ChannelGeographicEvidenceRow = {
  normalized_token: string;
  raw_token: string;
  guessed_region_code: string;
  row_count: number;
  customer_candidate_count: number;
  customer_candidate_ids: number[];
};

export function DsiChannelGeographicEvidenceSection({ importJobId }: { importJobId: number }) {
  const q = useQuery({
    queryKey: ['dsi-channel-geographic-evidence', importJobId],
    enabled: importJobId > 0,
    refetchOnWindowFocus: false,
    queryFn: ({ signal }) =>
      apiGet<{ import_job_id: number; channels: ChannelGeographicEvidenceRow[] }>(
        `/api/v1/mappings/import-jobs/${importJobId}/dsi-channel-geographic-evidence`,
        { signal }
      ),
  });

  if (q.isLoading) {
    return (
      <Alert severity="info" variant="outlined" data-testid="dsi-channel-geo-evidence-loading">
        Loading channel geographic evidence…
      </Alert>
    );
  }
  if (q.isError) {
    return (
      <Alert severity="error" data-testid="dsi-channel-geo-evidence-error">
        {safeDisplayError(q.error)}
      </Alert>
    );
  }

  const channels = q.data?.channels ?? [];
  if (channels.length === 0) {
    return null;
  }

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="dsi-channel-geographic-evidence">
      <Typography variant="subtitle2" gutterBottom>
        Channel values used as geographic hints
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
        These route-to-market strings look like countries or regions (not catalog channel mapping). They can
        inform region suggestions on customer rows — stewards should register or alias them explicitly.
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>File token</TableCell>
            <TableCell>Detected as</TableCell>
            <TableCell align="right">Rows in file</TableCell>
            <TableCell align="right">Customers</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {channels.map((row) => (
            <TableRow key={row.normalized_token} data-testid={`dsi-ch-geo-ev-${row.normalized_token}`}>
              <TableCell sx={{ wordBreak: 'break-word' }}>
                <Typography variant="body2">{row.raw_token}</Typography>
                <Typography variant="caption" color="text.secondary">
                  normalized: {row.normalized_token}
                </Typography>
              </TableCell>
              <TableCell>{row.guessed_region_code}</TableCell>
              <TableCell align="right">{row.row_count.toLocaleString()}</TableCell>
              <TableCell align="right">{row.customer_candidate_count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  );
}
