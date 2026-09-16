'use client';

import {
  Alert,
  Chip,
  Link,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import NextLink from 'next/link';
import { useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';

import { AdminChrome } from '@/features/administration/AdminChrome';
import { apiGet, safeDisplayError } from '@/lib/api';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

type FailedJob = {
  id: number;
  template_slug: string | null;
  status: string;
  stage: string;
  file_name: string;
  error_summary: string | null;
  created_at: string | null;
  completed_at: string | null;
  updated_at: string | null;
};

type OpsOverview = {
  tenant_id: string;
  as_of: string;
  readiness?: {
    status: string;
    database?: string | null;
    ok?: boolean;
  };
  counts: {
    failed_open: number;
    running_or_pending: number;
    completed_last_14d: number;
  };
  failed_jobs: FailedJob[];
  links: Record<string, string>;
};

export default function AdminOpsPage() {
  const { data: me, isError: meError } = useCurrentUser();
  const role = String(me?.role || '').toLowerCase();
  const allowed = role === 'admin' || role === 'steward';

  const overview = useQuery({
    queryKey: ['admin', 'ops', 'overview'],
    queryFn: () => apiGet<OpsOverview>('/api/v1/admin/ops/overview'),
    enabled: allowed,
    retry: false,
    refetchInterval: 30_000,
  });

  const failedJobCols = useMemo<ColDef<FailedJob>[]>(
    () => [
      {
        field: 'id',
        headerName: 'Job',
        minWidth: 90,
        cellRenderer: (p: { data?: FailedJob }) =>
          p.data ? (
            <Link component={NextLink} href={`/admin/imports?jobId=${p.data.id}`}>
              #{p.data.id}
            </Link>
          ) : null,
      },
      { field: 'template_slug', headerName: 'Template', minWidth: 160, valueFormatter: (p) => p.value ?? '—' },
      { field: 'stage', headerName: 'Stage', minWidth: 110 },
      { field: 'file_name', headerName: 'File', flex: 1, minWidth: 160 },
      { field: 'error_summary', headerName: 'Error', flex: 1.4, minWidth: 200, valueFormatter: (p) => p.value ?? '—' },
    ],
    [],
  );

  if (meError || (me && !allowed)) {
    return (
      <AdminChrome>
        <Alert severity="warning">Admin or steward role required.</Alert>
      </AdminChrome>
    );
  }

  const counts = overview.data?.counts;
  const readyOk = overview.data?.readiness?.status === 'ready';
  const failedJobs = overview.data?.failed_jobs ?? [];

  return (
    <AdminChrome>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 720 }}>
        Local multi-user readiness: API readiness, failed import jobs, and links to steward audit. Backup / restore
        runbooks live in <code>docs/BACKUP_AND_DR.md</code>.
      </Typography>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <Paper sx={{ p: 2, flex: 1 }} data-testid="ops-health-card">
          <Typography variant="subtitle2" gutterBottom>
            API readiness
          </Typography>
          {overview.isLoading ? (
            <Typography color="text.secondary">Checking…</Typography>
          ) : (
            <>
              <Chip
                size="small"
                color={readyOk ? 'success' : 'error'}
                label={overview.data?.readiness?.status ?? 'unknown'}
                sx={{ mb: 1 }}
              />
              <Typography variant="body2" color="text.secondary">
                database: {overview.data?.readiness?.database ?? '—'}
              </Typography>
              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                Direct API probes: <code>/health</code> · <code>/health/ready</code> (port 8001)
              </Typography>
            </>
          )}
        </Paper>
        <Paper sx={{ p: 2, flex: 1 }} data-testid="ops-counts-card">
          <Typography variant="subtitle2" gutterBottom>
            Import jobs (tenant {overview.data?.tenant_id ?? '…'})
          </Typography>
          <Typography variant="body2">Failed open: {counts?.failed_open ?? '—'}</Typography>
          <Typography variant="body2">Running / pending: {counts?.running_or_pending ?? '—'}</Typography>
          <Typography variant="body2">Completed (14d): {counts?.completed_last_14d ?? '—'}</Typography>
          <Typography variant="caption" display="block" sx={{ mt: 1 }}>
            <Link component={NextLink} href="/admin/imports">
              Import Center
            </Link>
            {' · '}
            <Link component={NextLink} href="/admin/steward-audit">
              Steward audit
            </Link>
          </Typography>
        </Paper>
      </Stack>

      {overview.isError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {safeDisplayError(overview.error)}
        </Alert>
      ) : null}

      <Paper sx={{ p: 2 }} data-testid="ops-failed-jobs">
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Failed import jobs
        </Typography>
        <EnterpriseDataGrid
          rowData={failedJobs}
          columnDefs={failedJobCols}
          height={360}
          gridOptions={{ overlayNoRowsTemplate: 'No open failed jobs for this tenant.' }}
        />
      </Paper>
    </AdminChrome>
  );
}
