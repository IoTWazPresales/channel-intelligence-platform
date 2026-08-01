'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { useMutation, useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

type SemanticMetric = {
  id: string;
  key: string;
  label: string;
  status: string;
  formula: string;
  allowed_grains: string[][];
  refuse_all?: boolean;
};

type CatalogResponse = {
  version: number;
  source_doc: string;
  metrics: SemanticMetric[];
  dimensions: { id: string; label: string }[];
};

type QueryResult = {
  ok: boolean;
  status: string;
  metric_id: string | null;
  metric_key: string | null;
  grains: string[];
  filters: Record<string, unknown>;
  validation: { ok: boolean; message: string; allowed_grains?: string[][] };
  invariants_applied: string[];
  data_vintage: Record<string, unknown> | null;
  value: unknown;
  rows: Record<string, unknown>[] | null;
  scorecard: Record<string, unknown> | null;
  cache: { hit: boolean; ttl_seconds: number; key: string } | null;
  message: string | null;
  handler: string | null;
};

export type VisualMode = 'kpi' | 'table' | 'bar';

function formatValue(v: unknown): string {
  if (v == null) return '—';
  if (typeof v === 'number') {
    if (Math.abs(v) <= 1.5 && Number.isFinite(v)) return `${(v * 100).toFixed(1)}%`;
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

function rowChartLabel(row: Record<string, unknown>): string {
  const parts = [
    row.distributor_id != null ? `D${row.distributor_id}` : null,
    row.product_id != null ? `P${row.product_id}` : null,
    row.bu != null ? String(row.bu) : null,
    row.customer_name != null ? String(row.customer_name) : null,
    row.period != null ? String(row.period) : null,
  ].filter(Boolean);
  return parts.join(' · ') || 'row';
}

export function ReportBuilderView() {
  const catalogQ = useQuery({
    queryKey: ['semantics-catalog'],
    queryFn: ({ signal }) => apiGet<CatalogResponse>('/api/v1/semantics/catalog', { signal }),
  });

  const queryableMetrics = useMemo(() => {
    const metrics = catalogQ.data?.metrics ?? [];
    return metrics.filter((m) => m.status === 'implemented' && !m.refuse_all);
  }, [catalogQ.data]);

  const [metricKey, setMetricKey] = useState('weeks_of_cover');
  const [grains, setGrains] = useState<string[]>(['distributor', 'product']);
  const [periodFrom, setPeriodFrom] = useState('26Q2');
  const [periodTo, setPeriodTo] = useState('26Q2');
  const [distributorId, setDistributorId] = useState('');
  const [bu, setBu] = useState('');
  const [visual, setVisual] = useState<VisualMode>('kpi');
  const [result, setResult] = useState<QueryResult | null>(null);

  const selected = queryableMetrics.find((m) => m.key === metricKey) ?? null;

  const allowedGrainSets = selected?.allowed_grains ?? [];
  const grainOptions = useMemo(() => {
    const s = new Set<string>();
    for (const g of allowedGrainSets) for (const d of g) s.add(d);
    return [...s].sort();
  }, [allowedGrainSets]);

  const needsPeriod = grains.includes('period');
  const needsDistProduct = grains.includes('distributor') || grains.includes('product');

  const runMut = useMutation({
    mutationFn: async () => {
      const filters: Record<string, string> = {};
      if (needsPeriod) {
        if (periodFrom.trim()) filters.period_from = periodFrom.trim();
        if (periodTo.trim()) filters.period_to = periodTo.trim();
      }
      if (distributorId.trim()) filters.distributor_id = distributorId.trim();
      if (bu.trim()) filters.bu = bu.trim();
      return apiPost<QueryResult>('/api/v1/query/execute', {
        metric: metricKey,
        grains,
        filters,
      });
    },
    onSuccess: (data) => setResult(data),
  });

  const columns = useMemo<ColDef[]>(() => {
    const rows = result?.rows ?? [];
    if (!rows.length) return [{ field: 'value', headerName: 'Value', flex: 1 }];
    const keys = Object.keys(rows[0]).filter((k) => k !== 'value' || true);
    return keys.map((k) => ({
      field: k,
      headerName: k,
      flex: 1,
      valueFormatter: (p: { value: unknown }) =>
        typeof p.value === 'number' ? formatValue(p.value) : p.value == null ? '—' : String(p.value),
    }));
  }, [result]);

  const chartData = useMemo(() => {
    const rows = result?.rows ?? [];
    return rows.slice(0, 40).map((r) => ({
      name: rowChartLabel(r),
      value: typeof r.value === 'number' ? r.value : Number(r.value) || 0,
    }));
  }, [result]);

  return (
    <Stack spacing={2}>
      <Paper sx={{ p: 2 }} data-testid="report-builder-author">
        <Typography variant="subtitle1" fontWeight={700} gutterBottom>
          Author
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Pick a governed metric, choose a valid grain, then run. Invalid combinations are refused by the semantic
          layer — same numbers as Channel Ops / Plan vs Executed / CPOR.
        </Typography>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'flex-start' }}>
          <FormControl sx={{ minWidth: 260 }} size="small">
            <InputLabel id="report-metric-label">Metric</InputLabel>
            <Select
              labelId="report-metric-label"
              label="Metric"
              value={metricKey}
              data-testid="report-metric-select"
              onChange={(e) => {
                const next = String(e.target.value);
                setMetricKey(next);
                setResult(null);
                const m = queryableMetrics.find((x) => x.key === next);
                const first = m?.allowed_grains?.[0];
                if (first) setGrains([...first]);
              }}
            >
              {queryableMetrics.map((m) => (
                <MenuItem key={m.key} value={m.key}>
                  {m.label} ({m.key})
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <Box sx={{ flex: 1 }}>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
              Dimensions (grain)
            </Typography>
            <Stack direction="row" flexWrap="wrap" gap={0.75} data-testid="report-grain-chips">
              {grainOptions.map((g) => {
                const on = grains.includes(g);
                return (
                  <Chip
                    key={g}
                    label={g}
                    size="small"
                    color={on ? 'primary' : 'default'}
                    variant={on ? 'filled' : 'outlined'}
                    onClick={() => {
                      setResult(null);
                      setGrains((prev) =>
                        prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g].sort()
                      );
                    }}
                  />
                );
              })}
            </Stack>
            {allowedGrainSets.length > 0 && (
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.75 }}>
                Allowed:{' '}
                {allowedGrainSets.map((g) => `{${g.join(', ')}}`).join('; ')}
              </Typography>
            )}
          </Box>
        </Stack>

        {selected?.formula && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5 }}>
            Formula: {selected.formula}
          </Typography>
        )}

        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mt: 2 }}>
          {needsPeriod && (
            <>
              <TextField
                size="small"
                label="Period from"
                value={periodFrom}
                onChange={(e) => setPeriodFrom(e.target.value)}
                placeholder="26Q2"
                data-testid="report-period-from"
              />
              <TextField
                size="small"
                label="Period to"
                value={periodTo}
                onChange={(e) => setPeriodTo(e.target.value)}
                placeholder="26Q2"
              />
            </>
          )}
          {needsDistProduct && (
            <TextField
              size="small"
              label="Distributor id (optional)"
              value={distributorId}
              onChange={(e) => setDistributorId(e.target.value)}
            />
          )}
          {(grains.includes('bu') || metricKey === 'volume_bias') && (
            <TextField size="small" label="BU filter (optional)" value={bu} onChange={(e) => setBu(e.target.value)} />
          )}
        </Stack>

        <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 2 }}>
          <ToggleButtonGroup
            exclusive
            size="small"
            value={visual}
            onChange={(_, v) => v && setVisual(v)}
            data-testid="report-visual-mode"
          >
            <ToggleButton value="kpi">KPI</ToggleButton>
            <ToggleButton value="table">Table</ToggleButton>
            <ToggleButton value="bar">Bar</ToggleButton>
          </ToggleButtonGroup>
          <Button
            variant="contained"
            onClick={() => runMut.mutate()}
            disabled={runMut.isPending || !metricKey || grains.length === 0}
            data-testid="report-run"
          >
            {runMut.isPending ? 'Running…' : 'Run report'}
          </Button>
        </Stack>
      </Paper>

      {runMut.isError && (
        <Alert severity="error">{safeDisplayError(runMut.error)}</Alert>
      )}

      <ModuleDataSection
        isLoading={catalogQ.isLoading}
        isError={catalogQ.isError}
        error={catalogQ.error instanceof Error ? catalogQ.error : null}
        onRetry={() => catalogQ.refetch()}
        isEmpty={!result && !runMut.isPending}
        empty={{
          title: 'No report yet',
          description: 'Run a report to see governed numbers here.',
        }}
      >
        {result && (
          <Stack spacing={1.5} data-testid="report-result">
            {!result.ok && (
              <Alert severity={result.status === 'refused' ? 'warning' : 'info'}>
                {result.message || result.validation?.message || result.status}
              </Alert>
            )}
            {result.ok && (
              <Alert severity="success" data-testid="report-vintage">
                {result.metric_key} · grain {'{'}
                {result.grains.join(', ')}
                {'}'}
                {result.data_vintage
                  ? ` · vintage ${JSON.stringify(result.data_vintage)}`
                  : ''}
                {result.cache ? ` · cache ${result.cache.hit ? 'hit' : 'miss'}` : ''}
              </Alert>
            )}
            {result.invariants_applied?.length > 0 && (
              <Stack direction="row" flexWrap="wrap" gap={0.5}>
                {result.invariants_applied.map((inv) => (
                  <Chip key={inv} size="small" label={inv} variant="outlined" />
                ))}
              </Stack>
            )}

            {result.ok && visual === 'kpi' && (
              <Paper variant="outlined" sx={{ p: 3 }} data-testid="report-kpi">
                <Typography variant="overline" color="text.secondary">
                  Value
                </Typography>
                <Typography variant="h3" fontWeight={700}>
                  {formatValue(result.value)}
                </Typography>
              </Paper>
            )}

            {result.ok && visual === 'table' && (
              <Box sx={{ height: 420 }} data-testid="report-table">
                <EnterpriseDataGrid
                  rowData={result.rows ?? []}
                  columnDefs={columns}
                  height={420}
                  gridOptions={{
                    getRowId: (p) =>
                      String(
                        (p.data as Record<string, unknown>).product_id ??
                          (p.data as Record<string, unknown>).customer_id ??
                          (p.data as Record<string, unknown>).bu ??
                          (p.data as Record<string, unknown>).period ??
                          JSON.stringify(p.data)
                      ),
                  }}
                />
              </Box>
            )}

            {result.ok && visual === 'bar' && (
              <Box sx={{ height: 320 }} data-testid="report-bar">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" hide={chartData.length > 12} interval={0} angle={-30} textAnchor="end" height={70} />
                    <YAxis />
                    <RechartsTooltip />
                    <Bar dataKey="value" fill="#1976d2" />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            )}
          </Stack>
        )}
      </ModuleDataSection>
    </Stack>
  );
}
