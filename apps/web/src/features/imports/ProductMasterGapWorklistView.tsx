'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet, apiPost } from '@/lib/api';

type GapRow = {
  token: string;
  sources: string[];
  status: 'unresolved' | 'ignored';
  resolution_statuses: string[];
  occurrence_count: number;
  quantity_impact: number;
  sample_identifiers: string;
  first_seen: string | null;
  last_seen: string | null;
  affected_job_ids: number[];
  deep_link: { href: string; label: string };
};

type WorklistResponse = {
  rows: GapRow[];
  total: number;
  truncated: boolean;
  data_unavailable: boolean;
};

export function ProductMasterGapWorklistView() {
  const [source, setSource] = useState<'all' | 'shipment' | 'dsi'>('all');
  const [status, setStatus] = useState<'all' | 'unresolved' | 'ignored'>('all');

  const q = useQuery({
    queryKey: ['product-master-gaps', source, status],
    queryFn: () => {
      const params = new URLSearchParams();
      if (source !== 'all') params.set('source', source);
      if (status !== 'all') params.set('status', status);
      const qs = params.toString();
      return apiGet<WorklistResponse>(`/api/v1/product-master-gaps/worklist${qs ? `?${qs}` : ''}`);
    },
  });

  const columnDefs = useMemo<ColDef<GapRow>[]>(
    () => [
      { field: 'token', headerName: 'Product token', flex: 1, minWidth: 180 },
      {
        field: 'sources',
        headerName: 'Source(s)',
        width: 130,
        valueFormatter: (p) => (p.value as string[] | undefined)?.join(', ') ?? '',
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 110,
        cellRenderer: (p: ICellRendererParams<GapRow>) => {
          const v = p.data?.status;
          if (!v) return null;
          return (
            <Chip
              size="small"
              label={v}
              color={v === 'ignored' ? 'default' : 'warning'}
              variant={v === 'ignored' ? 'outlined' : 'filled'}
            />
          );
        },
      },
      {
        field: 'resolution_statuses',
        headerName: 'Resolution detail',
        width: 160,
        valueFormatter: (p) => (p.value as string[] | undefined)?.join(', ') ?? '',
      },
      {
        field: 'occurrence_count',
        headerName: 'Occurrences',
        width: 120,
        type: 'numericColumn',
      },
      {
        field: 'quantity_impact',
        headerName: 'Qty impact',
        width: 110,
        type: 'numericColumn',
        valueFormatter: (p) => new Intl.NumberFormat().format(Math.round(Number(p.value ?? 0))),
      },
      { field: 'sample_identifiers', headerName: 'Sample IDs', flex: 1, minWidth: 160 },
      {
        field: 'affected_job_ids',
        headerName: 'Jobs',
        width: 100,
        valueFormatter: (p) => (p.value as number[] | undefined)?.join(', ') ?? '',
      },
      {
        colId: 'action',
        headerName: 'Steward',
        width: 130,
        cellRenderer: (p: ICellRendererParams<GapRow>) => {
          const link = p.data?.deep_link;
          if (!link) return null;
          return (
            <Button size="small" component={Link} href={link.href} variant="text">
              {link.label}
            </Button>
          );
        },
      },
    ],
    [],
  );

  const job310Count = useMemo(
    () => (q.data?.rows ?? []).filter((r) => r.affected_job_ids.includes(310)).length,
    [q.data?.rows],
  );

  return (
    <Stack spacing={2}>
      <Alert severity="info">
        Catalogue gaps across shipment evidence and DSI imports. Resolve tokens in the governed steward
        flows — this surface flags only; it does not create Product Master rows.
      </Alert>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} flexWrap="wrap" useFlexGap>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel id="pmg-source">Source</InputLabel>
          <Select
            labelId="pmg-source"
            label="Source"
            value={source}
            onChange={(e) => setSource(e.target.value as typeof source)}
          >
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="shipment">Shipment</MenuItem>
            <MenuItem value="dsi">DSI</MenuItem>
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel id="pmg-status">Status</InputLabel>
          <Select
            labelId="pmg-status"
            label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value as typeof status)}
          >
            <MenuItem value="all">All</MenuItem>
            <MenuItem value="unresolved">Unresolved</MenuItem>
            <MenuItem value="ignored">Ignored</MenuItem>
          </Select>
        </FormControl>
      </Stack>

      {q.data ? (
        <Typography variant="body2" color="text.secondary" data-testid="pmg-summary">
          {q.data.total} token{q.data.total === 1 ? '' : 's'}
          {job310Count > 0 ? ` · ${job310Count} touching job 310` : ''}
          {q.data.truncated ? ' (truncated)' : ''}
        </Typography>
      ) : null}

      <ModuleDataSection
        isLoading={q.isLoading}
        isError={q.isError}
        error={q.error}
        onRetry={() => void q.refetch()}
        isEmpty={Boolean(q.data && q.data.rows.length === 0)}
        empty={{
          title: 'No unresolved product tokens',
          description: 'All imported product identifiers resolved to Product Master for the current filters.',
        }}
      >
        <Box data-testid="pmg-grid">
          <EnterpriseDataGrid rowData={q.data?.rows ?? []} columnDefs={columnDefs} height={560} />
        </Box>
      </ModuleDataSection>
    </Stack>
  );
}
