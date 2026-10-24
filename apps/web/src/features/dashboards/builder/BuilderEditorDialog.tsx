'use client';

/**
 * Widget editor on the v2 catalog (spec s.4, S7, S8): measures from one model (or one governed
 * metric), up to 3 breakdowns in order, period grain, this widget's own filters, sort and row limit,
 * visual tiles with fit reasons, display options, and a live preview under the dashboard's filters.
 * Saves `definition_v2`. Pending catalog items are listed as "Not available yet" with their reason.
 */

import CloseIcon from '@mui/icons-material/Close';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  IconButton,
  InputLabel,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useEffect, useMemo, useState } from 'react';

import type { DashboardWidget, WidgetVisual } from '../types';
import { VISUAL_ICON } from '../WidgetEditorDialog';
import { useV2Query } from './BuilderData';
import { breakdownLabel, isPickableGoverned, lowerFirst, measureOf, modelOf } from './catalog';
import { BUILDER_VISUALS, effectiveVisualV2, fitsAll, visualsForV2 } from './fit';
import { FilterValuePicker } from './FilterBar';
import { requestFor } from './requestFor';
import { NO_FILTERS, type DashboardRunContext } from './runContext';
import { MAX_RULES } from './table';
import { BAR_FILTER_KEYS, type CatalogV2, type ColourRule, type DefinitionV2, type V2FilterValue, type V2Measure, type WidgetDisplay } from './types';
import { NotFilteredLine, sparklineGrain } from './V2WidgetCard';
import { V2WidgetBody } from './V2WidgetBody';
import { dualSeries } from './advancedShape';

export type BuilderEditorValue = { title: string; visual: WidgetVisual; definition_v2: DefinitionV2 };

export type BuilderEditorInitial = { widgetId?: number; title?: string; visual?: WidgetVisual; definition?: DefinitionV2 | null; measure?: string };

const GRAIN_WORD: Record<string, string> = { week: 'week', month: 'month', quarter: 'quarter', year: 'year' };

/** "Sell-through units by customer and week". */
export function autoTitleV2(catalog: CatalogV2 | null | undefined, measures: string[], breakdowns: string[], grain: string | null): string {
  const labels = measures.map((m) => measureOf(catalog, m)?.label ?? m);
  const what = labels.length <= 2 ? labels.join(' and ') : `${labels[0]} and ${labels.length - 1} more`;
  if (!breakdowns.length) return what || 'Widget';
  const by = breakdowns.map((b) => (b === 'period' ? GRAIN_WORD[grain ?? ''] ?? 'period' : lowerFirst(breakdownLabel(catalog, b))));
  return `${what} by ${by.join(' and ')}`;
}

