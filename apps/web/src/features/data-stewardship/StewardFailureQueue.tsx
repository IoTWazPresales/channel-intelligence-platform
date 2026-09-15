'use client';

import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import { Box, Button, Typography } from '@mui/material';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { ScopeBar } from '@/features/workbench-ui/controls';
import { apiGet } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

import type { StewardFailureQueueResponse, StewardQueueItem } from './types';
import { useClientReady } from './useClientReady';

export function StewardFailureQueue() {
  const router = useRouter();
  const search = useSearchParams();
  const entityType = search.get('entity_type');
  const ready = useClientReady();
  const qs = entityType ? `?entity_type=${encodeURIComponent(entityType)}` : '';
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['imports', 'steward-queue', entityType],
    queryFn: ({ signal }) =>
      apiGet<StewardFailureQueueResponse>(`/api/v1/imports/steward-queue${qs}`, { signal }),
  });
  const payload = ready ? data : undefined;

  const setEntity = (next: string | null) => {
    const params = new URLSearchParams(search.toString());
    if (next) params.set('entity_type', next);
    else params.delete('entity_type');
    const out = params.toString();
    router.replace(out ? `/admin/mappings?${out}` : '/admin/mappings', { scroll: false });
  };

  const chips = (payload?.groups ?? []).map((g) => ({
    key: g.entity_type,
    label: `${g.label} · ${g.candidate_count}`,
    active: entityType === g.entity_type,
    onToggle: () => setEntity(entityType === g.entity_type ? null : g.entity_type),
    tone: g.covered ? ('default' as const) : ('warning' as const),
  }));

  const uncovered = (payload?.groups ?? []).filter((g) => !g.covered).length;

  const columnDefs = useMemo<ColDef<StewardQueueItem>[]>(
    () => [
      { field: 'entity_type', headerName: 'Failure type', minWidth: 180, flex: 1, valueGetter: (p) => p.data?.label ?? p.data?.entity_type },
      { field: 'normalized_key', headerName: 'Token', minWidth: 200, flex: 1.4 },
      { field: 'row_count', headerName: 'Rows', type: 'rightAligned', width: 90 },
      { field: 'import_job_id', headerName: 'Job', width: 90 },
      { field: 'template_slug', headerName: 'Importer', minWidth: 160, flex: 1 },
      { field: 'file_name', headerName: 'File', minWidth: 180, flex: 1.2 },
      { field: 'job_status', headerName: 'Job status', width: 160 },
      {
        headerName: 'Open',
        width: 140,
        cellRenderer: (p: { data?: StewardQueueItem }) => {
          const href = p.data?.steward_href;
          if (!href) {
            return (
              <Typography variant="caption" color="text.secondary">
                UNCOVERED
              </Typography>
            );
          }
          return (
            <Button component={NextLink} href={href} size="small" data-testid={`steward-queue-open-${p.data?.id}`}>
              Steward
            </Button>
          );
        },
      },
    ],
    []
  );

  const onRowClicked = (e: RowClickedEvent<StewardQueueItem>) => {
    const href = e.data?.steward_href;
    if (href) router.push(href);
  };

  return (
    <>
      <Box data-testid="steward-failure-queue-strip">
        <HeadlineStrip columns={4}>
        <HeadlineFigure
          label="Open candidates"
          value={payload?.total_candidates ?? '—'}
          compact
          severity={payload?.total_candidates ? 'warn' : 'good'}
          caption="needs_review across jobs"
        />
        <HeadlineFigure label="Failure types" value={payload?.groups.length ?? '—'} compact caption="GROUP BY entity_type" />
        <HeadlineFigure label="Jobs with work" value={payload?.distinct_jobs ?? '—'} compact />
        <HeadlineFigure
          label="Uncovered types"
          value={uncovered}
          compact
          severity={uncovered ? 'warn' : 'good'}
          caption="no existing engine href"
        />
        </HeadlineStrip>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1, mb: 1.5 }} data-testid="steward-failure-queue-copy">
        Grouped by the failure type stored on each candidate, not by import job. Job is provenance. Resolve in the
        existing steward — this leaf does not accept or reject. Legacy <code>entity_mapping_queue</code> is D-0002
        (untouched) and is not this list.
      </Typography>
      <ScopeBar
        chips={chips}
        summary={
          payload
            ? `${payload.returned} of ${entityType ? payload.items.length : payload.total_candidates} candidates`
            : undefined
        }
        onClear={() => setEntity(null)}
      />
      <ModuleDataSection
        isLoading={isLoading || !ready}
        isError={isError}
        error={toQueryError(error)}
        onRetry={() => void refetch()}
        isEmpty={!isLoading && ready && (payload?.items.length ?? 0) === 0}
        empty={{
          title: 'No open steward candidates',
          description: 'Nothing in needs_review on import_entity_mapping_candidate for this tenant.',
          primary: { label: 'Import Center', href: '/admin/imports' },
        }}
        toolbar={<ModuleGridToolbar onRefresh={() => void refetch()} importsHref="/admin/imports" />}
      >
        <EnterpriseDataGrid<StewardQueueItem>
          rowData={payload?.items ?? []}
          columnDefs={columnDefs}
          height={420}
          gridOptions={{
            onRowClicked,
            getRowId: (p) => String(p.data.id),
            rowClass: 'cip-clickable-row',
          }}
        />
      </ModuleDataSection>
    </>
  );
}
