'use client';

import { Alert, Box, Button, Paper, Stack, Typography } from '@mui/material';
import type { GridOptions, RowClickedEvent } from 'ag-grid-community';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { Suspense, useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPost, apiUrl } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

import { DsiCandidateStewardPanel } from './DsiCandidateStewardPanel';

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

function adminBrowseHref(entityType: string): string | null {
  switch (entityType) {
    case 'distributor_token':
      return '/admin/distributors';
    case 'product_identifier':
      return '/admin/products';
    case 'customer_dealer_token':
      return '/admin/customers';
    default:
      return null;
  }
}

function AdminMappingsPageContent() {
  const searchParams = useSearchParams();
  const importJobIdParam = searchParams.get('import_job_id');
  const { jobId: importJobId, invalid: invalidJobIdParam } = useMemo(
    () => parseImportJobId(importJobIdParam),
    [importJobIdParam]
  );

  const [dsiSelected, setDsiSelected] = useState<DsiMappingCandidateRow | null>(null);

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

  const dsiQueryKey = ['dsi-mapping-candidates', importJobId] as const;
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
      apiGet<DsiMappingCandidateRow[]>(
        `/api/v1/mappings/import-jobs/${importJobId}/distributor-si-candidates`,
        { signal }
      ),
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
      void qc.invalidateQueries({ queryKey: ['dsi-mapping-candidates'] });
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
      return apiPost<{ ok: boolean }>(
        `/api/v1/mappings/import-jobs/${importJobId}/revalidate-distributor-sales-inventory`
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: dsiQueryKey });
      void refetchDsi();
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

  const dsiColDefs: ColDef<DsiMappingCandidateRow>[] = useMemo(
    () => [
      { field: 'entity_type', headerName: 'Entity type', minWidth: 160 },
      {
        headerName: 'Raw samples',
        minWidth: 180,
        valueGetter: (p) => {
          const s = p.data?.sample_raw_values;
          if (s == null || !Array.isArray(s)) return '';
          return s.filter(Boolean).join('; ');
        },
      },
      { field: 'normalized_key', headerName: 'Normalized token', minWidth: 160 },
      { field: 'dealer_group_token', headerName: 'Dealer / group token', minWidth: 140 },
      { field: 'suggested_entity_id', headerName: 'Suggested id', width: 120 },
      { field: 'match_reason', headerName: 'Match reason', minWidth: 120 },
      { field: 'confidence_score', headerName: 'Confidence', width: 110 },
      { field: 'row_count', headerName: 'Rows', width: 90 },
      { field: 'total_units', headerName: 'Total units', width: 110 },
      { field: 'total_reported_value', headerName: 'Total value', width: 120 },
      { field: 'status', headerName: 'Status', width: 120 },
      { field: 'source_definition_id', headerName: 'Source id', width: 100 },
      { field: 'created_at', headerName: 'First seen', minWidth: 160 },
      { field: 'updated_at', headerName: 'Last seen', minWidth: 160 },
      {
        headerName: 'Browse master',
        width: 160,
        cellRenderer: (p: { data: DsiMappingCandidateRow }) => {
          const href = adminBrowseHref(p.data.entity_type);
          if (!href) return null;
          return (
            <Button component={Link} href={href} size="small" variant="text">
              Open
            </Button>
          );
        },
      },
    ],
    []
  );

  const onDsiRowClicked = useCallback((e: RowClickedEvent<DsiMappingCandidateRow>) => {
    if (e.data) setDsiSelected(e.data);
  }, []);

  const dsiGridOptions = useMemo<GridOptions<DsiMappingCandidateRow>>(
    () => ({
      onRowClicked: onDsiRowClicked,
    }),
    [onDsiRowClicked]
  );

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
        primary: { label: 'Data & imports', href: '/admin/imports' },
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
                  DSI grouped import candidates (ImportEntityMappingCandidate)
                </Typography>
                <Alert severity="info" sx={{ mb: 1 }}>
                  Customer/dealer names vary by source—saving a mapping creates an <strong>approved alias</strong> so
                  future uploads resolve automatically. Use <strong>Revalidate import job</strong> after changes to
                  refresh staging and candidate groups for this job.
                </Alert>
                {dsiIsError ? (
                  <Alert severity="error">Could not load DSI candidates for this job.</Alert>
                ) : hasDsiGroups ? (
                  <>
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap" useFlexGap>
                      <Typography variant="body2" color="text.secondary" data-testid="dsi-candidate-count">
                        {dsiRows.length} grouped import candidate group{dsiRows.length !== 1 ? 's' : ''} need review for
                        DSI job #{importJobId}.
                      </Typography>
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
                    <EnterpriseDataGrid
                      rowData={dsiRows}
                      columnDefs={dsiColDefs}
                      height={420}
                      gridOptions={dsiGridOptions}
                    />
                    {importJobId != null ? (
                      <DsiCandidateStewardPanel
                        importJobId={importJobId}
                        candidate={dsiSelected}
                        onDone={() => void refetchDsi()}
                      />
                    ) : null}
                  </>
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
