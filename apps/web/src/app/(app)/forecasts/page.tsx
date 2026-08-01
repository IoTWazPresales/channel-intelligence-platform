'use client';

import { Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Paper, Stack, Switch, TextField } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { BulkPasteDialog } from '@/components/BulkPasteDialog';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type Row = {
  id: number;
  sku: string | null;
  period_start: string;
  forecast_units: number;
  confidence_placeholder: string | null;
  confidence_level?: string | null;
  method?: string | null;
  is_override: boolean;
};

type ForecastPasteRow = {
  sku: string;
  period_start: string;
  forecast_units: number;
  confidence_placeholder?: string;
  customer_code?: string;
  is_override?: boolean;
};

function parseForecastPaste(text: string): ForecastPasteRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (!lines.length) return [];
  const first = lines[0].toLowerCase();
  const hasHeader = first.includes('sku') && first.includes('period');
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const rows: ForecastPasteRow[] = [];
  for (const line of dataLines) {
    const parts = line.split(/[,\t]/).map((p) => p.trim().replace(/^"|"$/g, ''));
    if (parts.length < 3) continue;
    const [sku, period_start, unitsS, conf, cust, ov] = parts;
    if (!sku || !period_start) continue;
    const forecast_units = Number(unitsS);
    if (!Number.isFinite(forecast_units)) continue;
    const o: ForecastPasteRow = { sku, period_start, forecast_units };
    if (conf) o.confidence_placeholder = conf;
    if (cust) o.customer_code = cust;
    if (ov && ['1', 'true', 'yes', 'y'].includes(ov.toLowerCase())) o.is_override = true;
    rows.push(o);
  }
  return rows;
}

export default function ForecastsPage() {
  const qc = useQueryClient();
  const [pasteOpen, setPasteOpen] = useState(false);
  const [paste, setPaste] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [sku, setSku] = useState('');
  const [period, setPeriod] = useState(() => new Date().toISOString().slice(0, 10));
  const [units, setUnits] = useState('');
  const [conf, setConf] = useState('');
  const [cust, setCust] = useState('');
  const [override, setOverride] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['forecasts'],
    queryFn: ({ signal }) => apiGet<Row[]>('/api/v1/forecasts', { signal }),
  });

  const bulk = useMutation({
    mutationFn: (rows: ForecastPasteRow[]) => apiPost<{ created: number }>('/api/v1/forecasts/bulk', { rows }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['forecasts'] });
      setPasteOpen(false);
      setPaste('');
    },
  });

  const addOne = useMutation({
    mutationFn: () =>
      apiPost<{ id: number }>('/api/v1/forecasts', {
        sku: sku.trim(),
        period_start: period.trim(),
        forecast_units: Number(units),
        confidence_placeholder: conf.trim() || undefined,
        customer_code: cust.trim() || undefined,
        is_override: override,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['forecasts'] });
      setAddOpen(false);
      setSku('');
      setPeriod(new Date().toISOString().slice(0, 10));
      setUnits('');
      setConf('');
      setCust('');
      setOverride(false);
    },
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/forecasts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['forecasts'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/forecasts/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['forecasts'] }),
  });

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'sku', headerName: 'SKU', pinned: 'left' },
      { field: 'period_start', headerName: 'Period' },
      { field: 'forecast_units', headerName: 'Units', type: 'numericColumn' },
      { field: 'method', headerName: 'Method' },
      { field: 'confidence_placeholder', headerName: 'Confidence' },
      { field: 'is_override', headerName: 'Override' },
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending]);

  const rows = data ?? [];
  const busy = bulk.isPending || addOne.isPending || delRow.isPending || clearAll.isPending;

  return (
    <>
      <PageHeader crumbs={[{ label: 'Forecast' }]} title="Forecast & overrides" />
      <Paper sx={{ p: 2 }}>
        <ModuleDataSection
          intro="Demand forecast contract (fact_demand_forecast). Manual rows are overrides at distributor × product × customer × period. Unknown SKUs/customers are rejected — resolve in masters first. Missing customer → OPEN_CHANNEL; missing distributor → UNASSIGNED."
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No forecast rows yet',
            description: 'Use Add row or Paste upload, or use Data & imports for file-based loads.',
            primary: { label: 'Data & imports', href: '/admin/imports' },
            secondary: { label: 'Getting started', href: '/getting-started' },
          }}
          toolbar={
            <ModuleGridToolbar
              onRefresh={() => qc.invalidateQueries({ queryKey: ['forecasts'] })}
              onClearAll={() => {
                if (!window.confirm('Delete every forecast row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              onAdd={() => setAddOpen(true)}
              onUpload={() => setPasteOpen(true)}
              importsHref="/admin/imports"
              busy={busy}
            />
          }
        >
          <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} />
        </ModuleDataSection>
      </Paper>

      <BulkPasteDialog
        open={pasteOpen}
        title="Paste forecasts"
        hint={
          <>
            Columns: <code>sku, period_start, forecast_units</code> plus optional <code>confidence, customer_code, is_override</code>{' '}
            (1/true for override). Example: <code>SKU-001,2026-04-01,95,medium,CUST-1001,0</code>
          </>
        }
        placeholder="sku,period_start,forecast_units,confidence,customer_code,is_override"
        value={paste}
        onChange={setPaste}
        onClose={() => !bulk.isPending && setPasteOpen(false)}
        onSubmit={() => bulk.mutate(parseForecastPaste(paste))}
        busy={bulk.isPending}
        error={bulk.error as Error | null}
      />

      <Dialog open={addOpen} onClose={() => !addOne.isPending && setAddOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add forecast row</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="SKU" required value={sku} onChange={(e) => setSku(e.target.value)} fullWidth />
            <TextField label="Period start" required type="date" value={period} onChange={(e) => setPeriod(e.target.value)} fullWidth InputLabelProps={{ shrink: true }} />
            <TextField label="Forecast units" required type="number" value={units} onChange={(e) => setUnits(e.target.value)} fullWidth />
            <TextField label="Confidence (optional)" value={conf} onChange={(e) => setConf(e.target.value)} fullWidth />
            <TextField label="Customer code (optional)" value={cust} onChange={(e) => setCust(e.target.value)} fullWidth />
            <FormControlLabel control={<Switch checked={override} onChange={(_, v) => setOverride(v)} />} label="Override" />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)} disabled={addOne.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={addOne.isPending || !sku.trim() || !Number.isFinite(Number(units))}
            onClick={() => addOne.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
