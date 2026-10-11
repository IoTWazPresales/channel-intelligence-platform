'use client';

import {
  Alert,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { DataChrome } from '@/features/data-stewardship/DataChrome';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { apiGet, safeDisplayError } from '@/lib/api';

type AuditEvent = {
  id: number;
  created_at: string | null;
  actor: string;
  area: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  detail_json: Record<string, unknown> | null;
};

type AuditResponse = {
  tenant_id: string;
  count: number;
  events: AuditEvent[];
};

export default function PlatformAuditLogPage() {
  const { data: me, isError: meError } = useCurrentUser();
  const role = String(me?.role || '').toLowerCase();
  const allowed = role === 'admin';
  const [area, setArea] = useState('');

  const query = useQuery({
    queryKey: ['admin', 'audit-log', area],
    queryFn: () => {
      const qs = new URLSearchParams();
      qs.set('limit', '200');
      if (area) qs.set('area', area);
      return apiGet<AuditResponse>(`/api/v1/admin/audit-log?${qs.toString()}`);
    },
    enabled: allowed,
    retry: false,
  });

  const rows = useMemo(() => query.data?.events ?? [], [query.data]);
  const cols = useMemo<ColDef<AuditEvent>[]>(
    () => [
      {
        field: 'created_at',
        headerName: 'When',
        minWidth: 170,
        valueFormatter: (p) => (p.value ? String(p.value).replace('T', ' ').slice(0, 19) : '—'),
      },
      { field: 'actor', headerName: 'Who', minWidth: 140 },
      { field: 'area', headerName: 'Area', minWidth: 110 },
      { field: 'action', headerName: 'Action', minWidth: 160 },
      {
        headerName: 'Target',
        minWidth: 180,
        flex: 1,
        valueGetter: (p) =>
          [p.data?.target_type, p.data?.target_id].filter(Boolean).join(' ') || '—',
      },
    ],
    [],
  );

  if (meError || (me && !allowed)) {
    return (
      <DataChrome>
        <Alert severity="warning">Admin role required.</Alert>
      </DataChrome>
    );
  }

  return (
    <DataChrome>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }} data-testid="platform-audit-intro">
        Admin, user, settings and case-state actions. Steward decisions stay on Steward audit. SQL
        lookups stay on the SQL viewer.
      </Typography>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <FormControl sx={{ minWidth: 180 }} size="small">
          <InputLabel id="platform-audit-area-label">Area</InputLabel>
          <Select
            labelId="platform-audit-area-label"
            label="Area"
            value={area}
            onChange={(ev) => setArea(ev.target.value)}
            inputProps={{ 'data-testid': 'platform-audit-area' }}
          >
            <MenuItem value="">All</MenuItem>
            <MenuItem value="admin">Admin</MenuItem>
            <MenuItem value="user">User</MenuItem>
            <MenuItem value="settings">Settings</MenuItem>
            <MenuItem value="case">Case</MenuItem>
          </Select>
        </FormControl>
      </Stack>
      <Paper sx={{ p: 2 }} data-testid="platform-audit-table">
        <ModuleDataSection
          isLoading={query.isPending}
          isError={query.isError}
          error={query.isError ? new Error(safeDisplayError(query.error)) : null}
          onRetry={() => void query.refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No audit events yet',
            description: area
              ? 'No events match this area.'
              : 'User, settings and case-state actions appear here once they happen.',
          }}
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={cols} height={480} />
        </ModuleDataSection>
      </Paper>
    </DataChrome>
  );
}
