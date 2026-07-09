'use client';

import { Alert, Box, Button, Paper, Stack, Tab, Tabs, TextField, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { ColDef } from 'ag-grid-community';

import { EmptyWorkspace } from '@/components/EmptyWorkspace';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiDownloadBlob, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type PlanRow = {
  id: number;
  promotion_id: number;
  promo_code: string | null;
  sku: string | null;
  expected_uplift_pct: number | null;
  stock_readiness: string | null;
};

type ReadyRow = { id: number; sku: string | null; explanation_summary: string | null };

type ExportRow = {
  id: number;
  export_version: number;
  template_code: string;
  workflow_status: string;
  validation_status: string;
  file_name: string;
  checksum_sha256: string;
  submitted_at: string | null;
  decided_at: string | null;
  decided_by: string | null;
  last_comment: string | null;
  created_at: string | null;
};

type ExportEventRow = {
  id: number;
  event_type: string;
  actor: string | null;
  comment: string | null;
  payload: Record<string, unknown> | null;
  created_at: string | null;
};

export default function PromotionsPage() {
  const [tab, setTab] = useState(0);
  const [promotionId, setPromotionId] = useState<number | null>(null);
  const [selectedExportId, setSelectedExportId] = useState<number | null>(null);
  const [rejectComment, setRejectComment] = useState('Needs updated uplift assumption.');
  const [message, setMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const {
    data: plans,
    isLoading: plansLoading,
    isError: plansIsError,
    error: plansErr,
    refetch: refetchPlans,
  } = useQuery({
    queryKey: ['promo-plans'],
    queryFn: ({ signal }) => apiGet<PlanRow[]>('/api/v1/promotions/plans', { signal }),
  });

  const {
    data: readiness,
    isLoading: readinessLoading,
    isError: readinessIsError,
    error: readinessErr,
    refetch: refetchReadiness,
  } = useQuery({
    queryKey: ['promo-readiness'],
    queryFn: ({ signal }) => apiGet<ReadyRow[]>('/api/v1/promotions/readiness', { signal }),
  });

  const effectivePromotionId = useMemo(() => {
    if (promotionId != null) return promotionId;
    return plans?.[0]?.promotion_id ?? null;
  }, [promotionId, plans]);

  const delPlan = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/promotions/plans/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['promo-plans'] }),
  });
  const clearPlans = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/promotions/plans/clear-all', { confirm: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['promo-plans'] }),
  });
  const delReady = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/promotions/readiness/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['promo-readiness'] }),
  });
  const clearReady = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/promotions/readiness/clear-all', { confirm: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['promo-readiness'] }),
  });

  const promotionFieldValue = promotionId ?? '';

  const {
    data: exports,
    isLoading: exportsLoading,
    isError: exportsIsError,
    error: exportsErr,
    refetch: refetchExports,
  } = useQuery({
    queryKey: ['promo-exports', effectivePromotionId],
    queryFn: ({ signal }) =>
      apiGet<ExportRow[]>(`/api/v1/promotions/${effectivePromotionId}/exports`, { signal }),
    enabled: effectivePromotionId != null,
  });

  const {
    data: events,
    isLoading: eventsLoading,
    isError: eventsIsError,
    error: eventsErr,
    refetch: refetchEvents,
  } = useQuery({
    queryKey: ['promo-export-events', selectedExportId],
    queryFn: ({ signal }) =>
      apiGet<ExportEventRow[]>(`/api/v1/promotions/exports/${selectedExportId}/events`, { signal }),
    enabled: selectedExportId != null,
  });

  const planCols: ColDef<PlanRow>[] = useMemo(() => {
    const busyDel = delPlan.isPending || clearPlans.isPending;
    return [
      { field: 'promotion_id', headerName: 'Promo id', minWidth: 100 },
      { field: 'promo_code', headerName: 'Promo' },
      { field: 'sku', headerName: 'SKU' },
      { field: 'expected_uplift_pct', headerName: 'Uplift %' },
      { field: 'stock_readiness', headerName: 'Stock readiness' },
      gridDeleteColumn<PlanRow>((id) => void delPlan.mutate(id), { busy: busyDel }),
    ];
  }, [delPlan, delPlan.isPending, clearPlans.isPending]);

  const readyCols: ColDef<ReadyRow>[] = useMemo(() => {
    const busyDel = delReady.isPending || clearReady.isPending;
    return [
      { field: 'sku', headerName: 'SKU' },
      { field: 'explanation_summary', headerName: 'Explanation', flex: 1, minWidth: 260 },
      gridDeleteColumn<ReadyRow>((id) => void delReady.mutate(id), { busy: busyDel }),
    ];
  }, [delReady, delReady.isPending, clearReady.isPending]);

  const exportCols: ColDef<ExportRow>[] = [
    { field: 'id', headerName: 'Export id', minWidth: 100 },
    { field: 'export_version', headerName: 'Version', minWidth: 90 },
    { field: 'workflow_status', headerName: 'Workflow', minWidth: 130 },
    { field: 'validation_status', headerName: 'Validation', minWidth: 110 },
    { field: 'file_name', headerName: 'File', flex: 1, minWidth: 220 },
    { field: 'checksum_sha256', headerName: 'SHA-256', minWidth: 140 },
    { field: 'submitted_at', headerName: 'Submitted', minWidth: 160 },
    { field: 'decided_at', headerName: 'Decided', minWidth: 160 },
  ];

  const eventCols: ColDef<ExportEventRow>[] = [
    { field: 'created_at', headerName: 'When', minWidth: 170 },
    { field: 'event_type', headerName: 'Event', minWidth: 140 },
    { field: 'actor', headerName: 'Actor', minWidth: 120 },
    { field: 'comment', headerName: 'Comment', flex: 1, minWidth: 200 },
  ];

  const planRows = plans ?? [];
  const readyRows = readiness ?? [];
  const exportRows = exports ?? [];
  const eventRows = events ?? [];

  async function run(action: string, fn: () => Promise<void>) {
    setMessage(null);
    try {
      await fn();
      setMessage(`${action} succeeded`);
      await queryClient.invalidateQueries({ queryKey: ['promo-exports', effectivePromotionId] });
      await queryClient.invalidateQueries({ queryKey: ['promo-export-events', selectedExportId] });
    } catch (e) {
      setMessage(`${action} failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <>
      <PageHeader crumbs={[{ label: 'Promotions' }]} title="Promo calendar & readiness" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Scaffold plans/readiness are parked (CPOR U6 / spec §7). Use{' '}
        <strong>Commercial Planning → CPOR Cases</strong> (
        <a href="/commercial-planner/cpor-cases">/commercial-planner/cpor-cases</a>) for live promotion cases and
        U4 XLSX export. Legacy export tab below remains for empty scaffold only.
      </Alert>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 900 }}>
        <strong>Plans</strong> and <strong>Readiness</strong> APIs return empty (parked). Prefer CPOR Cases for
        case builder, lifecycle, and settlement.
      </Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Plans" />
        <Tab label="Readiness (explainable)" />
        <Tab label="CPOR export & approval" />
      </Tabs>
      {message ? (
        <Alert sx={{ mb: 2 }} severity={message.includes('failed') ? 'error' : 'success'}>
          {message}
        </Alert>
      ) : null}
      <Paper sx={{ p: 2 }}>
        {tab === 0 ? (
          <ModuleDataSection
            intro="Each row ties a promotion to a SKU with uplift and stock-readiness hints from the API."
            isLoading={plansLoading}
            isError={plansIsError}
            error={toQueryError(plansErr)}
            onRetry={() => void refetchPlans()}
            isEmpty={planRows.length === 0}
            empty={{
              title: 'No promotion plan lines',
              description: 'Plan lines come from fact_promotion_plan. Use Data imports or internal writes to load promo data.',
              primary: { label: 'Data imports', href: '/admin/imports' },
              secondary: { label: 'Getting started', href: '/getting-started' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => queryClient.invalidateQueries({ queryKey: ['promo-plans'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every promotion plan line? This cannot be undone.')) return;
                  void clearPlans.mutate();
                }}
                importsHref="/admin/imports"
                busy={delPlan.isPending || clearPlans.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={planRows} columnDefs={planCols} />
          </ModuleDataSection>
        ) : tab === 1 ? (
          <ModuleDataSection
            intro="Readiness uses the recommendation pattern (summary + structured factors in the API)."
            isLoading={readinessLoading}
            isError={readinessIsError}
            error={toQueryError(readinessErr)}
            onRetry={() => void refetchReadiness()}
            isEmpty={readyRows.length === 0}
            empty={{
              title: 'No readiness recommendations',
              description: 'These rows are generated when promos and inventory signals exist in the database.',
              primary: { label: 'Plans tab', href: '/promotions' },
              secondary: { label: 'Inventory', href: '/inventory' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => queryClient.invalidateQueries({ queryKey: ['promo-readiness'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every promo readiness row? This cannot be undone.')) return;
                  void clearReady.mutate();
                }}
                clearAllLabel="Clear all readiness rows"
                importsHref="/admin/imports"
                busy={delReady.isPending || clearReady.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={readyRows} columnDefs={readyCols} />
          </ModuleDataSection>
        ) : effectivePromotionId == null ? (
          <EmptyWorkspace
            title="No promotion to export"
            description="CPOR export needs a promotion id. Load the Plans tab so the app can default to the first promotion, or type an id after plans exist."
            primary={{ label: 'Open Plans tab', href: '/promotions' }}
            secondary={{ label: 'Getting started', href: '/getting-started' }}
          />
        ) : (
          <Stack spacing={2}>
            <Typography variant="body2" color="text.secondary">
              Template-driven Excel export (CPOR-style layout) with validation, versioning, manual download, and
              approval scaffolding. Email delivery remains optional and disabled by default in API settings.
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }}>
              <TextField
                label="Promotion id (optional override)"
                type="number"
                size="small"
                value={promotionFieldValue}
                onChange={(e) => {
                  const v = e.target.value;
                  setPromotionId(v === '' ? null : Number(v));
                }}
                helperText={
                  plans?.[0]
                    ? `Defaults to plans[0].promotion_id=${plans[0].promotion_id} when empty.`
                    : 'Type a promotion id from your database.'
                }
              />
              <Button
                variant="outlined"
                onClick={() =>
                  run('Validate', async () => {
                    await apiPost(`/api/v1/promotions/${effectivePromotionId}/exports/validate`);
                  })
                }
              >
                Validate
              </Button>
              <Button
                variant="contained"
                onClick={() =>
                  run('Create export', async () => {
                    await apiPost(`/api/v1/promotions/${effectivePromotionId}/exports`);
                  })
                }
              >
                Create export
              </Button>
              <Button
                variant="outlined"
                onClick={() =>
                  run('Resend (new version)', async () => {
                    if (selectedExportId == null) throw new Error('Select an export row id first');
                    await apiPost(`/api/v1/promotions/exports/${selectedExportId}/resend`);
                  })
                }
              >
                Resend
              </Button>
            </Stack>
            <Typography variant="subtitle2">Export history</Typography>
            <ModuleDataSection
              intro="Select a row to attach the audit trail panel below. Create export adds a new versioned file."
              isLoading={exportsLoading}
              isError={exportsIsError}
              error={toQueryError(exportsErr)}
              onRetry={() => void refetchExports()}
              isEmpty={exportRows.length === 0}
              empty={{
                title: 'No exports for this promotion yet',
                description: 'Click Create export after Validate passes. Exports require at least one plan line for the promotion.',
                secondary: { label: 'Getting started', href: '/getting-started' },
              }}
              toolbar={
                <ModuleGridToolbar
                  onRefresh={() => {
                    void queryClient.invalidateQueries({ queryKey: ['promo-exports', effectivePromotionId] });
                  }}
                  importsHref="/admin/imports"
                />
              }
            >
              <EnterpriseDataGrid
                rowData={exportRows}
                columnDefs={exportCols}
                gridOptions={{
                  onRowClicked: (e) => setSelectedExportId((e.data as ExportRow | undefined)?.id ?? null),
                }}
              />
            </ModuleDataSection>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap">
              <Button
                variant="contained"
                color="secondary"
                disabled={!selectedExportId}
                onClick={() =>
                  run('Download', async () => {
                    if (selectedExportId == null) throw new Error('Select an export');
                    const row = exports?.find((x) => x.id === selectedExportId);
                    await apiDownloadBlob(`/api/v1/promotions/exports/${selectedExportId}/file`, row?.file_name ?? 'export.xlsx');
                  })
                }
              >
                Download selected
              </Button>
              <Button
                variant="outlined"
                disabled={!selectedExportId}
                onClick={() =>
                  run('Submit for approval', async () => {
                    if (selectedExportId == null) throw new Error('Select an export');
                    await apiPost(`/api/v1/promotions/exports/${selectedExportId}/submit`);
                  })
                }
              >
                Submit
              </Button>
              <Button
                variant="outlined"
                disabled={!selectedExportId}
                onClick={() =>
                  run('Approve', async () => {
                    if (selectedExportId == null) throw new Error('Select an export');
                    await apiPost(`/api/v1/promotions/exports/${selectedExportId}/approve`);
                  })
                }
              >
                Approve
              </Button>
            </Stack>
            <TextField
              label="Reject comment"
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              fullWidth
              multiline
              minRows={2}
            />
            <Button
              variant="outlined"
              color="warning"
              disabled={!selectedExportId}
              onClick={() =>
                run('Reject', async () => {
                  if (selectedExportId == null) throw new Error('Select an export');
                  await apiPost(`/api/v1/promotions/exports/${selectedExportId}/reject`, { comment: rejectComment });
                })
              }
            >
              Reject with comment
            </Button>
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Audit trail {selectedExportId ? `(export ${selectedExportId})` : ''}
              </Typography>
              {!selectedExportId ? (
                <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                  Select an export row in the grid above to load its approval and email-stub events.
                </Typography>
              ) : (
                <ModuleDataSection
                  intro="Events append on create, submit, approve, reject, and resend."
                  isLoading={eventsLoading}
                  isError={eventsIsError}
                  error={toQueryError(eventsErr)}
                  onRetry={() => void refetchEvents()}
                  isEmpty={eventRows.length === 0}
                  empty={{
                    title: 'No events for this export',
                    description: 'If the export was just created, refresh or re-open the row; events should appear after actions.',
                    secondary: { label: 'Getting started', href: '/getting-started' },
                  }}
                  toolbar={
                    <ModuleGridToolbar
                      onRefresh={() => {
                        void queryClient.invalidateQueries({ queryKey: ['promo-export-events', selectedExportId] });
                      }}
                    />
                  }
                >
                  <EnterpriseDataGrid rowData={eventRows} columnDefs={eventCols} />
                </ModuleDataSection>
              )}
            </Box>
          </Stack>
        )}
      </Paper>
    </>
  );
}
