'use client';

import { Alert, Box, Button, Paper, Stack, Typography } from '@mui/material';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { Suspense, useMemo } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { DataChrome } from '@/features/data-stewardship/DataChrome';
import { StewardFailureQueue } from '@/features/data-stewardship/StewardFailureQueue';
import { StewardResolveWorkspace } from '@/features/data-stewardship/StewardResolveWorkspace';
import { apiDelete, apiGet, apiPost, apiUrl, authHeaders } from '@/lib/api';

type LegacyRow = {
  id: number;
  entity_type: string;
  raw_value: string;
  status: string;
  confidence_score: number | null;
  job_id: number | null;
};

function parseImportJobId(raw: string | null): { jobId: number | null; invalid: boolean } {
  if (raw == null || raw.trim() === '') {
    return { jobId: null, invalid: false };
  }
  const t = raw.trim();
  if (!/^\d+$/.test(t)) {
    return { jobId: null, invalid: true };
  }
  const n = Number.parseInt(t, 10);
  if (n < 1) {
    return { jobId: null, invalid: true };
  }
  return { jobId: n, invalid: false };
}

function AdminMappingsPageContent() {
  const searchParams = useSearchParams();
  const importJobIdParam = searchParams.get('import_job_id');
  const resolveWorkspace = searchParams.get('workspace') === 'resolve';
  const { jobId: importJobId, invalid: invalidJobIdParam } = useMemo(
    () => parseImportJobId(importJobIdParam),
    [importJobIdParam]
  );

  const qc = useQueryClient();
  const {
    data: legacyData,
    isLoading: legacyLoading,
  } = useQuery({
    queryKey: ['mapping-queue'],
    queryFn: ({ signal }) => apiGet<LegacyRow[]>('/api/v1/mappings/queue', { signal }),
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/mappings/queue/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['mapping-queue'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/mappings/queue/clear-all', { confirm: true }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['mapping-queue'] }),
  });

  const approve = useMutation({
    mutationFn: async ({ id, entityId }: { id: number; entityId: number }) => {
      const res = await fetch(apiUrl(`/api/v1/mappings/queue/${id}/approve?entity_id=${entityId}`), {
        method: 'POST',
        headers: authHeaders(undefined, false),
      });
      return res.json();
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['mapping-queue'] });
    },
  });

  const legacyColDefs: ColDef<LegacyRow>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'entity_type', headerName: 'Entity' },
      { field: 'raw_value', headerName: 'Raw' },
      { field: 'status', headerName: 'Status' },
      { field: 'confidence_score', headerName: 'Confidence' },
      { field: 'job_id', headerName: 'Job' },
      {
        headerName: 'Quick approve (demo)',
        width: 220,
        cellRenderer: (p: { data: LegacyRow }) => (
          <Box sx={{ display: 'flex', gap: 1 }}>
            <Button size="small" onClick={() => approve.mutate({ id: p.data.id, entityId: 1 })}>
              Map → id 1
            </Button>
          </Box>
        ),
      },
      gridDeleteColumn<LegacyRow>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [approve, delRow, delRow.isPending, clearAll.isPending]);

  const legacyRows = legacyData ?? [];

  return (
    <>
      {invalidJobIdParam ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Query parameter <code>import_job_id</code> must be a positive integer. Remove it or fix the URL.
        </Alert>
      ) : null}
      {importJobId != null && !resolveWorkspace ? (
        <Alert severity="info" sx={{ mb: 2 }} data-testid="dsi-job-filter-banner">
          <Typography variant="body2">
            Old job filter <strong>#{importJobId}</strong> — stewarding is on the import workspace, not this queue.{' '}
            <Button
              component={Link}
              href={`/admin/mappings?workspace=resolve&job=${importJobId}`}
              size="small"
              variant="contained"
              sx={{ ml: 1 }}
              data-testid="dsi-open-import-resolution"
            >
              Open DSI resolution workspace
            </Button>
            <Button component={Link} href="/admin/mappings" size="small" variant="outlined" sx={{ ml: 1 }}>
              Clear job filter
            </Button>
          </Typography>
        </Alert>
      ) : null}
      {resolveWorkspace ? <StewardResolveWorkspace /> : <StewardFailureQueue />}
      {resolveWorkspace ? null : (
      <Paper sx={{ p: 2, mt: 3 }} data-testid="legacy-mapping-queue">
        <Typography variant="subtitle2" fontWeight={600} gutterBottom>
          Mapping queue — pipeline state
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Unresolved entity tokens wait here as pipeline state. This is not a restore-or-retire control. Resolve them in
          the resolve workspace.
        </Typography>
        {legacyLoading ? (
          <Typography variant="body2" color="text.secondary">
            Loading legacy rows…
          </Typography>
        ) : legacyRows.length === 0 ? (
          <Typography variant="body2" color="text.secondary" data-testid="legacy-mapping-queue-empty">
            No legacy queue rows.
          </Typography>
        ) : (
          <Stack spacing={1}>
            <EnterpriseDataGrid rowData={legacyRows} columnDefs={legacyColDefs} height={280} />
            <Button
              size="small"
              color="warning"
              disabled={clearAll.isPending}
              onClick={() => {
                if (!window.confirm('Delete every legacy mapping queue row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
            >
              Clear legacy queue
            </Button>
          </Stack>
        )}
      </Paper>
      )}
    </>
  );
}

export default function AdminMappingsPage() {
  return (
    <DataChrome>
      <Suspense
        fallback={
          <Box sx={{ p: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Loading mappings…
            </Typography>
          </Box>
        }
      >
        <AdminMappingsPageContent />
      </Suspense>
    </DataChrome>
  );
}
