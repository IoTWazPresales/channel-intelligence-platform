'use client';

import HistoryIcon from '@mui/icons-material/History';
import { Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Paper, Stack, Switch, TextField } from '@mui/material';
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
  analogue_product_id?: number | null;
  analogue_basis?: Record<string, unknown> | null;
  velocity_basis?: string | null;
  seasonal_index?: number | null;
  lower_band?: number | null;
  upper_band?: number | null;
};

type ComputeFromHistoryResponse = {
  tenant_id: string;
  weeks_ahead: number;
  skip_overrides: boolean;
  never_merges_actuals: boolean;
  velocity: { upserted?: number; skipped_override?: number; considered?: number };
  analogue: { upserted?: number; skipped_override?: number; considered?: number };
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

  const [methodFilter, setMethodFilter] = useState<string | null>(null);
  const [computeMsg, setComputeMsg] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['forecasts', methodFilter],
    queryFn: ({ signal }) => {
      const q = new URLSearchParams({ limit: '500' });
      if (methodFilter) q.set('method', methodFilter);
      return apiGet<Row[]>(`/api/v1/forecasts?${q}`, { signal });
    },
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

  const computeHistory = useMutation({
    mutationFn: () =>
      apiPost<ComputeFromHistoryResponse>('/api/v1/forecasts/compute-from-history', {
        confirm: true,
        weeks_ahead: 13,
      }),
    onSuccess: (res) => {
      const v = res.velocity?.upserted ?? 0;
      const a = res.analogue?.upserted ?? 0;
      const skipped = (res.velocity?.skipped_override ?? 0) + (res.analogue?.skipped_override ?? 0);
      setComputeMsg(
        `Computed from history: ${v} velocity + ${a} analogue rows (tenant ${res.tenant_id}). ` +
          `Overrides kept: ${skipped}. Forecast never writes sell-out actuals.`,
      );
      void qc.invalidateQueries({ queryKey: ['forecasts'] });
    },
    onError: (err) => {
      setComputeMsg(err instanceof Error ? err.message : 'Compute from history failed');
    },
  });

  const runComputeFromHistory = () => {
    if (
      !window.confirm(
        'Compute demand forecast from sell-out history (velocity) and analogues for SKUs with no history? Manual override rows are kept. This does not change sell-out actuals.',
      )
    ) {
      return;
    }
    setComputeMsg(null);
    void computeHistory.mutate();
  };

  const colDefs: ColDef<Row>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'sku', headerName: 'SKU', pinned: 'left' },
      { field: 'period_start', headerName: 'Period' },
      { field: 'forecast_units', headerName: 'Units', type: 'numericColumn' },
      { field: 'method', headerName: 'Method' },
      { field: 'velocity_basis', headerName: 'Velocity basis' },
      { field: 'seasonal_index', headerName: 'Seasonal index', type: 'numericColumn' },
      {
        field: 'analogue_product_id',
        headerName: 'Analogue product id',
      },
      {
        field: 'analogue_basis',
        headerName: 'Analogue provenance',
        valueFormatter: (p) => (p.value ? JSON.stringify(p.value) : ''),
      },
      { field: 'lower_band', headerName: 'Lower band', type: 'numericColumn' },
      { field: 'upper_band', headerName: 'Upper band', type: 'numericColumn' },
      { field: 'confidence_level', headerName: 'Confidence' },
      { field: 'confidence_placeholder', headerName: 'Confidence (legacy)', hide: true },
      { field: 'is_override', headerName: 'Override' },
      gridDeleteColumn<Row>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending]);

  const rows = data ?? [];
  const busy = bulk.isPending || addOne.isPending || delRow.isPending || clearAll.isPending || computeHistory.isPending;

  return (
    <>
      <PageHeader crumbs={[{ label: 'Forecast' }]} title="Demand Forecast" />
      <Paper sx={{ p: 2 }}>
        {computeMsg ? (
          <Alert
            severity={computeHistory.isError ? 'error' : 'success'}
            sx={{ mb: 2 }}
            onClose={() => setComputeMsg(null)}
            data-testid="forecast-compute-msg"
          >
            {computeMsg}
          </Alert>
        ) : null}
        <Stack direction="row" spacing={1} sx={{ mb: 1.5 }} flexWrap="wrap" useFlexGap>
          {[
            { id: null, label: 'All methods' },
            { id: 'velocity', label: 'Velocity' },
            { id: 'analogue', label: 'Analogue' },
            { id: 'manual', label: 'Manual / override' },
          ].map((opt) => (
            <Chip
              key={opt.label}
              size="small"
              label={opt.label}
              color={methodFilter === opt.id ? 'primary' : 'default'}
              variant={methodFilter === opt.id ? 'filled' : 'outlined'}
              onClick={() => setMethodFilter(opt.id)}
              data-testid={`forecast-method-filter-${opt.id ?? 'all'}`}
            />
          ))}
        </Stack>
        <ModuleDataSection
          introWhen="always"
          intro="History is the source of the forecast: Compute from history writes velocity (52wk × seasonal) and analogue rows into fact_demand_forecast. Paste and Add row are overrides — they never merge into sell-out actuals. Rollups are plain sums."
          isLoading={isLoading}
          isError={isError}
          error={toQueryError(error)}
          onRetry={() => void refetch()}
          isEmpty={rows.length === 0}
          empty={{
            title: 'No forecast rows yet',
            description: 'Compute from sell-out history first. Paste or add a row only to override a generated value.',
            primary: { label: 'Compute from history', onClick: runComputeFromHistory },
            secondary: { label: 'Paste override', onClick: () => setPasteOpen(true) },
          }}
          toolbar={
            <ModuleGridToolbar
              leading={
                <Button
                  startIcon={<HistoryIcon />}
                  variant="contained"
                  size="small"
                  disabled={busy}
                  onClick={runComputeFromHistory}
                  data-testid="forecast-compute-from-history"
                >
                  Compute from history
                </Button>
              }
              onRefresh={() => qc.invalidateQueries({ queryKey: ['forecasts'] })}
              onClearAll={() => {
                if (!window.confirm('Delete every forecast row? This cannot be undone.')) return;
                void clearAll.mutate();
              }}
              onAdd={() => setAddOpen(true)}
              addLabel="Add override"
              addVariant="outlined"
              onUpload={() => setPasteOpen(true)}
              uploadLabel="Paste override"
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
        title="Paste override"
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
        <DialogTitle>Add override row</DialogTitle>
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
