'use client';

import { Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { DataChrome } from '@/features/data-stewardship/DataChrome';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import type { PortCondition } from '@/features/supply-inbound/onTheWater/types';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

type Listing = { items: PortCondition[]; current: PortCondition[] };

/** Ports the ACZA reports deliver to. Any other UN/LOCODE can be typed. */
const KNOWN_PORTS = [
  { code: 'ZADUR', label: 'Durban' },
  { code: 'ZAJNB', label: 'City Deep' },
  { code: 'MUPLU', label: 'Port Louis' },
  { code: 'ZACPT', label: 'Cape Town' },
];

export default function PortConditionsPage() {
  const { data: me, isError: meError } = useCurrentUser();
  const allowed = String(me?.role || '').toLowerCase() === 'admin';
  const qc = useQueryClient();
  const [code, setCode] = useState('ZADUR');
  const [days, setDays] = useState('');
  const [note, setNote] = useState('');

  const listing = useQuery({
    queryKey: ['shipping', 'port-conditions'],
    queryFn: ({ signal }) => apiGet<Listing>('/api/v1/shipping/port-conditions', { signal }),
    enabled: allowed,
    retry: false,
  });

  const add = useMutation({
    mutationFn: () => apiPost<PortCondition>('/api/v1/shipping/port-conditions', { port_code: code.trim(), delay_days: Number(days), note: note.trim() || null }),
    onSuccess: async () => {
      setDays('');
      setNote('');
      await qc.invalidateQueries({ queryKey: ['shipping', 'port-conditions'] });
      await qc.invalidateQueries({ queryKey: ['shipping-on-the-water'] });
    },
  });

  const cols = useMemo<ColDef<PortCondition>[]>(
    () => [
      { field: 'entered_at', headerName: 'Entered', minWidth: 170, valueFormatter: (p) => (p.value ? String(p.value).replace('T', ' ').slice(0, 16) : '—') },
      { headerName: 'Port', minWidth: 170, valueGetter: (p) => (p.data ? `${p.data.label} (${p.data.port_code})` : '') },
      { field: 'delay_days', headerName: 'Delay (days)', minWidth: 120, type: 'numericColumn' },
      { field: 'entered_by', headerName: 'Entered by', minWidth: 150 },
      { field: 'note', headerName: 'Note', minWidth: 220, flex: 1 },
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

  const rows = listing.data?.items ?? [];
  const currentCodes = new Set((listing.data?.current ?? []).map((c) => c.port_code.toUpperCase()));
  const valid = /^[A-Za-z0-9]{3,16}$/.test(code.trim()) && days.trim() !== '' && Number.isFinite(Number(days)) && Number(days) >= 0 && Number(days) <= 365;

  return (
    <DataChrome>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }} data-testid="port-conditions-intro">
        How many days a port is running late. This is a hand-entered figure until a congestion feed is chosen: it shows on the On the water map
        with who entered it and when. The newest row for a port is the current one. A correction is a new row; rows are kept and never changed.
      </Typography>
      <Paper sx={{ p: 2, mb: 2 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'flex-start' }} component="form"
          onSubmit={(e) => { e.preventDefault(); if (valid && !add.isPending) add.mutate(); }}>
          <TextField select size="small" label="Port" value={KNOWN_PORTS.some((p) => p.code === code) ? code : 'other'} sx={{ minWidth: 200 }}
            onChange={(e) => setCode(e.target.value === 'other' ? '' : e.target.value)} inputProps={{ 'data-testid': 'port-condition-port' }}>
            {KNOWN_PORTS.map((p) => (
              <MenuItem key={p.code} value={p.code}>{`${p.label} (${p.code})`}{currentCodes.has(p.code) ? ' · has a figure' : ''}</MenuItem>
            ))}
            <MenuItem value="other">Another port…</MenuItem>
          </TextField>
          {KNOWN_PORTS.some((p) => p.code === code) ? null : (
            <TextField size="small" label="UN/LOCODE" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} helperText="For example ZADUR" />
          )}
          <TextField size="small" label="Delay (days)" type="number" value={days} onChange={(e) => setDays(e.target.value)} inputProps={{ min: 0, max: 365, step: 0.5, 'data-testid': 'port-condition-days' }} sx={{ width: 150 }} />
          <TextField size="small" label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} sx={{ flex: 1, minWidth: 220 }} inputProps={{ maxLength: 1000 }} />
          <Button type="submit" variant="contained" disabled={!valid || add.isPending} data-testid="port-condition-save">
            Add figure
          </Button>
        </Stack>
        {add.isError ? <Alert severity="error" sx={{ mt: 2 }}>{safeDisplayError(add.error)}</Alert> : null}
        {add.isSuccess ? <Alert severity="success" sx={{ mt: 2 }}>Added. The map shows it now.</Alert> : null}
      </Paper>
      <Paper sx={{ p: 2 }} data-testid="port-conditions-table">
        <ModuleDataSection
          isLoading={listing.isPending}
          isError={listing.isError}
          error={listing.isError ? new Error(safeDisplayError(listing.error)) : null}
          onRetry={() => void listing.refetch()}
          isEmpty={rows.length === 0}
          empty={{ title: 'No figures entered yet', description: 'Until one is entered, each port on the map reads "No figure entered · Planned".' }}
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={cols} height={420} />
        </ModuleDataSection>
      </Paper>
    </DataChrome>
  );
}
