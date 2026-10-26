'use client';

import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  Collapse,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  InputLabel,
  List,
  ListItemButton,
  ListItemText,
  ListSubheader,
  MenuItem,
  Select,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CellStyle, ColDef } from 'ag-grid-community';
import { useMemo, useState, type ReactNode } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { useProductLines } from '@/features/catalog/useProductLines';
import type { DefinitionV2 } from '@/features/dashboards/builder/types';
import type { ChartControlsState } from '@/features/workbench-ui/ChartControls';
import { RankedBars, StateKey, TrendChart, axisTitle, formatMeasure, rankBars, type MeasureUnit } from '@/features/workbench-ui/charts';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { StatusChip } from '@/features/workbench-ui/controls';
import { apiDelete, apiDownloadBlob, apiGet, apiPost, safeDisplayError } from '@/lib/api';

import {
  asOfLabel,
  buildBars,
  buildKpis,
  buildLookups,
  buildResultTable,
  dimensionLabel,
  formatCell,
  grainSetKey,
  grainSetLabel,
  groupMetricsByFamily,
  metricPresentation,
  ruleLabel,
  scopeLabel,
  seriesOf,
  stateTone,
  type CatalogResponse,
  type CustomerOption,
  type DistributorOption,
  type EntityLookups,
  type QueryResult,
  type ResultTable,
  type SemanticMetric,
} from './reportPresentation';

type SavedReport = {
  id: number;
  name: string;
  description: string | null;
  visibility: string;
  shared_roles: string[];
  metric_key: string;
  grains: string[];
  filters: Record<string, unknown>;
  visual: string;
  period_grain?: string | null;
  updated_at?: string | null;
  overview_pinned?: boolean;
  definition_v2?: DefinitionV2 | null;
};

type Schedule = {
  id: number;
  saved_report_id: number | null;
  name: string;
  cadence: string;
  enabled: boolean;
  last_run_at: string | null;
  next_run_at: string | null;
};

type Delivery = {
  id: number;
  saved_report_id: number | null;
  trigger: string;
  format: string;
  status: string;
  subject: string;
  missing_data_alert: boolean;
  created_at: string | null;
};

type DashboardsResponse = {
  items: { id: number; name: string; widgets?: { saved_report_id?: number | null }[] }[];
};

export type VisualMode = 'kpi' | 'table' | 'bar' | 'line';

type Cadence = 'weekly_monday_0700' | 'daily_0700' | 'on_import_complete';

const CADENCE_LABEL: Record<string, string> = {
  weekly_monday_0700: 'Mondays 07:00',
  daily_0700: 'Daily 07:00',
  on_import_complete: 'After each import',
};

const oneLine = { whiteSpace: 'nowrap', flexShrink: 0 } as const;

function savedVisual(v: string | null | undefined): VisualMode {
  if (v === 'table' || v === 'bar' || v === 'kpi') return v;
  if (v === 'line' || v === 'area') return 'line';
  return 'kpi';
}

