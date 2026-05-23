'use client';

import { Alert, Box, Button, Paper, Stack, Typography } from '@mui/material';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { Suspense, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { DSI_STEWARD_CONFIG, invalidateDsiImportJobStewardQueries } from '@/features/import-steward';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPost, apiUrl } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type LegacyRow = {
  id: number;
  entity_type: string;
  raw_value: string;
  status: string;
  confidence_score: number | null;
  job_id: number | null;
};

type DsiMappingCandidateRow = {
  id: number;
  import_job_id: number;
  source_definition_id: number | null;
  entity_type: string;
  normalized_key: string;
  dealer_group_token: string | null;
  row_count: number;
  total_units: number | null;
  total_reported_value: number | null;
  sample_raw_values: string[] | null;
  suggested_entity_id: number | null;
  match_reason: string | null;
  confidence_score: number | null;
  status: string;
  context: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
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
  const { jobId: importJobId, invalid: invalidJobIdParam } = useMemo(
    () => parseImportJobId(importJobIdParam),
    [importJobIdParam]
  );

  const qc = useQueryClient();
  const {
    data: legacyData,
    isLoading: legacyLoading,
    isError: legacyIsError,
    error: legacyError,
    refetch: refetchLegacy,
  } = useQuery({
    queryKey: ['mapping-queue'],
    queryFn: ({ signal }) => apiGet<LegacyRow[]>('/api/v1/mappings/queue', { signal }),
  });

  const dsiQueryKey =
    importJobId != null ? DSI_STEWARD_CONFIG.mappingCandidatesListQueryKey(importJobId) : (['dsi-mapping-candidates', null] as const);
  const {
    data: dsiData,
    isLoading: dsiLoading,
    isError: dsiIsError,
    error: dsiError,
    refetch: refetchDsi,
    isFetched: dsiFetched,
  } = useQuery({
    queryKey: dsiQueryKey,
    queryFn: ({ signal }) =>
      apiGet<{ items: DsiMappingCandidateRow[]; total: number }>(
        `/api/v1/mappings/import-jobs/${importJobId}/distributor-si-candidates?limit=1000`,
        { signal }
      ).then((r) => r.items),
    enabled: importJobId != null,
  });

  const approve = useMutation({
    mutationFn: async ({ id, entityId }: { id: number; entityId: number }) => {
      const res = await fetch(apiUrl(`/api/v1/mappings/queue/${id}/approve?entity_id=${entityId}`), {
        method: 'POST',
        headers: { 'X-User-Role': 'data_steward' },
      });
      return res.json();
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['mapping-queue'] });
      if (importJobId != null) {
        invalidateDsiImportJobStewardQueries(qc, importJobId);
      }
    },
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/mappings/queue/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['mapping-queue'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/mappings/queue/clear-all', { confirm: true }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['mapping-queue'] }),
  });
  const revalidateJob = useMutation({
    mutationFn: async () => {
      if (importJobId == null) throw new Error('Missing import job');
      const res = await apiPost<{ ok: boolean; async?: boolean; task_id?: string | null }>(
        `/api/v1/mappings/import-jobs/${importJobId}/revalidate-distributor-sales-inventory`
      );
      if (res.async) {
        const { notifyDsiAsyncPipelineStarted } = await import('@/features/import-steward/dsiAsyncPipelineRun');
        notifyDsiAsyncPipelineStarted(qc, importJobId, { taskId: res.task_id });
      }
      return res;
    },
    onSuccess: (res) => {
      if (!res.async) {
        void qc.invalidateQueries({ queryKey: dsiQueryKey });
        void refetchDsi();
      }
      void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
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
  const dsiRows = dsiData ?? [];

  const combinedLoading = legacyLoading || (importJobId != null && dsiLoading);
  const combinedError = legacyIsError || (importJobId != null && dsiIsError);
  const combinedErr = legacyIsError ? legacyError : dsiError;

  const legacyEmpty = legacyRows.length === 0;
  const dsiEmpty = importJobId == null ? true : dsiFetched && dsiRows.length === 0;
  const hasDsiGroups = importJobId != null && dsiRows.length > 0;

  const showGlobalEmpty = !combinedLoading && !combinedError && legacyEmpty && dsiEmpty;

  const emptyBlock = useMemo(() => {
    if (importJobId != null && dsiFetched && legacyEmpty && dsiRows.length === 0 && !dsiIsError) {
      return {
        title: `No grouped import candidates for job #${importJobId}`,
        description:
          'This import job has no persisted DSI mapping candidate rows (they may have been cleared, or the job id does not match a distributor sales & inventory validation).',
        primary: { label: 'Open import job workspace', href: `/admin/imports?job=${importJobId}` },
        secondary: { label: 'Clear job filter', href: '/admin/mappings' },
      } as const;
    }
    return {
      title: 'Mapping queue is empty',
      description:
        'Nothing is waiting in the legacy EntityMappingQueue. For distributor sales & inventory, after validation use the Mapping queue link from Data & Imports — it includes import_job_id so grouped DSI candidates appear here.',
      primary: { label: 'Data & imports', href: '/admin/imports' },
      secondary: { label: 'Getting started', href: '/getting-started' },
    } as const;
  }, [importJobId, dsiFetched, legacyEmpty, dsiRows.length, dsiIsError]);

  const refreshAll = () => {
    void qc.invalidateQueries({ queryKey: ['mapping-queue'] });
    if (importJobId != null) void qc.invalidateQueries({ queryKey: dsiQueryKey });
    void refetchLegacy();
    if (importJobId != null) void refetchDsi();
  };

  return (
    <>
      <PageHeader crumbs={[{ label: 'Admin' }, { label: 'Mappings' }]} title="Manual mapping queue" />
      <Paper sx={{ p: 2 }}>
        {invalidJobIdParam ? (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Query parameter <code>import_job_id</code> must be a positive integer. Remove it or fix the URL.
          </Alert>
        ) : null}
        {importJobId != null ? (
          <Alert severity="info" sx={{ mb: 2 }} data-testid="dsi-job-filter-banner">
            <Typography variant="body2">
              Showing DSI grouped import candidates for import job <strong>#{importJobId}</strong>.{' '}
              <Button component={Link} href="/admin/mappings" size="small" variant="outlined" sx={{ ml: 1 }}>
                Clear job filter
              </Button>
            </Typography>
          </Alert>
        ) : null}
        <ModuleDataSection
          intro={
            <>
              <strong>Legacy queue</strong> lists unresolved matches from <code>EntityMappingQueue</code> (one row per
              gap). <strong>DSI grouped import candidates</strong> are aggregated tokens from distributor sales &amp;
              inventory validation (<code>ImportEntityMappingCandidate</code>) and load when you open this page with{' '}
              <code>?import_job_id=…</code> (for example from Data &amp; Imports after validation).
            </>
          }
          isLoading={combinedLoading}
          isError={combinedError}
          error={toQueryError(combinedErr)}
          onRetry={() => {
            void refetchLegacy();
            if (importJobId != null) void refetchDsi();
          }}
          isEmpty={showGlobalEmpty}
          empty={emptyBlock}
          toolbar={
            <ModuleGridToolbar
              onRefresh={refreshAll}
              onClearAll={() => {
                if (!window.confirm('Delete every legacy mapping queue row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              importsHref="/admin/imports"
              busy={approve.isPending || delRow.isPending || clearAll.isPending}
            />
          }
        >
          <Stack spacing={3}>
            <Box>
              <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                Legacy mapping queue (EntityMappingQueue)
              </Typography>
              {legacyEmpty ? (
                <Typography variant="body2" color="text.secondary">
                  No legacy queue rows{importJobId != null ? ' for this view.' : '.'}
                </Typography>
              ) : (
                <EnterpriseDataGrid rowData={legacyRows} columnDefs={legacyColDefs} height={360} />
              )}
            </Box>

            {importJobId != null ? (
              <Box data-testid="dsi-candidates-section">
                <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                  DSI grouped import candidates
                </Typography>
                {dsiIsError ? (
                  <Alert severity="error">Could not load DSI candidates for this job.</Alert>
                ) : hasDsiGroups ? (
                  <Alert severity="info" data-testid="dsi-candidate-count">
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      <strong>{dsiRows.length}</strong> grouped mapping candidate
                      {dsiRows.length !== 1 ? 's' : ''} for import job <strong>#{importJobId}</strong>. Steward
                      resolution (filters, bulk actions, resolution plan, and single-row steward) lives on the import job
                      workspace — not on this legacy mapping queue page.
                    </Typography>
                    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                      <Button
                        component={Link}
                        href={`/admin/imports?job=${importJobId}`}
                        variant="contained"
                        size="small"
                        data-testid="dsi-open-import-resolution"
                      >
                        Open DSI resolution workspace
                      </Button>
                      <Button
                        size="small"
                        variant="outlined"
                        disabled={revalidateJob.isPending}
                        onClick={() => void revalidateJob.mutateAsync()}
                        data-testid="dsi-revalidate-job"
                      >
                        Revalidate import job
                      </Button>
                    </Stack>
                  </Alert>
                ) : dsiFetched ? (
                  <Typography variant="body2" color="text.secondary">
                    No DSI grouped candidates for this job.
                  </Typography>
                ) : null}
              </Box>
            ) : null}
          </Stack>
        </ModuleDataSection>
      </Paper>
    </>
  );
}

export default function AdminMappingsPage() {
  return (
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
  );
}