/** A v1 widget's fields as a v2 definition (legacy keys map to model measures; the rest are governed). */
export function definitionFromV1(catalog: CatalogV2 | null | undefined, w: Pick<DashboardWidget, 'metric_key' | 'grains' | 'period_grain' | 'filters'>): DefinitionV2 {
  const model = catalog?.measures.find((m) => m.kind !== 'governed' && m.legacy_key === w.metric_key);
  const id = model?.id ?? w.metric_key;
  const filters: Record<string, V2FilterValue[]> = {};
  const map: Record<string, string> = { customer_id: 'customer', product_id: 'product', distributor_id: 'distributor', bu: 'bu', site_label: 'site_label' };
  for (const [k, v] of Object.entries(w.filters ?? {})) {
    const key = map[k];
    if (key && (typeof v === 'string' || typeof v === 'number')) filters[key] = [v];
  }
  return {
    v: 1,
    query: {
      measures: [id],
      ...(w.grains.length ? { breakdowns: [...w.grains] } : {}),
      ...(w.period_grain && w.grains.includes('period') ? { period: { grain: w.period_grain } } : {}),
      ...(Object.keys(filters).length ? { filters } : {}),
    },
  };
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function groupOrder(catalog: CatalogV2 | null | undefined, group: string): number {
  const i = catalog?.groups.indexOf(group) ?? -1;
  return i === -1 ? 99 : i;
}

export function BuilderEditorDialog({
  open,
  catalog,
  initial,
  ctx = NO_FILTERS,
  dashboardModels = [],
  error,
  saving,
  onClose,
  onSave,
}: {
  open: boolean;
  catalog: CatalogV2;
  initial?: BuilderEditorInitial;
  ctx?: DashboardRunContext;
  dashboardModels?: string[];
  error?: string | null;
  saving?: boolean;
  onClose: () => void;
  onSave: (v: BuilderEditorValue) => void;
}) {
  const theme = useTheme();
  const phone = useMediaQuery(theme.breakpoints.down('sm'));
  const [measures, setMeasures] = useState<string[]>([]);
  const [breakdowns, setBreakdowns] = useState<string[]>([]);
  const [grain, setGrain] = useState<string | null>(null);
  const [own, setOwn] = useState<Record<string, V2FilterValue[]>>({});
  const [sort, setSort] = useState<{ by: string; dir: 'asc' | 'desc' } | null>(null);
  const [limit, setLimit] = useState<number>(catalog.limits?.default_limit ?? 500);
  const [visual, setVisual] = useState<WidgetVisual>('kpi');
  const [display, setDisplay] = useState<WidgetDisplay>({});
  const [title, setTitle] = useState('');
  const [search, setSearch] = useState('');
  const [withDash, setWithDash] = useState(true);

  useEffect(() => {
    if (!open) return;
    const d = initial?.definition;
    const ms = d?.query.measures ?? (initial?.measure ? [initial.measure] : []);
    setMeasures(ms);
    setBreakdowns(d?.query.breakdowns ?? []);
    setGrain(d?.query.period?.grain ?? null);
    const f: Record<string, V2FilterValue[]> = {};
    for (const [k, v] of Object.entries(d?.query.filters ?? {})) f[k] = Array.isArray(v) ? v : [v];
    setOwn(f);
    setSort(d?.query.sort ?? null);
    setLimit(d?.query.limit ?? catalog.limits?.default_limit ?? 500);
    setDisplay(d?.display ?? {});
    setTitle(initial?.title ?? '');
    setSearch('');
    const mm = ms.map((id) => measureOf(catalog, id)).filter(Boolean) as V2Measure[];
    setVisual(initial?.visual ? effectiveVisualV2(initial.visual, mm, d?.query.breakdowns ?? []) : visualsForV2(mm, d?.query.breakdowns ?? [])[0] ?? 'kpi');
  }, [open, initial, catalog]);

  const chosen = useMemo(() => measures.map((id) => measureOf(catalog, id)).filter(Boolean) as V2Measure[], [catalog, measures]);
  const first = chosen[0];
  const governed = first?.kind === 'governed';
  const model = modelOf(catalog, first?.model);
  const roleWall = catalog.walls.find((w) => w.id === 'W-CUSTOMER-ROLE')?.reason ?? 'Measures from different data are never combined.';

  // Breakdowns every chosen measure allows.
  const allowed = useMemo(() => {
    if (!chosen.length) return [] as string[];
    return chosen.reduce<string[]>((acc, m, i) => (i === 0 ? [...m.breakdowns] : acc.filter((b) => m.breakdowns.includes(b))), []);
  }, [chosen]);
  const grains = useMemo(() => {
    if (!chosen.length) return [] as string[];
    return chosen.reduce<string[]>((acc, m, i) => (i === 0 ? [...m.period_grains] : acc.filter((g) => m.period_grains.includes(g))), []);
  }, [chosen]);

  const pickMeasure = (m: V2Measure) => {
    if (measures.includes(m.id)) {
      setMeasures(measures.filter((id) => id !== m.id));
      return;
    }
    const curFirst = measureOf(catalog, measures[0] ?? '');
    if (m.kind === 'governed' || !curFirst || curFirst.kind === 'governed' || curFirst.model !== m.model) {
      // A new data family has different filter semantics. Do not retain invisible old filters.
      setOwn({});
      setMeasures([m.id]);
    } else setMeasures([...measures, m.id]);
  };

  // Keep breakdowns, grain and visual consistent with the measures.
  useEffect(() => {
    if (!open) return;
    if (governed) {
      const sets = first?.grain_sets ?? [];
      const key = [...breakdowns].sort().join('|');
      if (!sets.some((s) => [...s].sort().join('|') === key)) setBreakdowns(sets[0] ? [...sets[0]] : []);
    } else {
      const kept = breakdowns.filter((b) => allowed.includes(b)).slice(0, catalog.limits?.max_breakdowns ?? 3);
      if (kept.length !== breakdowns.length) setBreakdowns(kept);
    }
  }, [open, governed, first, allowed, breakdowns, catalog.limits?.max_breakdowns]);
  useEffect(() => {
    if (!breakdowns.includes('period')) {
      if (grain !== null && !governed) setGrain(null);
      return;
    }
    if (grains.length && (!grain || !grains.includes(grain))) setGrain(grains.includes('week') ? 'week' : grains[0]);
  }, [breakdowns, grains, grain, governed]);
  const fits = fitsAll(chosen, breakdowns);
  useEffect(() => {
    if (!chosen.length) return;
    if (!fits.find((f) => f.id === visual)?.fits) setVisual(visualsForV2(chosen, breakdowns)[0] ?? 'table');
  }, [fits, visual, chosen, breakdowns]);

  const toggleBreakdown = (b: string) => {
    setBreakdowns((cur) => (cur.includes(b) ? cur.filter((x) => x !== b) : cur.length >= (catalog.limits?.max_breakdowns ?? 3) ? cur : [...cur, b]));
  };

  const filterKeys = governed ? BAR_FILTER_KEYS.filter((k) => first?.honours?.filters.includes(k)) : BAR_FILTER_KEYS.filter((k) => model?.breakdowns.includes(k));

  const definition: DefinitionV2 = useMemo(() => {
    const filters: Record<string, V2FilterValue[] | V2FilterValue> = {};
    for (const [k, v] of Object.entries(own)) if (v.length) filters[k] = governed ? v[0] : v;
    const d: DefinitionV2 = { v: 1, query: { measures: [...measures] } };
    if (breakdowns.length) d.query.breakdowns = [...breakdowns];
    if (breakdowns.includes('period') && grain) d.query.period = { grain };
    if (Object.keys(filters).length) d.query.filters = filters;
    if (sort && (measures.includes(sort.by) || breakdowns.includes(sort.by))) d.query.sort = sort;
    if (limit && limit !== (catalog.limits?.default_limit ?? 500)) d.query.limit = limit;
    const disp: WidgetDisplay = {};
    if (visual === 'kpi' && display.kpi) disp.kpi = display.kpi;
    if (visual === 'combo' && display.series) disp.series = display.series;
    if (visual === 'dual_axis') disp.series = Object.fromEntries(dualSeries(chosen, display).map((s) => [s.key, { axis: s.axis, kind: s.kind }]));
    if (visual === 'table' && display.table?.rules?.length) disp.table = { rules: display.table.rules.filter((r) => measures.includes(r.measure)).slice(0, MAX_RULES) };
    if ((visual === 'hbar' || visual === 'bar') && display.top_n) disp.top_n = display.top_n;
    if (display.caption) disp.caption = display.caption;
    if (Object.keys(disp).length) d.display = disp;
    return d;
  }, [measures, chosen, breakdowns, grain, own, sort, limit, visual, display, governed, catalog.limits?.default_limit]);

  const previewCtx = withDash ? ctx : NO_FILTERS;
  const debounced = useDebounced(definition, 300);
  const plan = useMemo(
    () => requestFor(debounced, { catalog, filters: previewCtx.filters, window: previewCtx.window, required: previewCtx.required, names: previewCtx.names }),
    [debounced, catalog, previewCtx],
  );
  const preview = useV2Query(open && measures.length && plan.status === 'ready' ? plan.request : null, { tag: 'editor-preview' });
  const refusals = preview.data && !preview.data.ok ? preview.data.refusals : [];
  const measureRefusals = refusals.filter((r) => r.measure && measures.includes(r.measure));
  const filterRefusals = refusals.filter((r) => /^Filter '/.test(r.reason));
  const autoTitle = autoTitleV2(catalog, measures, breakdowns, grain);

  const q = search.trim().toLowerCase();
  const matches = (m: V2Measure) => !q || m.label.toLowerCase().includes(q) || m.id.toLowerCase().includes(q);
  const governedList = catalog.measures.filter((m) => isPickableGoverned(m) && !m.hidden && matches(m));
  const pending = catalog.pending.filter((p) => !q || p.id.toLowerCase().includes(q) || p.reason.toLowerCase().includes(q));
  const otherModelPicked = (m: V2Measure) => Boolean(first && !governed && m.kind !== 'governed' && first.model !== m.model);

  const visibleBreakdowns = useMemo(() => {
    if (governed || !model) return [];
    const refusals = model.filter_refusals ?? {};
    return catalog.breakdowns
      .filter((b) => model.breakdowns.includes(b.id) || (refusals[b.id] && !/is not a breakdown of/.test(refusals[b.id])))
      .sort((a, b) => groupOrder(catalog, a.group) - groupOrder(catalog, b.group));
  }, [governed, model, catalog]);

  const rules = display.table?.rules ?? [];
  const setRules = (next: ColourRule[]) => setDisplay((d) => ({ ...d, table: { rules: next } }));
  const spark = sparklineGrain(first, plan);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xl" fullScreen={phone} data-testid="builder-editor" PaperProps={{ sx: { height: { md: '90vh' } } }}>
      <DialogTitle sx={{ pb: 1, display: 'flex', alignItems: 'center' }}>
        <Box sx={{ flex: 1 }}>{initial?.widgetId ? 'Edit widget' : 'Add widget'}</Box>
        <IconButton aria-label="Close editor" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={{ p: 0, display: 'flex', flexDirection: { xs: 'column', md: 'row' }, minHeight: 0 }}>
        {/* Measures, grouped by model. */}
        <Box sx={{ width: { md: 300 }, flexShrink: 0, borderRight: { md: 1 }, borderColor: { md: 'divider' }, display: 'flex', flexDirection: 'column', minHeight: 0, maxHeight: { xs: 360, md: 'none' } }}>
          <Box sx={{ p: 1.5, pb: 1 }}>
            <TextField
              size="small"
              fullWidth
              label="Find a measure"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              inputProps={{ 'data-testid': 'builder-editor-search' }}
            />
          </Box>
          <List dense sx={{ overflowY: 'auto', flex: 1, pt: 0 }} data-testid="builder-editor-measures">
            {catalog.models.map((mdl) => {
              const ms = catalog.measures.filter((m) => m.model === mdl.id && m.kind !== 'governed' && matches(m));
              if (!ms.length) return null;
              const blocked = Boolean(first && (governed || first.model !== mdl.id));
              return (
                <li key={mdl.id}>
                  <ul style={{ padding: 0 }}>
                    <ListSubheader sx={{ lineHeight: 1.6, pt: 1 }}>{mdl.label}</ListSubheader>
                    {blocked && !governed ? (
                      <Typography variant="caption" color="text.secondary" sx={{ px: 2, display: 'block' }} data-testid={`builder-editor-model-note-${mdl.id}`}>
                        Not combinable with your measures: {roleWall}
                      </Typography>
                    ) : null}
                    {ms.map((m) => {
                      const on = measures.includes(m.id);
                      const disabled = otherModelPicked(m);
                      return (
                        <ListItemButton
                          key={m.id}
                          dense
                          selected={on}
                          disabled={disabled}
                          onClick={() => pickMeasure(m)}
                          title={disabled ? roleWall : undefined}
                          data-testid={`builder-editor-measure-${m.id}`}
                          aria-pressed={on}
                        >
                          <ListItemIcon sx={{ minWidth: 32 }}>
                            <Checkbox edge="start" size="small" checked={on} tabIndex={-1} disableRipple inputProps={{ 'aria-hidden': true }} />
                          </ListItemIcon>
                          <ListItemText
                            primary={m.label}
                            secondary={[m.unit ? `Unit: ${m.unit.replace(/_/g, ' ')}` : null, m.requires.length ? `Needs ${m.requires.join(', ')}` : null].filter(Boolean).join(' · ')}
                          />
                        </ListItemButton>
                      );
                    })}
                  </ul>
                </li>
              );
            })}
            {governedList.length ? (
              <li>
                <ul style={{ padding: 0 }}>
                  <ListSubheader sx={{ lineHeight: 1.6, pt: 1 }}>Other governed metrics</ListSubheader>
                  <Typography variant="caption" color="text.secondary" sx={{ px: 2, display: 'block' }}>
                    Picked on their own, at their own grains.
                  </Typography>
                  {governedList.map((m) => (
                    <ListItemButton key={m.id} dense selected={measures.includes(m.id)} onClick={() => pickMeasure(m)} data-testid={`builder-editor-measure-${m.id}`} aria-pressed={measures.includes(m.id)}>
                      <ListItemIcon sx={{ minWidth: 32 }}>
                        <Checkbox edge="start" size="small" checked={measures.includes(m.id)} tabIndex={-1} disableRipple inputProps={{ 'aria-hidden': true }} />
                      </ListItemIcon>
                      <ListItemText primary={m.label} />
                    </ListItemButton>
                  ))}
                </ul>
              </li>
            ) : null}
            {pending.length ? (
              <li>
                <ul style={{ padding: 0 }} data-testid="builder-editor-pending">
                  <ListSubheader sx={{ lineHeight: 1.6, pt: 1 }}>Not available yet</ListSubheader>
                  {pending.map((p) => (
                    <Box component="li" key={p.id} sx={{ px: 2, py: 0.75, color: 'text.disabled', listStyle: 'none' }} data-testid={`builder-editor-pending-${p.id}`}>
                      <Typography variant="body2" color="text.secondary">
                        {p.id.replace(/^[a-z_]+\./, '').replace(/_/g, ' ')}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {p.reason}
                      </Typography>
                    </Box>
                  ))}
                </ul>
              </li>
            ) : null}
          </List>
          {measureRefusals.length ? (
            <Alert severity="warning" sx={{ m: 1 }} data-testid="builder-editor-refusal-measures">
              {measureRefusals.map((r) => `${measureOf(catalog, r.measure ?? '')?.label ?? r.measure}: ${r.reason}`).join(' ')}
            </Alert>
          ) : null}
        </Box>

        {/* Preview and query controls. */}
        <Stack spacing={2} sx={{ flex: 1, minWidth: 0, p: 2, overflowY: 'auto' }}>
          <Paper variant="outlined" sx={{ p: 1.5 }} data-testid="builder-editor-preview">
            <Stack direction="row" alignItems="center" spacing={1}>
              <Typography variant="subtitle2" fontWeight={700} noWrap sx={{ flex: 1, minWidth: 0 }}>
                {title.trim() || autoTitle}
              </Typography>
              <FormControlLabel
                control={<Switch size="small" checked={withDash} onChange={(e) => setWithDash(e.target.checked)} />}
                label={<Typography variant="caption">Preview with dashboard filters</Typography>}
                data-testid="builder-editor-with-dashboard"
              />
            </Stack>
            <NotFilteredLine items={plan.notFiltered} testId="builder-editor-not-filtered" />
            <Box sx={{ height: 300, mt: 1 }}>
              {!measures.length ? (
                <Typography variant="body2" color="text.secondary">
                  Pick a measure on the left.
                </Typography>
              ) : plan.status === 'blocked' ? (
                <Alert severity="info" variant="outlined">
                  {plan.message}
                </Alert>
              ) : (
                <V2WidgetBody
                  def={debounced}
                  visual={visual}
                  catalog={catalog}
                  result={preview.data}
                  loading={preview.isLoading}
                  error={preview.isError ? preview.error : null}
                  onRetry={() => void preview.refetch()}
                  caption={plan.caption}
                  testKey="preview"
                  chartHeight={280}
                />
              )}
            </Box>
          </Paper>

          <Box>
            <Typography variant="overline" color="text.secondary" display="block">
              Break down by {governed ? '' : `(up to ${catalog.limits?.max_breakdowns ?? 3}, in order)`}
            </Typography>
            {governed ? (
              <Stack direction="row" flexWrap="wrap" gap={1}>
                {(first?.grain_sets ?? []).map((set) => {
                  const key = [...set].sort().join('|');
                  const on = [...breakdowns].sort().join('|') === key;
                  return (
                    <Chip
                      key={key || 'none'}
                      label={set.length ? set.map((b) => breakdownLabel(catalog, b)).join(' × ') : 'Total only'}
                      color={on ? 'primary' : 'default'}
                      variant={on ? 'filled' : 'outlined'}
                      onClick={() => setBreakdowns([...set])}
                      data-testid={`builder-editor-grainset-${key || 'none'}`}
                    />
                  );
                })}
              </Stack>
            ) : (
              <Stack spacing={1}>
                {[...new Set(visibleBreakdowns.map((b) => b.group))].map((g) => (
                  <Stack key={g} direction="row" flexWrap="wrap" gap={1} alignItems="center">
                    <Typography variant="caption" color="text.secondary" sx={{ width: 80 }}>
                      {g}
                    </Typography>
                    {visibleBreakdowns
                      .filter((b) => b.group === g)
                      .map((b) => {
                        const idx = breakdowns.indexOf(b.id);
                        const inModel = model?.breakdowns.includes(b.id);
                        const forMeasures = allowed.includes(b.id);
                        const full = idx === -1 && breakdowns.length >= (catalog.limits?.max_breakdowns ?? 3);
                        const reason = !inModel
                          ? model?.filter_refusals?.[b.id]
                          : !forMeasures
                            ? `Not available for ${chosen.find((m) => !m.breakdowns.includes(b.id))?.label ?? 'one of your measures'}.`
                            : full
                              ? 'Up to 3 breakdowns.'
                              : undefined;
                        return (
                          <Box key={b.id} component="span" title={reason}>
                            <Chip
                              label={idx >= 0 ? `${idx + 1}. ${b.label}` : b.label}
                              color={idx >= 0 ? 'primary' : 'default'}
                              variant={idx >= 0 ? 'filled' : 'outlined'}
                              disabled={Boolean(reason)}
                              onClick={() => toggleBreakdown(b.id)}
                              aria-pressed={idx >= 0}
                              aria-description={reason}
                              data-testid={`builder-editor-breakdown-${b.id}`}
                            />
                          </Box>
                        );
                      })}
                  </Stack>
                ))}
                {visibleBreakdowns.some((b) => !model?.breakdowns.includes(b.id)) ? (
                  <Typography variant="caption" color="text.secondary" data-testid="builder-editor-blocked-breakdowns">
                    Greyed out:{' '}
                    {visibleBreakdowns
                      .filter((b) => !model?.breakdowns.includes(b.id))
                      .map((b) => `${b.label} (${model?.filter_refusals?.[b.id]})`)
                      .join(' ')}
                  </Typography>
                ) : null}
              </Stack>
            )}
          </Box>

          {breakdowns.includes('period') && grains.length ? (
            <Box>
              <Typography variant="overline" color="text.secondary" display="block">
                Group periods by
              </Typography>
              <ToggleButtonGroup exclusive size="small" value={grain} onChange={(_e, v: string | null) => v && setGrain(v)}>
                {grains.map((g) => (
                  <ToggleButton key={g} value={g} data-testid={`builder-editor-grain-${g}`}>
                    {g.charAt(0).toUpperCase() + g.slice(1)}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
            </Box>
          ) : null}

          {first ? (
            <Box data-testid="builder-editor-filters">
              <Typography variant="overline" color="text.secondary" display="block">
                Filters (this widget only; combined with the dashboard&apos;s)
              </Typography>
              {filterKeys.length ? (
                <Stack direction="row" flexWrap="wrap" useFlexGap spacing={1.5}>
                  {filterKeys.map((k) => (
                    <FilterValuePicker
                      key={k}
                      catalog={catalog}
                      filterKey={k}
                      value={own[k] ?? []}
                      onChange={(next) => setOwn((o) => ({ ...o, [k]: governed ? next.slice(-1) : next }))}
                      models={first.model ? [first.model] : dashboardModels}
                      window={ctx.window}
                      testPrefix="builder-editor-filter"
                    />
                  ))}
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  This metric takes no filters.
                </Typography>
              )}
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }} data-testid="builder-editor-filter-summary">
                {Object.entries(own).filter(([, v]) => v.length).length
                  ? `Filters: ${Object.entries(own)
                      .filter(([, v]) => v.length)
                      .map(([k, v]) => `${breakdownLabel(catalog, k)} = ${v.map((x) => ctx.names?.[k]?.[String(x)] ?? (typeof x === 'string' ? x : `${v.length} selected`)).filter((x, i, a) => a.indexOf(x) === i).join(', ')}`)
                      .join('; ')}`
                  : 'Filters: none of its own.'}
              </Typography>
              {filterRefusals.length ? (
                <Alert severity="warning" sx={{ mt: 1 }} data-testid="builder-editor-refusal-filters">
                  {filterRefusals.map((r) => r.reason).join(' ')}
                </Alert>
              ) : null}
            </Box>
          ) : null}

          {first ? (
            <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap alignItems="center">
              <FormControl size="small" sx={{ minWidth: 220 }}>
                <InputLabel id="builder-sort-label">Sort rows by</InputLabel>
                <Select
                  labelId="builder-sort-label"
                  label="Sort rows by"
                  value={sort ? `${sort.by}|${sort.dir}` : ''}
                  onChange={(e) => {
                    const v = String(e.target.value);
                    if (!v) setSort(null);
                    else {
                      const [by, dir] = v.split('|');
                      setSort({ by, dir: dir as 'asc' | 'desc' });
                    }
                  }}
                  inputProps={{ 'data-testid': 'builder-editor-sort' }}
                >
                  <MenuItem value="">Default order</MenuItem>
                  {[...measures, ...breakdowns].flatMap((id) => {
                    const label = measureOf(catalog, id)?.label ?? breakdownLabel(catalog, id);
                    return [
                      <MenuItem key={`${id}|desc`} value={`${id}|desc`}>
                        {label}, highest first
                      </MenuItem>,
                      <MenuItem key={`${id}|asc`} value={`${id}|asc`}>
                        {label}, lowest first
                      </MenuItem>,
                    ];
                  })}
                </Select>
              </FormControl>
              <TextField
                size="small"
                type="number"
                label="Row limit"
                value={limit}
                onChange={(e) => setLimit(Math.max(1, Math.min(catalog.limits?.max_limit ?? 5000, Number(e.target.value) || 1)))}
                inputProps={{ min: 1, max: catalog.limits?.max_limit ?? 5000, 'data-testid': 'builder-editor-limit' }}
                helperText={`Up to ${(catalog.limits?.max_limit ?? 5000).toLocaleString('en-US')}`}
                sx={{ width: 150 }}
              />
            </Stack>
          ) : null}
        </Stack>

        {/* Visual, display options, title. */}
        <Stack spacing={2} sx={{ width: { md: 300 }, flexShrink: 0, p: 2, borderLeft: { md: 1 }, borderColor: { md: 'divider' }, overflowY: 'auto' }}>
          <Box>
            <Typography variant="overline" color="text.secondary">
              Chart
            </Typography>
            <ToggleButtonGroup
              exclusive
              value={visual}
              onChange={(_e, v: WidgetVisual | null) => v && setVisual(v)}
              sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0.75, '& .MuiToggleButtonGroup-grouped': { border: 1, borderColor: 'divider', borderRadius: '8px !important', m: 0 } }}
            >
              {BUILDER_VISUALS.map((v) => {
                const f = fits.find((x) => x.id === v.id);
                const ok = Boolean(f?.fits) && chosen.length > 0;
                return (
                  <ToggleButton
                    key={v.id}
                    value={v.id}
                    disabled={!ok}
                    title={ok ? v.hint : f?.reason}
                    aria-label={ok ? v.label : `${v.label}: ${f?.reason ?? 'pick a measure first'}`}
                    data-testid={`builder-editor-visual-${v.id}`}
                    sx={{ flexDirection: 'column', gap: 0.25, py: 1, textTransform: 'none', fontSize: 12, lineHeight: 1.2 }}
                  >
                    {VISUAL_ICON[v.id]}
                    {v.label}
                  </ToggleButton>
                );
              })}
            </ToggleButtonGroup>
            {chosen.length ? (
              <Box component="ul" sx={{ m: 0, mt: 1, pl: 2 }} data-testid="builder-editor-fit-reasons">
                {fits
                  .filter((f) => !f.fits)
                  .map((f) => (
                    <Typography component="li" variant="caption" color="text.secondary" key={f.id}>
                      {BUILDER_VISUALS.find((v) => v.id === f.id)?.label}: {f.reason}
                    </Typography>
                  ))}
              </Box>
            ) : null}
          </Box>

          {visual === 'kpi' && first ? (
            <Box data-testid="builder-editor-kpi-options">
              <Typography variant="overline" color="text.secondary" display="block">
                Number options
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={Boolean(display.kpi?.compare)}
                    onChange={(e) => setDisplay((d) => ({ ...d, kpi: { ...d.kpi, compare: e.target.checked } }))}
                    inputProps={{ 'aria-label': 'Compare with the dashboard comparison' }}
                  />
                }
                label="Compare (uses the dashboard's Compare setting)"
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={Boolean(display.kpi?.sparkline) && spark !== false}
                    disabled={spark === false}
                    onChange={(e) => setDisplay((d) => ({ ...d, kpi: { ...d.kpi, sparkline: e.target.checked } }))}
                    inputProps={{ 'aria-label': 'Show a trend line' }}
                  />
                }
                label={spark === false ? 'Trend line: not for this measure (stock is a latest count, or no period)' : 'Trend line'}
              />
            </Box>
          ) : null}

          {visual === 'dual_axis' && chosen.length === 2 ? (
            <FormControl size="small" fullWidth>
              <InputLabel id="builder-right-axis-label">Right axis</InputLabel>
              <Select labelId="builder-right-axis-label" label="Right axis" value={dualSeries(chosen, display).find((s) => s.axis === 'right')?.key ?? measures[1]}
                onChange={(e) => setDisplay((d) => ({ ...d, series: Object.fromEntries(chosen.map((m, i) => [m.id, { axis: m.id === e.target.value ? 'right' : 'left', kind: d.series?.[m.id]?.kind ?? (i === 0 ? 'bar' : 'line') }])) }))}>
                {chosen.map((m) => <MenuItem key={m.id} value={m.id}>{m.label}</MenuItem>)}
              </Select>
            </FormControl>
          ) : null}
          {visual === 'scatter' && chosen.length === 2 ? <Box>
            <Typography variant="caption">Across: {chosen[0].label}; up: {chosen[1].label}.</Typography>
            <Button size="small" onClick={() => setMeasures(([a, b]) => [b, a])}>Swap axes</Button>
          </Box> : null}
          {visual === 'pivot' && breakdowns.length === 2 ? <Box>
            <Typography variant="caption">Rows: {breakdownLabel(catalog, breakdowns[0])}; columns: {breakdownLabel(catalog, breakdowns[1])}.</Typography>
            <Button size="small" onClick={() => setBreakdowns(([a, b]) => [b, a])}>Swap rows and columns</Button>
          </Box> : null}
          {(visual === 'combo' || visual === 'dual_axis') && chosen.length === 2 ? (
            <FormControl size="small" fullWidth data-testid="builder-editor-combo-options">
              <InputLabel id="builder-combo-label">Bars</InputLabel>
              <Select
                labelId="builder-combo-label"
                label="Bars"
                value={Object.entries(display.series ?? {}).find(([, s]) => s.kind === 'bar')?.[0] ?? measures[0]}
                onChange={(e) => {
                  const bars = String(e.target.value);
                  const line = measures.find((m) => m !== bars) ?? '';
                  setDisplay((d) => ({ ...d, series: { [bars]: { ...d.series?.[bars], kind: 'bar' }, [line]: { ...d.series?.[line], kind: 'line' } } }));
                }}
              >
                {chosen.map((m) => (
                  <MenuItem key={m.id} value={m.id}>
                    {m.label} as bars (the other as a line)
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          ) : null}

          {(visual === 'hbar' || visual === 'bar') && first ? (
            <FormControl size="small" fullWidth>
              <InputLabel id="builder-topn-label">Start with top</InputLabel>
              <Select
                labelId="builder-topn-label"
                label="Start with top"
                value={display.top_n ?? 15}
                onChange={(e) => setDisplay((d) => ({ ...d, top_n: Number(e.target.value) }))}
              >
                {[5, 10, 15, 25, 50].map((n) => (
                  <MenuItem key={n} value={n}>
                    {n}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          ) : null}

          {visual === 'table' && first ? (
            <Box data-testid="builder-editor-rules">
              <Typography variant="overline" color="text.secondary" display="block">
                Colour rules (up to {MAX_RULES})
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                No thresholds are set for you. Each rule adds a tint, a dot and a word, so colour is never the only signal.
              </Typography>
              <Stack spacing={1}>
                {rules.map((r, i) => (
                  <Stack key={i} direction="row" spacing={0.5} flexWrap="wrap" useFlexGap alignItems="center" data-testid={`builder-editor-rule-${i}`}>
                    <Select size="small" value={r.measure} onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, measure: String(e.target.value) } : x)))} sx={{ minWidth: 120, maxWidth: 160 }} inputProps={{ 'aria-label': 'Measure' }}>
                      {chosen.map((m) => (
                        <MenuItem key={m.id} value={m.id}>
                          {m.label}
                        </MenuItem>
                      ))}
                    </Select>
                    <Select size="small" value={r.op} onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, op: e.target.value as ColourRule['op'] } : x)))} inputProps={{ 'aria-label': 'Condition' }}>
                      {(['<', '<=', '>', '>=', 'between'] as const).map((op) => (
                        <MenuItem key={op} value={op}>
                          {op}
                        </MenuItem>
                      ))}
                    </Select>
                    <TextField size="small" type="number" value={r.value} onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, value: Number(e.target.value) } : x)))} sx={{ width: 80 }} inputProps={{ 'aria-label': 'Value' }} />
                    {r.op === 'between' ? (
                      <TextField size="small" type="number" value={r.value2 ?? r.value} onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, value2: Number(e.target.value) } : x)))} sx={{ width: 80 }} inputProps={{ 'aria-label': 'Upper value' }} />
                    ) : null}
                    <Select size="small" value={r.tone} onChange={(e) => setRules(rules.map((x, j) => (j === i ? { ...x, tone: e.target.value as ColourRule['tone'] } : x)))} inputProps={{ 'aria-label': 'Tone' }}>
                      <MenuItem value="good">Good</MenuItem>
                      <MenuItem value="warn">Warning</MenuItem>
                      <MenuItem value="bad">Problem</MenuItem>
                    </Select>
                    <IconButton size="small" aria-label={`Remove rule ${i + 1}`} onClick={() => setRules(rules.filter((_x, j) => j !== i))}>
                      <CloseIcon fontSize="small" />
                    </IconButton>
                  </Stack>
                ))}
                <Button
                  size="small"
                  variant="outlined"
                  disabled={rules.length >= MAX_RULES}
                  onClick={() => setRules([...rules, { measure: measures[0], op: '<', value: 0, tone: 'warn' }])}
                  data-testid="builder-editor-add-rule"
                >
                  Add rule
                </Button>
              </Stack>
            </Box>
          ) : null}

          <TextField
            label="Title"
            value={title}
            placeholder={autoTitle}
            onChange={(e) => setTitle(e.target.value)}
            fullWidth
            size="small"
            InputLabelProps={{ shrink: true }}
            helperText="Leave blank to use the suggested title."
            inputProps={{ 'data-testid': 'builder-editor-title' }}
          />
          {error ? <Alert severity="error">{error}</Alert> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          disabled={!measures.length || saving}
          onClick={() => onSave({ title: title.trim() || autoTitle, visual, definition_v2: definition })}
          data-testid="builder-editor-save"
        >
          {initial?.widgetId ? 'Save' : 'Add to dashboard'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