function whenLabel(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const days = (now.getTime() - d.getTime()) / 86_400_000;
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  if (days < 1 && d.getDate() === now.getDate()) return `Today ${time}`;
  if (days < 7) return `${d.toLocaleDateString('en-GB', { weekday: 'short' })} ${time}`;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

/** Delivery subjects carry "Name (metric_key)"; show the saved report's name instead. */
function runTitle(d: Delivery, savedById: Map<number, SavedReport>): string {
  const s = d.saved_report_id != null ? savedById.get(d.saved_report_id) : undefined;
  if (s) return s.name;
  return d.subject.replace(/^\[MISSING DATA\]\s*/, '').replace(/\s*\([a-z0-9_.]+\)\s*$/i, '');
}

export function ReportBuilderView() {
  const qc = useQueryClient();
  const catalogQ = useQuery({
    queryKey: ['semantics-catalog'],
    queryFn: ({ signal }) => apiGet<CatalogResponse>('/api/v1/semantics/catalog', { signal }),
  });
  const savedQ = useQuery({
    queryKey: ['saved-reports'],
    queryFn: ({ signal }) => apiGet<{ items: SavedReport[] }>('/api/v1/saved-reports', { signal }),
    retry: false,
  });
  const schedulesQ = useQuery({
    queryKey: ['report-schedules'],
    queryFn: ({ signal }) => apiGet<{ items: Schedule[] }>('/api/v1/reports/schedules', { signal }),
    retry: false,
  });
  const inboxQ = useQuery({
    queryKey: ['report-inbox', 'recent'],
    queryFn: ({ signal }) => apiGet<{ items: Delivery[] }>('/api/v1/reports/inbox?limit=200', { signal }),
    retry: false,
  });
  const dashboardsQ = useQuery({
    queryKey: ['dashboards'],
    queryFn: ({ signal }) => apiGet<DashboardsResponse>('/api/v1/dashboards', { signal }),
    retry: false,
  });
  const entitiesQ = useQuery({
    queryKey: ['sellout-filter-options'],
    queryFn: ({ signal }) =>
      apiGet<{ distributors: DistributorOption[]; customers?: CustomerOption[] }>('/api/v1/sellout/filter-options', { signal }),
    retry: false,
  });

  const lookups: EntityLookups = useMemo(() => buildLookups(entitiesQ.data), [entitiesQ.data]);

  const allMetrics = useMemo(() => catalogQ.data?.metrics ?? [], [catalogQ.data]);
  const queryableMetrics = useMemo(
    () => allMetrics.filter((m) => m.status === 'implemented' && !m.refuse_all && m.handler_backed !== false),
    [allMetrics],
  );
  const notRunnable = useMemo(
    () => allMetrics.filter((m) => !(m.status === 'implemented' && !m.refuse_all && m.handler_backed !== false)),
    [allMetrics],
  );
  const families = useMemo(() => groupMetricsByFamily(queryableMetrics), [queryableMetrics]);

  const [metricKey, setMetricKey] = useState('weeks_of_cover');
  const [grains, setGrains] = useState<string[]>(['distributor', 'product']);
  const [periodFrom, setPeriodFrom] = useState('26Q2');
  const [periodTo, setPeriodTo] = useState('26Q2');
  const [periodGrain, setPeriodGrain] = useState<string | null>(null);
  const [distributorId, setDistributorId] = useState('');
  const [bu, setBu] = useState('');
  const [visual, setVisual] = useState<VisualMode>('kpi');
  const [result, setResult] = useState<QueryResult | null>(null);
  const [ranFilters, setRanFilters] = useState<Record<string, string>>({});
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState('');
  const [publishOnSave, setPublishOnSave] = useState(false);
  const [loadedSavedId, setLoadedSavedId] = useState<number | null>(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleName, setScheduleName] = useState('');
  const [scheduleCadence, setScheduleCadence] = useState<Cadence>('weekly_monday_0700');
  const [exportBusy, setExportBusy] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const savedItems = useMemo(() => savedQ.data?.items ?? [], [savedQ.data]);
  const savedById = useMemo(() => new Map(savedItems.map((s) => [s.id, s])), [savedItems]);
  const loadedSaved = loadedSavedId != null ? savedById.get(loadedSavedId) ?? null : null;
  const savedDefinition = loadedSaved?.definition_v2 ?? null;

  const selected = queryableMetrics.find((m) => m.key === metricKey) ?? null;
  const metricLabelOf = (key: string) => allMetrics.find((m) => m.key === key)?.label ?? 'Saved figure';

  const allowedGrainSets = useMemo(() => selected?.allowed_grains ?? [], [selected]);
  const grainChoices = useMemo(() => {
    const sets = allowedGrainSets.map((g) => [...g].sort());
    if (grains.length && !sets.some((s) => grainSetKey(s) === grainSetKey(grains))) sets.push([...grains].sort());
    return sets;
  }, [allowedGrainSets, grains]);

  const needsPeriod = grains.includes('period');
  const needsDistProduct = grains.includes('distributor') || grains.includes('product');
  const needsBu = grains.includes('bu') || metricKey === 'volume_bias';
  const productLinesQ = useProductLines({ enabled: needsBu });
  const productLineLabel = (code: string) =>
    productLinesQ.data?.product_lines.find((l) => l.code === code)?.label ?? code;

  const distributorOptions = entitiesQ.data?.distributors ?? [];
  const pickedDistributor = distributorOptions.find((d) => String(d.id) === distributorId) ?? null;

  const buildFilters = () => {
    const filters: Record<string, string> = {};
    if (needsPeriod) {
      if (periodFrom.trim()) filters.period_from = periodFrom.trim();
      if (periodTo.trim()) filters.period_to = periodTo.trim();
    }
    if (distributorId.trim()) filters.distributor_id = distributorId.trim();
    if (bu.trim()) filters.bu = bu.trim();
    return filters;
  };

  const runMut = useMutation({
    mutationFn: async () => {
      if (savedDefinition) throw new Error('Download or send this saved report. Start a new report to build another question.');
      const filters = buildFilters();
      const data = await apiPost<QueryResult>('/api/v1/query/execute', {
        metric: metricKey,
        grains,
        filters,
        ...(needsPeriod && periodGrain ? { period_grain: periodGrain } : {}),
      });
      return { data, filters };
    },
    onSuccess: ({ data, filters }) => {
      setResult(data);
      setRanFilters(filters);
    },
  });

  const saveMut = useMutation({
    mutationFn: async () => {
      if (savedDefinition) throw new Error('This saved report keeps its dashboard definition. Start a new report to build another question.');
      return apiPost<SavedReport>('/api/v1/saved-reports', {
        name: saveName.trim() || `${selected?.label ?? metricKey} report`,
        metric: metricKey,
        grains,
        filters: buildFilters(),
        ...(needsPeriod && periodGrain ? { period_grain: periodGrain } : {}),
        visual,
        visibility: publishOnSave ? 'published' : 'personal',
        shared_roles: [],
      });
    },
    onSuccess: async (row) => {
      setSaveOpen(false);
      setSaveName('');
      setLoadedSavedId(row.id);
      setActionErr(null);
      setActionMsg(`Saved “${row.name}”.`);
      await qc.invalidateQueries({ queryKey: ['saved-reports'] });
    },
  });

  const overviewPinMut = useMutation({
    mutationFn: async (report: SavedReport) => {
      const path = `/api/v1/saved-reports/${report.id}/overview-pin`;
      if (report.overview_pinned) {
        await apiDelete(path);
        return;
      }
      await apiPost(path);
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['saved-reports'] });
    },
  });

  const deliverMut = useMutation({
    mutationFn: async (reportId: number) =>
      apiPost<{ id: number; subject: string; missing_data_alert: boolean }>(
        `/api/v1/reports/saved/${reportId}/deliver`,
        { format: 'xlsx' },
      ),
    onSuccess: async (d) => {
      setActionErr(null);
      setActionMsg(
        `Sent to your Report inbox${loadedSaved ? `: ${loadedSaved.name}` : ''}${d.missing_data_alert ? ' — some data is missing, and the report says so' : ''}.`,
      );
      await qc.invalidateQueries({ queryKey: ['report-inbox'] });
    },
    onError: (e) => {
      setActionMsg(null);
      setActionErr(safeDisplayError(e));
    },
  });

  const scheduleMut = useMutation({
    mutationFn: async () => {
      if (loadedSavedId == null) throw new Error('Save the report first');
      const sched = await apiPost<{ id: number }>('/api/v1/reports/schedules', {
        name: scheduleName.trim() || `${loadedSaved?.name ?? selected?.label ?? metricKey} schedule`,
        saved_report_id: loadedSavedId,
        cadence: scheduleCadence,
        format: 'xlsx',
        enabled: true,
        subscriber_user_ids: [],
      });
      await apiPost(`/api/v1/reports/schedules/${sched.id}/run-now`, {});
      return sched;
    },
    onSuccess: async () => {
      setScheduleOpen(false);
      setScheduleName('');
      setScheduleCadence('weekly_monday_0700');
      setActionErr(null);
      setActionMsg('Schedule created, and one copy sent to your Report inbox now.');
      await qc.invalidateQueries({ queryKey: ['report-schedules'] });
      await qc.invalidateQueries({ queryKey: ['report-inbox'] });
    },
    onError: (e) => {
      setActionMsg(null);
      setActionErr(safeDisplayError(e));
    },
  });

  const exportCurrent = async (fmt: 'xlsx' | 'pdf') => {
    setExportBusy(true);
    setActionErr(null);
    setActionMsg(null);
    try {
      if (savedDefinition && loadedSaved) {
        await apiDownloadBlob(`/api/v1/reports/saved/${loadedSaved.id}/export?format=${fmt}`, `${loadedSaved.name}.${fmt}`);
        setActionMsg(`${fmt === 'pdf' ? 'PDF' : 'Excel file'} downloaded from the saved report.`);
        return;
      }
      const stem = `${metricKey}_${grains.join('-')}`;
      // Legacy reports keep exporting the current editable author form.
      await apiDownloadBlob(`/api/v1/reports/export`, `${stem}.${fmt}`, {
        method: 'POST',
        body: JSON.stringify({
          metric: metricKey,
          grains,
          filters: buildFilters(),
          ...(needsPeriod && periodGrain ? { period_grain: periodGrain } : {}),
          format: fmt,
          title: selected?.label || metricKey,
        }),
      });
      setActionMsg(`${fmt === 'pdf' ? 'PDF' : 'Excel file'} downloaded — the as-of date is on the cover.`);
    } catch (e) {
      setActionErr(safeDisplayError(e));
    } finally {
      setExportBusy(false);
    }
  };

  const pickMetric = (next: string) => {
    if (savedDefinition) {
      setPeriodFrom('26Q2');
      setPeriodTo('26Q2');
      setDistributorId('');
      setBu('');
      setVisual('kpi');
    }
    setLoadedSavedId(null);
    setPeriodGrain(null);
    setActionMsg(null);
    setActionErr(null);
    setMetricKey(next);
    setResult(null);
    const m = queryableMetrics.find((x) => x.key === next);
    const first = m?.allowed_grains?.[0];
    if (first) setGrains([...first]);
  };

  const loadSaved = (s: SavedReport) => {
    setLoadedSavedId(s.id);
    setPeriodGrain(s.period_grain ?? null);
    setActionMsg(null);
    setActionErr(null);
    setMetricKey(s.metric_key);
    setGrains([...(s.grains || [])]);
    setVisual(savedVisual(s.visual));
    const f = s.filters || {};
    setPeriodFrom(String(f.period_from || f.period || '26Q2'));
    setPeriodTo(String(f.period_to || f.period || '26Q2'));
    setDistributorId(f.distributor_id != null ? String(f.distributor_id) : '');
    setBu(f.bu != null ? String(f.bu) : f.product_line != null ? String(f.product_line) : '');
    setResult(null);
  };

  /* ---------- derived summary (only from what the API returns) ---------- */
  const pinnedIds = useMemo(() => {
    const ids = new Set<number>();
    for (const d of dashboardsQ.data?.items ?? []) for (const w of d.widgets ?? []) if (w.saved_report_id != null) ids.add(w.saved_report_id);
    return ids;
  }, [dashboardsQ.data]);
  const schedules = schedulesQ.data?.items ?? [];
  const enabledSchedules = schedules.filter((s) => s.enabled);
  const scheduleBySaved = useMemo(() => {
    const m = new Map<number, Schedule>();
    for (const s of schedulesQ.data?.items ?? []) if (s.saved_report_id != null && s.enabled && !m.has(s.saved_report_id)) m.set(s.saved_report_id, s);
    return m;
  }, [schedulesQ.data]);
  const reportRuns = (inboxQ.data?.items ?? []).filter((d) => d.saved_report_id != null);
  const weekAgo = Date.now() - 7 * 86_400_000;
  const runsThisWeek = reportRuns.filter((d) => d.created_at && new Date(d.created_at).getTime() >= weekAgo);
  const failedThisWeek = runsThisWeek.filter((d) => d.status !== 'delivered').length;

  /* ---------- result models ---------- */
  const ctx = useMemo(() => (result && result.ok ? { metric: selected, result, lookups } : null), [result, selected, lookups]);
  const table: ResultTable | null = useMemo(() => (ctx ? buildResultTable(ctx) : null), [ctx]);
  const kpis = useMemo(() => (ctx ? buildKpis(ctx) : []), [ctx]);
  const bars = useMemo(() => (ctx ? buildBars(ctx) : null), [ctx]);
  const series = useMemo(() => seriesOf(result && result.ok ? result : null), [result]);
  const presentation = metricPresentation(selected);
  const canTrend = grains.length === 1 && grains[0] === 'period';
  const effectiveVisual: VisualMode = visual === 'line' && !canTrend ? 'bar' : visual;
  const rows = result?.rows ?? [];
  const scope = scopeLabel(result ? ranFilters : buildFilters(), lookups, productLineLabel);

  const runDisabled = Boolean(savedDefinition) || runMut.isPending || !metricKey || grains.length === 0;
  const exportDisabled = exportBusy || (!savedDefinition && (!metricKey || grains.length === 0));
  const sendReason = loadedSavedId == null ? 'Save the report first — sending and scheduling work on a saved report.' : '';

  const summaryState = (q: { isLoading: boolean; isError: boolean }) => (q.isLoading ? 'loading' : q.isError ? 'empty' : 'ready') as 'loading' | 'empty' | 'ready';

  return (
    <Box data-testid="report-builder">
      <HeadlineStrip columns={4}>
        <HeadlineFigure
          label="Saved reports"
          value={savedItems.length}
          compact
          state={summaryState(savedQ)}
          stateNote={savedQ.isError ? 'Not available right now.' : undefined}
          caption={dashboardsQ.isSuccess ? `${pinnedIds.size} pinned to dashboards` : undefined}
          testId="reports-summary-saved"
        />
        <HeadlineFigure
          label="Scheduled"
          value={enabledSchedules.length}
          compact
          state={summaryState(schedulesQ)}
          stateNote={schedulesQ.isError ? 'Not available right now.' : undefined}
          caption={
            enabledSchedules.length
              ? Array.from(new Set(enabledSchedules.map((s) => CADENCE_LABEL[s.cadence] ?? 'Custom'))).join(' · ')
              : 'Nothing scheduled yet'
          }
          testId="reports-summary-scheduled"
        />
        <HeadlineFigure
          label="Runs this week"
          value={runsThisWeek.length}
          compact
          state={summaryState(inboxQ)}
          stateNote={inboxQ.isError ? 'Not available right now.' : undefined}
          severity={failedThisWeek > 0 ? 'bad' : 'neutral'}
          caption={runsThisWeek.length ? (failedThisWeek ? `${failedThisWeek} failed` : 'None failed') : 'Sent or scheduled runs'}
          testId="reports-summary-runs"
        />
        <HeadlineFigure
          label="Ready to run"
          value={queryableMetrics.length}
          compact
          state={summaryState(catalogQ)}
          stateNote={catalogQ.isError ? 'Not available right now.' : undefined}
          caption="Figures the platform can calculate"
          testId="reports-summary-metrics"
        />
      </HeadlineStrip>

      <Box
        sx={{
          display: 'grid',
          gap: 2,
          mt: 2,
          alignItems: 'start',
          gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: '240px minmax(0, 1fr)', lg: '240px minmax(0, 1fr) 280px' },
        }}
      >
        {/* ---------- metric catalog (md+) ---------- */}
        <Box sx={{ display: { xs: 'none', md: 'block' }, minWidth: 0, gridColumn: { md: '1' }, gridRow: { md: '1 / span 2' } }}>
          <Panel title="Metric" subtitle="Grouped by area; only figures the platform can calculate can run" flush>
            <List component="nav" dense disablePadding sx={{ maxHeight: 640, overflowY: 'auto', pb: 1 }} data-testid="report-metric-catalog" aria-label="Metrics">
              {families.map((f) => (
                <Box key={f.family}>
                  <ListSubheader component="div" disableSticky sx={{ lineHeight: '28px', bgcolor: 'transparent', fontWeight: 600 }}>
                    {f.family}
                  </ListSubheader>
                  <Box>
                    {f.metrics.map((m) => (
                      <ListItemButton
                        key={m.key}
                        selected={m.key === metricKey}
                        onClick={() => pickMetric(m.key)}
                        sx={{ py: 0.5, pl: 2 }}
                        data-testid={`report-metric-${m.key}`}
                      >
                        <ListItemText
                          primary={m.label}
                          secondary={m.allowed_grains.length ? Array.from(new Set(m.allowed_grains.flat())).map(dimensionLabel).join(' · ') : undefined}
                          primaryTypographyProps={{ variant: 'body2' }}
                          secondaryTypographyProps={{ variant: 'caption', noWrap: true }}
                        />
                      </ListItemButton>
                    ))}
                  </Box>
                </Box>
              ))}
              {notRunnable.length ? (
                <Box>
                  <ListSubheader component="div" disableSticky sx={{ lineHeight: '28px', bgcolor: 'transparent', fontWeight: 600 }}>
                    Not available to run
                  </ListSubheader>
                  <Box>
                    {notRunnable.map((m) => (
                      <ListItemButton key={m.key} disabled sx={{ py: 0.5, pl: 2 }}>
                        <ListItemText
                          primary={m.label}
                          secondary={m.status === 'do_not_build' || m.refuse_all ? 'Cannot be calculated from the data we hold' : 'Not calculable yet'}
                          primaryTypographyProps={{ variant: 'body2' }}
                          secondaryTypographyProps={{ variant: 'caption' }}
                        />
                      </ListItemButton>
                    ))}
                  </Box>
                </Box>
              ) : null}
            </List>
          </Panel>
        </Box>

        {/* ---------- question + result ---------- */}
        <Stack spacing={2} sx={{ minWidth: 0, gridColumn: { md: '2' }, gridRow: { md: '1' } }}>
          <Panel
            title={savedDefinition ? loadedSaved!.name : selected?.label ?? metricLabelOf(metricKey)}
            subtitle={
              result?.ok
                ? [`by ${grainSetLabel(result.grains)}`, asOfLabel(result) ? `as of ${asOfLabel(result)}` : null, `${rows.length} ${rows.length === 1 ? 'row' : 'rows'}`]
                    .filter(Boolean)
                    .join(' · ')
                : loadedSaved
                  ? `Saved report: ${loadedSaved.name}`
                  : 'Choose how to break it down, then run'
            }
            actions={
              <Button variant="contained" size="small" onClick={() => runMut.mutate()} disabled={runDisabled} data-testid="report-run" sx={oneLine}>
                {runMut.isPending ? 'Running…' : 'Run report'}
              </Button>
            }
            sx={{ height: 'auto' }}
          >
            <Stack spacing={1.5} data-testid="report-builder-author">
              {savedDefinition ? (
                <Alert severity="info" data-testid="report-saved-definition-note">
                  This report uses its saved measures, breakdowns and filters. Download, send or schedule it here.
                  {savedDefinition.dashboard?.fixed_window
                    ? ` It uses fixed dates: ${savedDefinition.dashboard.fixed_window.from} to ${savedDefinition.dashboard.fixed_window.to}; schedules keep these dates.`
                    : ' It has no fixed date range.'}
                  {' '}To build a different question, use the dashboard builder or start a new report.
                  <Box sx={{ mt: 1 }}><Button size="small" onClick={() => pickMetric('weeks_of_cover')}>Start a new report</Button></Box>
                </Alert>
              ) : <>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} useFlexGap flexWrap="wrap" alignItems={{ sm: 'flex-start' }}>
                <FormControl size="small" sx={{ minWidth: 220, display: { xs: 'flex', md: 'none' } }}>
                  <InputLabel id="report-metric-label">Metric</InputLabel>
                  <Select
                    labelId="report-metric-label"
                    label="Metric"
                    value={selected ? metricKey : ''}
                    data-testid="report-metric-select"
                    onChange={(e) => pickMetric(String(e.target.value))}
                  >
                    {families.flatMap((f) => [
                      <ListSubheader key={`h-${f.family}`}>{f.family}</ListSubheader>,
                      ...f.metrics.map((m) => (
                        <MenuItem key={m.key} value={m.key}>
                          {m.label}
                        </MenuItem>
                      )),
                    ])}
                  </Select>
                </FormControl>
                <FormControl size="small" sx={{ minWidth: 200 }}>
                  <InputLabel id="report-breakdown-label">Break down by</InputLabel>
                  <Select
                    labelId="report-breakdown-label"
                    label="Break down by"
                    value={grains.length ? grainSetKey(grains) : ''}
                    data-testid="report-grain-select"
                    onChange={(e) => {
                      const key = String(e.target.value);
                      const next = grainChoices.find((g) => grainSetKey(g) === key);
                      if (next) {
                        setGrains([...next]);
                        setResult(null);
                      }
                    }}
                  >
                    {grainChoices.map((g) => (
                      <MenuItem key={grainSetKey(g)} value={grainSetKey(g)}>
                        {grainSetLabel(g)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                {needsDistProduct ? (
                  <Autocomplete
                    size="small"
                    sx={{ minWidth: 240, flex: { sm: '1 1 240px' }, maxWidth: { sm: 360 } }}
                    options={distributorOptions}
                    value={pickedDistributor}
                    onChange={(_, v) => setDistributorId(v ? String(v.id) : '')}
                    getOptionLabel={(o) => o.distributor_name || 'Unnamed distributor'}
                    isOptionEqualToValue={(a, b) => a.id === b.id}
                    loading={entitiesQ.isLoading}
                    renderInput={(params) => <TextField {...params} label="Distributor" placeholder="All distributors" />}
                    data-testid="report-distributor-picker"
                  />
                ) : null}
                {needsPeriod ? (
                  <>
                    <TextField size="small" label="From period" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} placeholder="26Q2" sx={{ width: 130 }} inputProps={{ 'data-testid': 'report-period-from' }} />
                    <TextField size="small" label="To period" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} placeholder="26Q2" sx={{ width: 130 }} />
                  </>
                ) : null}
                {needsBu ? (
                  <FormControl size="small" sx={{ minWidth: 180 }}>
                    <InputLabel id="report-bu-label">Product line</InputLabel>
                    <Select labelId="report-bu-label" label="Product line" value={bu} onChange={(e) => setBu(String(e.target.value))} data-testid="report-bu-select">
                      <MenuItem value="">All product lines</MenuItem>
                      {(productLinesQ.data?.product_lines ?? []).map((l) => (
                        <MenuItem key={l.code} value={l.code}>
                          {l.label}
                        </MenuItem>
                      ))}
                      {bu && !(productLinesQ.data?.product_lines ?? []).some((l) => l.code === bu) ? <MenuItem value={bu}>{bu}</MenuItem> : null}
                    </Select>
                  </FormControl>
                ) : null}
                <Box sx={{ flex: 1, display: { xs: 'none', sm: 'block' } }} />
                <ToggleButtonGroup
                  exclusive
                  size="small"
                  value={effectiveVisual}
                  onChange={(_, v) => v && setVisual(v)}
                  data-testid="report-visual-mode"
                  aria-label="Show as"
                  sx={{ alignSelf: { xs: 'flex-start', sm: 'center' } }}
                >
                  <ToggleButton value="kpi" sx={{ px: 1.5, textTransform: 'none' }}>KPI</ToggleButton>
                  <ToggleButton value="bar" sx={{ px: 1.5, textTransform: 'none' }}>Bar</ToggleButton>
                  {canTrend ? <ToggleButton value="line" sx={{ px: 1.5, textTransform: 'none' }}>Trend</ToggleButton> : null}
                  <ToggleButton value="table" sx={{ px: 1.5, textTransform: 'none' }}>Table</ToggleButton>
                </ToggleButtonGroup>
              </Stack>

              <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" data-testid="report-question-chips">
                <Chip size="small" variant="outlined" label={`Metric · ${selected?.label ?? metricLabelOf(metricKey)}`} />
                <Chip size="small" variant="outlined" label={`Breakdown · ${grainSetLabel(result?.ok ? result.grains : grains)}`} />
                <Chip size="small" variant="outlined" label={`Scope · ${scope}`} />
              </Stack>
              </>}

              {runMut.isError ? <Alert severity="error">{safeDisplayError(runMut.error)}</Alert> : null}
              {actionErr ? (
                <Alert severity="error" onClose={() => setActionErr(null)}>
                  {actionErr}
                </Alert>
              ) : null}
              {actionMsg ? (
                <Alert severity="success" onClose={() => setActionMsg(null)} data-testid="report-action-msg">
                  {actionMsg}
                </Alert>
              ) : null}

              {!savedDefinition ? <><ModuleDataSection
                isLoading={catalogQ.isLoading}
                isError={catalogQ.isError}
                error={catalogQ.error instanceof Error ? catalogQ.error : null}
                onRetry={() => catalogQ.refetch()}
                isEmpty={!result && !runMut.isPending}
                empty={{
                  title: 'No report yet',
                  description: 'Pick a figure and how to break it down, then press Run report.',
                }}
              >
                <Box data-testid="report-result">
                  {runMut.isPending && effectiveVisual === 'kpi' ? (
                    <HeadlineStrip columns={3}>
                      <HeadlineFigure label={selected?.label ?? 'Result'} value="" state="loading" lead />
                    </HeadlineStrip>
                  ) : null}
                  {result && !result.ok ? (
                    <Alert severity={result.status === 'refused' ? 'warning' : 'info'} data-testid="report-refused">
                      {result.message || result.validation?.message || 'This combination cannot be calculated.'}
                    </Alert>
                  ) : null}
                  {result?.ok && !runMut.isPending ? (
                    <ResultVisual
                      visual={effectiveVisual}
                      metric={selected}
                      kpis={kpis}
                      bars={bars}
                      series={series}
                      table={table}
                      unitFormat={(v) => formatMeasure(v, presentation.unit, 'short')}
                      unit={presentation.unit}
                      grains={result.grains}
                    />
                  ) : null}
                </Box>
              </ModuleDataSection>

              <AboutFigure metric={selected} result={result?.ok ? result : null} scope={scope} />
              </> : null}

              <Divider />
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center" data-testid="report-actions">
                <Button size="small" variant="outlined" disabled={exportDisabled} onClick={() => void exportCurrent('xlsx')} data-testid="report-export-xlsx" sx={oneLine}>
                  {exportBusy ? 'Exporting…' : 'Export Excel'}
                </Button>
                <Button size="small" variant="outlined" disabled={exportDisabled} onClick={() => void exportCurrent('pdf')} data-testid="report-export-pdf" sx={oneLine}>
                  Export PDF
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  disabled={Boolean(savedDefinition)}
                  onClick={() => {
                    setSaveName(`${selected?.label || metricLabelOf(metricKey)}`);
                    setSaveOpen(true);
                  }}
                  data-testid="report-save"
                  sx={oneLine}
                >
                  Save
                </Button>
                <DisabledReason reason={sendReason}>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={loadedSavedId == null || deliverMut.isPending}
                    onClick={() => loadedSavedId != null && deliverMut.mutate(loadedSavedId)}
                    data-testid="report-deliver-inbox"
                    sx={oneLine}
                  >
                    {deliverMut.isPending ? 'Sending…' : 'Send to inbox'}
                  </Button>
                </DisabledReason>
                <DisabledReason reason={sendReason}>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={loadedSavedId == null}
                    onClick={() => {
                      setScheduleName(`${loadedSaved?.name || selected?.label || metricLabelOf(metricKey)} schedule`);
                      setScheduleCadence('weekly_monday_0700');
                      setScheduleOpen(true);
                    }}
                    data-testid="report-schedule"
                    sx={oneLine}
                  >
                    Schedule
                  </Button>
                </DisabledReason>
                {loadedSavedId == null ? (
                  <Typography variant="caption" color="text.secondary" data-testid="report-send-hint">
                    Save the report to send or schedule it.
                  </Typography>
                ) : (
                  <Typography variant="caption" color="text.secondary" data-testid="report-loaded-saved">
                    Saved report: {loadedSaved?.name ?? 'loaded'}
                  </Typography>
                )}
              </Stack>
            </Stack>
          </Panel>
        </Stack>

        {/* ---------- result table: spans the question and side columns on wide screens ---------- */}
        {!savedDefinition && result?.ok && !runMut.isPending && table && table.rows.length > 0 ? (
          <Box
            sx={{ minWidth: 0, gridColumn: { md: '2', lg: '2 / -1' }, gridRow: { md: '2' } }}
            data-testid={effectiveVisual === 'table' ? 'report-table' : undefined}
          >
            <Panel
              title="Result"
              subtitle={
                effectiveVisual === 'table'
                  ? `Row by row · ${table.rows.length} ${table.rows.length === 1 ? 'row' : 'rows'}`
                  : 'The same numbers as the chart, row by row'
              }
              flush
              sx={{ height: 'auto' }}
            >
              <ResultGrid table={table} />
            </Panel>
          </Box>
        ) : null}

        {/* ---------- saved reports + recent runs ---------- */}
        <Stack spacing={2} sx={{ minWidth: 0, gridColumn: { md: '1 / -1', lg: '3' }, gridRow: { md: '3', lg: '1' } }}>
          <Panel title="Saved reports" subtitle="Yours and the ones shared with you" flush sx={{ height: 'auto' }}>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }} data-testid="saved-reports-panel">
              {savedQ.isError ? (
                <Typography variant="body2" color="text.secondary" sx={{ px: 1, py: 1 }}>
                  Saved reports are not available right now.
                </Typography>
              ) : null}
              {savedItems.map((s) => {
                const sched = scheduleBySaved.get(s.id);
                return (
                  <Box key={s.id} data-testid={`saved-report-${s.id}`}>
                  <PanelRow
                    severity={loadedSavedId === s.id ? 'info' : 'neutral'}
                    primary={s.name}
                    secondary={[
                      ...(s.definition_v2 ? ['Saved question', s.definition_v2.dashboard?.fixed_window
                        ? `Fixed dates: ${s.definition_v2.dashboard.fixed_window.from} to ${s.definition_v2.dashboard.fixed_window.to}`
                        : 'No fixed date range'] : [metricLabelOf(s.metric_key), grainSetLabel(s.grains || [])]),
                      sched ? CADENCE_LABEL[sched.cadence] ?? 'Scheduled' : s.visibility === 'published' ? 'Shared' : 'Only you',
                    ].join(' · ')}
                    figure={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }} onClick={(e) => e.stopPropagation()}>
                        {pinnedIds.has(s.id) ? <StatusChip label="pinned" tone="info" /> : null}
                        <Button
                          size="small"
                          variant="text"
                          data-testid={`overview-pin-${s.id}`}
                          onClick={() => overviewPinMut.mutate(s)}
                        >
                          {s.overview_pinned ? 'Unpin' : 'Pin to Overview'}
                        </Button>
                      </Box>
                    }
                    onClick={() => loadSaved(s)}
                  />
                  </Box>
                );
              })}
              {!savedQ.isLoading && !savedQ.isError && savedItems.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ px: 1, py: 1 }}>
                  No saved reports yet. Run a report and press Save.
                </Typography>
              ) : null}
            </Stack>
          </Panel>
          <Panel title="Recent runs" subtitle="Reports sent to the inbox, newest first" flush sx={{ height: 'auto' }}>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }} data-testid="recent-runs-panel">
              {inboxQ.isError ? (
                <Typography variant="body2" color="text.secondary" sx={{ px: 1, py: 1 }}>
                  Recent runs are not available right now.
                </Typography>
              ) : null}
              {reportRuns.slice(0, 5).map((d) => (
                <PanelRow
                  key={d.id}
                  severity={d.status !== 'delivered' ? 'danger' : d.missing_data_alert ? 'warning' : 'neutral'}
                  primary={runTitle(d, savedById)}
                  secondary={[
                    whenLabel(d.created_at),
                    d.trigger === 'schedule' || d.trigger === 'scheduled' ? 'scheduled' : null,
                    d.format ? d.format.toUpperCase() : null,
                    d.status !== 'delivered' ? 'failed' : d.missing_data_alert ? 'missing data' : 'delivered',
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                  href="/inbox"
                />
              ))}
              {!inboxQ.isLoading && !inboxQ.isError && reportRuns.length === 0 ? (
                <Typography variant="body2" color="text.secondary" sx={{ px: 1, py: 1 }}>
                  No runs yet. Sending or scheduling a saved report adds it here.
                </Typography>
              ) : null}
            </Stack>
          </Panel>
          <Typography variant="caption" color="text.secondary">
            A report answers a question once; a dashboard keeps showing it. Pinning copies the question, not a snapshot of the numbers.
          </Typography>
        </Stack>
      </Box>

      <Dialog open={saveOpen} onClose={() => setSaveOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Save report</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="Name" value={saveName} onChange={(e) => setSaveName(e.target.value)} fullWidth autoFocus inputProps={{ 'data-testid': 'report-save-name' }} />
            <FormControlLabel
              control={<Switch checked={publishOnSave} onChange={(e) => setPublishOnSave(e.target.checked)} />}
              label="Share with everyone in your organisation"
            />
            {saveMut.isError ? <Alert severity="error">{safeDisplayError(saveMut.error)}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSaveOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => saveMut.mutate()} disabled={saveMut.isPending || !saveName.trim()} data-testid="report-save-confirm">
            {saveMut.isPending ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={scheduleOpen} onClose={() => setScheduleOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Schedule delivery</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              The report is sent even when some data is missing — it says what is missing. One copy goes to your Report inbox
              now. Weekly and daily deliveries go out at 07:00 UTC; “after each import” sends when new distributor or shipment
              data has been applied.
            </Typography>
            <FormControl fullWidth>
              <InputLabel id="report-schedule-cadence-label">How often</InputLabel>
              <Select
                labelId="report-schedule-cadence-label"
                label="How often"
                value={scheduleCadence}
                onChange={(e) => setScheduleCadence(e.target.value as Cadence)}
                inputProps={{ 'data-testid': 'report-schedule-cadence' }}
              >
                <MenuItem value="weekly_monday_0700">Every Monday, 07:00 UTC</MenuItem>
                <MenuItem value="daily_0700">Every day, 07:00 UTC</MenuItem>
                <MenuItem value="on_import_complete">After each import</MenuItem>
              </Select>
            </FormControl>
            <TextField label="Schedule name" value={scheduleName} onChange={(e) => setScheduleName(e.target.value)} fullWidth inputProps={{ 'data-testid': 'report-schedule-name' }} />
            {scheduleMut.isError ? <Alert severity="error">{safeDisplayError(scheduleMut.error)}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setScheduleOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => scheduleMut.mutate()}
            disabled={scheduleMut.isPending || loadedSavedId == null || !scheduleName.trim()}
            data-testid="report-schedule-confirm"
          >
            {scheduleMut.isPending ? 'Scheduling…' : 'Schedule and send now'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

/** Disabled MUI buttons swallow pointer events; the span carries the tooltip with the reason. */
function DisabledReason({ reason, children }: { reason: string; children: ReactNode }) {
  if (!reason) return <>{children}</>;
  return (
    <Tooltip title={reason}>
      <span style={{ display: 'inline-flex' }}>{children}</span>
    </Tooltip>
  );
}

function ResultVisual({
  visual,
  metric,
  kpis,
  bars,
  series,
  table,
  unitFormat,
  unit,
  grains,
}: {
  visual: VisualMode;
  metric: SemanticMetric | null;
  kpis: ReturnType<typeof buildKpis>;
  bars: ReturnType<typeof buildBars> | null;
  series: { label: string; value: number }[] | null;
  table: ResultTable | null;
  unitFormat: (v: number) => string;
  unit: MeasureUnit;
  /** Breakdown of the result: titles the category axis ("Distributor × Product"). */
  grains: string[];
}) {
  const label = metric?.label ?? 'Result';
  if (visual === 'kpi') {
    return (
      <Box
        data-testid="report-kpi"
        sx={{
          display: 'grid',
          gap: 1.5,
          gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: kpis.length > 1 ? `2fr repeat(${kpis.length - 1}, minmax(0, 1fr))` : 'minmax(0, 1fr)' },
          '& > :first-of-type': { gridColumn: { xs: '1 / -1', md: 'auto' } },
        }}
      >
        {kpis.map((k) => (
          <HeadlineFigure
            key={k.id}
            label={k.label}
            value={k.value}
            unit={k.unit}
            severity={k.severity}
            delta={k.delta}
            target={k.target}
            caption={k.caption}
            sparkline={k.sparkline}
            state={k.state}
            stateNote={k.stateNote}
            lead={k.lead}
            testId={`report-kpi-${k.id}`}
          />
        ))}
      </Box>
    );
  }
  if (visual === 'line' && series) {
    return (
      <Box data-testid="report-trend">
        <TrendChart
          data={series.map((s) => ({ label: s.label, value: s.value }))}
          x="label"
          series={[{ key: 'value', label, kind: 'line', tone: 'primary' }]}
          height={260}
          unit={unit}
          // The result carries no week/month/quarter word, so the time axis is titled "Period".
          xAxisTitle={dimensionLabel('period')}
          yAxisTitle={axisTitle(label, unit)}
          lastPointLabel
          legend={false}
          summary={`Line chart of ${label} by period, ${series[0].label} to ${series[series.length - 1].label}, latest ${unitFormat(series[series.length - 1].value)}`}
        />
      </Box>
    );
  }
  if (visual === 'table') {
    return table && table.rows.length ? (
      <Typography variant="body2" color="text.secondary">
        Shown as a table below.
      </Typography>
    ) : (
      <Typography variant="body2" color="text.secondary" data-testid="report-table">
        The result has a total only — see the KPI view.
      </Typography>
    );
  }
  // bar
  if (!bars || bars.data.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary" data-testid="report-bar">
        Nothing to chart: the result has a total only.
      </Typography>
    );
  }
  // Keyed by the starting sort so a metric with the other direction starts fresh.
  return <ReportBars key={bars.sort} bars={bars} label={label} unit={unit} categoryTitle={grainSetLabel(grains)} />;
}

/** Ranked bars with the toolbar state held here, so the caption above and the chart agree (N-0114). */
function ReportBars({
  bars,
  label,
  unit,
  categoryTitle,
}: {
  bars: NonNullable<ReturnType<typeof buildBars>>;
  label: string;
  unit: MeasureUnit;
  categoryTitle: string;
}) {
  // 25 is the nearest offered top-N choice to the previous fixed cap of 20.
  const [controls, setControls] = useState<ChartControlsState>({ topN: 25, sort: { by: 'value', dir: bars.sort } });
  const ranked = rankBars(bars.data, { sort: bars.sort, max: Infinity });
  const shown = controls.topN === 'all' ? ranked.total : Math.min(controls.topN, ranked.total);
  const sortWords =
    controls.sort.by === 'name'
      ? 'by name'
      : controls.sort.by === 'period'
        ? 'as listed'
        : controls.sort.dir === 'asc'
          ? 'lowest first'
          : 'highest first';
  return (
    <Box data-testid="report-bar">
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
        {`Sorted ${sortWords}`}
        {bars.threshold ? ` · ${bars.threshold.label} marked` : ''}
        {ranked.withoutValue ? ` · ${ranked.withoutValue} without a value` : ''}
      </Typography>
      <RankedBars
        data={bars.data}
        sort={bars.sort}
        controls={{ ...controls, onChange: setControls }}
        threshold={bars.threshold}
        unit={unit}
        summary={`Horizontal bar chart of ${label}, ${shown} rows sorted ${sortWords}${bars.threshold ? `, ${bars.threshold.label} marked` : ''}. Values are listed in the table that follows.`}
        labelHeader={categoryTitle}
        valueHeader={label}
        xAxisTitle={categoryTitle}
        yAxisTitle={axisTitle(label, unit)}
        testId="report-bars"
      />
      {bars.key ? <StateKey items={bars.key} /> : null}
    </Box>
  );
}

// The shared grid lays cells out with flex, so right alignment needs justify-content, not text-align.
const NUMERIC_CELL: CellStyle = { fontVariantNumeric: 'tabular-nums', justifyContent: 'flex-end' };
const CODE_CELL: CellStyle = { opacity: 0.72 };

function ResultGrid({ table }: { table: ResultTable }) {
  const colDefs = useMemo<ColDef[]>(
    () =>
      table.columns.map((c, i) => ({
        field: c.field,
        headerName: c.header,
        flex: c.kind === 'name' ? 1.4 : 1,
        minWidth: c.kind === 'name' ? 180 : c.kind === 'code' ? 110 : 120,
        type: c.numeric ? 'rightAligned' : undefined,
        cellStyle: c.numeric ? NUMERIC_CELL : c.kind === 'code' ? CODE_CELL : undefined,
        valueFormatter: (p: { value: unknown; node?: { rowPinned?: string | null } | null }) =>
          p.node?.rowPinned && i === 0 && typeof p.value === 'string' ? p.value : formatCell(c, p.value),
        ...(c.kind === 'state'
          ? {
              cellRenderer: (p: { value: unknown; node?: { rowPinned?: string | null } | null }) =>
                p.value && !p.node?.rowPinned ? <StatusChip label={formatCell(c, p.value)} tone={stateTone(p.value)} /> : null,
              sortable: false,
            }
          : {}),
      })),
    [table],
  );
  const pinned = useMemo(() => {
    const first = table.columns[0]?.field;
    const row: Record<string, unknown> = { ...table.totals };
    if (first) row[first] = table.totalLabel;
    return [row];
  }, [table]);
  const height = Math.min(460, 44 + 36 * (table.rows.length + 1) + 4);
  return (
    <EnterpriseDataGrid
      rowData={table.rows}
      columnDefs={colDefs}
      height={height}
      gridOptions={{
        pinnedBottomRowData: pinned,
        getRowStyle: (p) => (p.node.rowPinned ? { fontWeight: 600 } : undefined),
      }}
    />
  );
}

function AboutFigure({ metric, result, scope }: { metric: SemanticMetric | null; result: QueryResult | null; scope: string }) {
  const [open, setOpen] = useState(false);
  const p = metricPresentation(metric);
  const sets = metric?.allowed_grains ?? [];
  const asOf = result ? asOfLabel(result) : null;
  const rules = Array.from(new Set((result?.invariants_applied ?? []).map(ruleLabel)));
  return (
    <Box data-testid="report-about">
      <Button
        size="small"
        variant="text"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls="report-about-body"
        endIcon={<ExpandMoreIcon sx={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 120ms' }} />}
        sx={{ px: 0.5, ...oneLine }}
      >
        About this figure
      </Button>
      <Collapse in={open} id="report-about-body">
        <Box sx={{ mt: 0.5, p: 1.5, borderRadius: 1, bgcolor: 'action.hover', display: 'grid', gap: 1 }}>
          <AboutRow title="What it measures">{p.about || 'No description yet.'}</AboutRow>
          {sets.length ? <AboutRow title="Ways to break it down">{sets.map((g) => grainSetLabel(g)).join(' · ')}</AboutRow> : null}
          <AboutRow title="This run">
            {[scope, asOf ? `Data as of ${asOf}` : null, result ? `${(result.rows ?? []).length} rows` : 'Not run yet'].filter(Boolean).join(' · ')}
          </AboutRow>
          {rules.length ? (
            <AboutRow title="Rules applied">
              <Box component="ul" sx={{ m: 0, pl: 2.25 }}>
                {rules.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </Box>
            </AboutRow>
          ) : null}
        </Box>
      </Collapse>
    </Box>
  );
}

function AboutRow({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Box>
      <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.primary', display: 'block' }}>
        {title}
      </Typography>
      <Typography variant="body2" component="div" color="text.secondary">
        {children}
      </Typography>
    </Box>
  );
}
