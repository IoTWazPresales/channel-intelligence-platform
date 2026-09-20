'use client';

import {
  Alert,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';

import { DataChrome } from '@/features/data-stewardship/DataChrome';
import { apiGet, safeDisplayError } from '@/lib/api';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

type AuditEvent = {
  id: number;
  created_at: string | null;
  actor: string;
  action: string;
  importer: string;
  entity_type: string | null;
  entity_token: string | null;
  import_job_id: number | null;
  candidate_id: number | null;
  target_dim: string | null;
  target_id: number | null;
  payload_json: Record<string, unknown> | null;
};

type AuditResponse = {
  tenant_id: string;
  count: number;
  events: AuditEvent[];
};

export default function StewardAuditPage() {
  const { data: me, isError: meError } = useCurrentUser();
  const role = String(me?.role || '').toLowerCase();
  const allowed = role === 'admin' || role === 'steward';

  const [importer, setImporter] = useState('');
  const [jobId, setJobId] = useState('');

  const query = useQuery({
    queryKey: ['admin', 'steward-audit', importer, jobId],
    queryFn: () => {
      const qs = new URLSearchParams();
      qs.set('limit', '200');
      if (importer) qs.set('importer', importer);
      if (jobId.trim()) qs.set('import_job_id', jobId.trim());
      return apiGet<AuditResponse>(`/api/v1/admin/steward-audit?${qs.toString()}`);
    },
    enabled: allowed,
    retry: false,
  });

  const rows = useMemo(() => query.data?.events ?? [], [query.data]);
  const auditCols = useMemo<ColDef<AuditEvent>[]>(
    () => [
      {
        field: 'created_at',
        headerName: 'When',
        minWidth: 160,
        valueFormatter: (p) => (p.value ? String(p.value).replace('T', ' ').slice(0, 19) : '—'),
      },
      { field: 'actor', headerName: 'Actor', minWidth: 120 },
      { field: 'action', headerName: 'Action', minWidth: 120 },
      { field: 'importer', headerName: 'Importer', minWidth: 110 },
      {
        headerName: 'Entity',
        minWidth: 180,
        flex: 1,
        valueGetter: (p) => [p.data?.entity_type, p.data?.entity_token].filter(Boolean).join(': ') || '—',
      },
      {
        field: 'import_job_id',
        headerName: 'Job',
        minWidth: 80,
        valueFormatter: (p) => p.value ?? '—',
      },
      {
        headerName: 'Target',
        minWidth: 140,
        valueGetter: (p) =>
          p.data?.target_dim && p.data.target_id != null ? `${p.data.target_dim}#${p.data.target_id}` : '—',
      },
    ],
    [],
  );

  if (meError || (me && !allowed)) {
    return (
      <DataChrome>
        <Alert severity="warning">Admin or steward role required.</Alert>
      </DataChrome>
    );
  }

  return (
    <DataChrome>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Append-only log of steward resolve / map / ignore / provisional / bulk decisions (DSI first).
      </Typography>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <FormControl sx={{ minWidth: 180 }} size="small">
          <InputLabel id="audit-importer-label">Importer</InputLabel>
          <Select
            labelId="audit-importer-label"
            label="Importer"
            value={importer}
            onChange={(ev) => setImporter(ev.target.value)}
            inputProps={{ 'data-testid': 'steward-audit-importer' }}
          >
            <MenuItem value="">All</MenuItem>
            <MenuItem value="dsi">dsi</MenuItem>
            <MenuItem value="shipment">shipment</MenuItem>
            <MenuItem value="cpor">cpor</MenuItem>
            <MenuItem value="cst">cst</MenuItem>
          </Select>
        </FormControl>
        <TextField
          size="small"
          label="Import job id"
          value={jobId}
          onChange={(ev) => setJobId(ev.target.value)}
          inputProps={{ 'data-testid': 'steward-audit-job-id' }}
        />
      </Stack>

      <Paper sx={{ p: 2 }} data-testid="steward-audit-table">
        <ModuleDataSection
          isLoading={query.isPending}
          isError={query.isError}
          error={query.isError ? new Error(safeDisplayError(query.error)) : null}
          onRetry={() => void query.refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No steward audit events yet',
            description:
              importer || jobId
                ? 'No steward decisions match the current importer / job filter.'
                : 'Steward resolve, map, ignore, provisional and bulk decisions appear here once made.',
            primary: { label: 'Import Center', href: '/admin/imports' },
          }}
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={auditCols} height={480} />
        </ModuleDataSection>
      </Paper>
    </DataChrome>
  );
}
