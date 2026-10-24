'use client';

/**
 * Dashboard filter bar (spec s.3, S6): date range + compare, customer, distributor, product,
 * business unit, channel, region. Names only. Values come from v2 execute. Click chips (session
 * only) sit in their own row with "×" and Clear. At phone width the controls fold into a
 * "Filters (n)" bottom drawer and the chips stay visible in one scrolling row.
 */

import TouchAppOutlinedIcon from '@mui/icons-material/TouchAppOutlined';
import {
  Autocomplete,
  Box,
  Button,
  Chip,
  Collapse,
  Drawer,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useEffect, useState } from 'react';

import { breakdownLabel } from './catalog';
import type { ClickState } from './clickFilters';
import { COMPARE_MODES, DATE_PRESETS, resolvePreset, windowLabel } from './dates';
import { useFilterOptions, type FilterOption } from './filterOptions';
import { BAR_FILTER_KEYS, type CatalogV2, type CompareMode, type DashboardFilters, type DatePreset, type DateWindow, type V2FilterValue } from './types';

export const DEFAULT_FILTERS: DashboardFilters = { date: { preset: 'all_time', from: null, to: null }, compare: 'none' };

/** The saved `filters_json` (possibly `{}` or absent) as a full bar state. */
export function normaliseFilters(raw: unknown): DashboardFilters {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Partial<DashboardFilters>;
  const date = r.date && typeof r.date === 'object' ? r.date : DEFAULT_FILTERS.date;
  return {
    ...r,
    date: { preset: (date.preset as DatePreset) ?? 'all_time', from: date.from ?? null, to: date.to ?? null },
    compare: (r.compare as CompareMode) ?? 'none',
  };
}

export function barValues(f: DashboardFilters, key: string): V2FilterValue[] {
  const v = f[key];
  return Array.isArray(v) ? (v.filter((x) => typeof x === 'string' || typeof x === 'number') as V2FilterValue[]) : [];
}

/** How many bar settings are active (the "Filters (n)" count). */
export function activeCount(f: DashboardFilters): number {
  let n = 0;
  if (f.date.preset !== 'all_time') n += 1;
  if (f.compare !== 'none') n += 1;
  for (const [k, v] of Object.entries(f)) {
    if (k === 'date' || k === 'compare' || k === 'required') continue;
    if (Array.isArray(v) && v.length) n += 1;
  }
  return n;
}

/** Additional attributes are catalog-driven; pending or unsupported model fields are never invented. */
export function extraFilterKeys(catalog: CatalogV2 | null | undefined): string[] {
  return (catalog?.breakdowns ?? []).filter((b) => b.kind === 'attribute'
    && !BAR_FILTER_KEYS.some((key) => key === b.id)
    && catalog?.models.some((m) => m.breakdowns.includes(b.id))).map((b) => b.id);
}

export function FilterValuePicker({
  catalog,
  filterKey,
  value,
  onChange,
  models,
  window,
  required,
  onNames,
  size = 'small',
  testPrefix = 'dashboard-filter',
}: {
  catalog: CatalogV2 | null | undefined;
  filterKey: string;
  value: V2FilterValue[];
  onChange: (next: V2FilterValue[]) => void;
  models: string[];
  window: DateWindow;
  required?: boolean;
  /** Report value -> name pairs (for messages that name what a filter holds). */
  onNames?: (key: string, names: Record<string, string>) => void;
  size?: 'small' | 'medium';
  testPrefix?: string;
}) {
  const [open, setOpen] = useState(false);
  const { options, loading, truncated } = useFilterOptions(catalog, filterKey, models, window, open || value.length > 0);
  const label = breakdownLabel(catalog, filterKey);
  const selected: FilterOption[] = value.map((v) => options.find((o) => String(o.value) === String(v)) ?? { value: v, label: loading ? 'Loading…' : 'Not in this date range', tags: [] });
  useEffect(() => {
    if (!onNames || !options.length) return;
    onNames(filterKey, Object.fromEntries(options.map((o) => [String(o.value), o.label])));
  }, [onNames, filterKey, options]);
  return (
    <Autocomplete<FilterOption, true, false, false>
      multiple
      size={size}
      open={open}
      onOpen={() => setOpen(true)}
      onClose={() => setOpen(false)}
      options={options}
      loading={loading}
      value={selected}
      isOptionEqualToValue={(o, v) => String(o.value) === String(v.value)}
      getOptionLabel={(o) => o.label}
      filterSelectedOptions
      onChange={(_e, next) => onChange(next.map((o) => o.value))}
      renderOption={(props, o) => {
        const { key, ...rest } = props as typeof props & { key: string };
        return (
          <li key={key} {...rest}>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2">{o.label}</Typography>
              {o.tags.length ? (
                <Typography variant="caption" color="text.secondary">
                  {o.tags.join(' · ')}
                </Typography>
              ) : null}
            </Box>
          </li>
        );
      }}
      noOptionsText={loading ? 'Loading…' : 'No values with data in this date range'}
      sx={{ minWidth: 190, flex: '1 1 190px', maxWidth: { sm: 320 } }}
      renderInput={(params) => (
        <TextField
          {...params}
          label={required ? `${label} (required)` : label}
          error={Boolean(required && !value.length)}
          helperText={truncated && open ? `First ${(5000).toLocaleString('en-US')} values; type to search` : undefined}
          inputProps={{ ...params.inputProps, 'data-testid': `${testPrefix}-${filterKey}` }}
        />
      )}
    />
  );
}

export type FilterBarProps = {
  catalog: CatalogV2 | null | undefined;
  value: DashboardFilters;
  onChange: (next: DashboardFilters) => void;
  /** Models the dashboard's widgets use (filter values come from them). */
  models: string[];
  clicks: ClickState;
  onRemoveChip: (key: string, value: V2FilterValue) => void;
  onClearPeriod: () => void;
  onClearChips: () => void;
  onSave?: () => void;
  saving?: boolean;
  dirty?: boolean;
  onNames?: (key: string, names: Record<string, string>) => void;
  /** Hide controls the server cannot honour (old API: no saved filters). */
  canSave?: boolean;
  now?: Date;
};

function Controls(props: FilterBarProps & { stacked?: boolean }) {
  const { catalog, value, onChange, models } = props;
  const [more, setMore] = useState(false);
  const extra = extraFilterKeys(catalog);
  const selectedExtra = extra.some((key) => barValues(value, key).length > 0);
  const window = resolvePreset(value.date, props.now);
  const required = value.required ?? [];
  const set = (patch: Partial<DashboardFilters>) => onChange({ ...value, ...patch });
  return (
    <Stack direction={props.stacked ? 'column' : 'row'} flexWrap="wrap" useFlexGap spacing={1.5} alignItems={props.stacked ? 'stretch' : 'flex-start'}>
      <FormControl size="small" sx={{ minWidth: 160 }}>
        <InputLabel id="dash-date-label">Date range</InputLabel>
        <Select
          labelId="dash-date-label"
          label="Date range"
          value={value.date.preset}
          onChange={(e) => set({ date: { ...value.date, preset: e.target.value as DatePreset } })}
          inputProps={{ 'data-testid': 'dashboard-filter-date' }}
        >
          {DATE_PRESETS.map((p) => (
            <MenuItem key={p.id} value={p.id}>
              {p.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {value.date.preset === 'custom' ? (
        <>
          <TextField
            size="small"
            type="date"
            label="From"
            value={value.date.from ?? ''}
            onChange={(e) => set({ date: { ...value.date, from: e.target.value || null } })}
            InputLabelProps={{ shrink: true }}
            inputProps={{ 'data-testid': 'dashboard-filter-from' }}
          />
          <TextField
            size="small"
            type="date"
            label="To"
            value={value.date.to ?? ''}
            onChange={(e) => set({ date: { ...value.date, to: e.target.value || null } })}
            InputLabelProps={{ shrink: true }}
            inputProps={{ 'data-testid': 'dashboard-filter-to' }}
          />
        </>
      ) : null}
      <FormControl size="small" sx={{ minWidth: 160 }}>
        <InputLabel id="dash-compare-label">Compare</InputLabel>
        <Select
          labelId="dash-compare-label"
          label="Compare"
          value={value.compare}
          onChange={(e) => set({ compare: e.target.value as CompareMode })}
          inputProps={{ 'data-testid': 'dashboard-filter-compare' }}
        >
          {COMPARE_MODES.map((m) => (
            <MenuItem key={m.id} value={m.id}>
              {m.label}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {BAR_FILTER_KEYS.map((key) => (
        <FilterValuePicker
          key={key}
          catalog={catalog}
          filterKey={key}
          value={barValues(value, key)}
          onChange={(next) => set({ [key]: next })}
          models={models}
          window={window}
          required={required.includes(key)}
          onNames={props.onNames}
        />
      ))}
      {extra.length ? <Box sx={{ flexBasis: '100%', minWidth: 0 }}>
        <Button size="small" onClick={() => setMore((v) => !v)} aria-expanded={more || selectedExtra} data-testid="dashboard-more-filters">
          More filters
        </Button>
        <Collapse in={more || selectedExtra}>
          <Stack direction={props.stacked ? 'column' : 'row'} flexWrap="wrap" useFlexGap spacing={1.5} sx={{ pt: 1 }}>
            {extra.map((key) => <FilterValuePicker key={key} catalog={catalog} filterKey={key} value={barValues(value, key)}
              onChange={(next) => set({ [key]: next })} models={models} window={window} onNames={props.onNames} />)}
          </Stack>
        </Collapse>
      </Box> : null}
      <Stack direction="row" spacing={1} alignItems="center" sx={{ minHeight: 40 }}>
        {props.canSave !== false && props.onSave ? (
          <Button size="small" variant="outlined" disabled={!props.dirty || props.saving} onClick={props.onSave} data-testid="dashboard-filter-save">
            {props.saving ? 'Saving…' : 'Save filters'}
          </Button>
        ) : null}
        <Typography variant="caption" color="text.secondary" data-testid="dashboard-filter-window">
          {windowLabel(window)}
        </Typography>
      </Stack>
    </Stack>
  );
}

function ChipRow({ clicks, onRemoveChip, onClearPeriod, onClearChips, catalog }: FilterBarProps) {
  if (!clicks.chips.length && !clicks.period) return null;
  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="center"
      sx={{ mt: 1, overflowX: 'auto', flexWrap: { xs: 'nowrap', sm: 'wrap' }, rowGap: 1, pb: 0.5 }}
      data-testid="dashboard-click-chips"
      aria-label="Filters from charts"
      role="group"
    >
      <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
        From charts:
      </Typography>
      {clicks.period ? (
        <Chip
          size="small"
          variant="outlined"
          color="primary"
          icon={<TouchAppOutlinedIcon />}
          label={`Period ${clicks.period.label}`}
          onDelete={onClearPeriod}
          data-testid="dashboard-click-chip-period"
          sx={{ flexShrink: 0 }}
        />
      ) : null}
      {clicks.chips.map((c) => (
        <Chip
          key={`${c.key}:${c.value}`}
          size="small"
          variant="outlined"
          color="primary"
          icon={<TouchAppOutlinedIcon />}
          label={`${breakdownLabel(catalog, c.key)}: ${c.label}`}
          onDelete={() => onRemoveChip(c.key, c.value)}
          data-testid={`dashboard-click-chip-${c.key}`}
          sx={{ flexShrink: 0 }}
        />
      ))}
      <Button size="small" onClick={onClearChips} sx={{ flexShrink: 0 }} data-testid="dashboard-click-chips-clear">
        Clear
      </Button>
      <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0, display: { xs: 'none', md: 'inline' } }}>
        Esc clears
      </Typography>
    </Stack>
  );
}

export function DashboardFilterBar(props: FilterBarProps & { forcePhone?: boolean }) {
  const theme = useTheme();
  const phoneQuery = useMediaQuery(theme.breakpoints.down('sm'));
  const phone = props.forcePhone ?? phoneQuery;
  const [drawer, setDrawer] = useState(false);
  const n = activeCount(props.value);
  return (
    <Paper
      variant="outlined"
      sx={{ p: 1.5, position: 'sticky', top: 0, zIndex: 3, bgcolor: 'background.paper' }}
      data-testid="dashboard-filter-bar"
      component="section"
      aria-label="Dashboard filters"
    >
      {phone ? (
        <>
          <Stack direction="row" spacing={1} alignItems="center">
            <Button variant="outlined" size="small" onClick={() => setDrawer(true)} data-testid="dashboard-filters-open">
              Filters ({n})
            </Button>
            <Typography variant="caption" color="text.secondary" noWrap sx={{ minWidth: 0 }}>
              {windowLabel(resolvePreset(props.value.date, props.now))}
            </Typography>
          </Stack>
          <Drawer anchor="bottom" open={drawer} onClose={() => setDrawer(false)} data-testid="dashboard-filters-drawer">
            <Box sx={{ p: 2, maxHeight: '85vh', overflowY: 'auto' }}>
              <Stack direction="row" alignItems="center" sx={{ mb: 1.5 }}>
                <Typography variant="subtitle1" fontWeight={700} sx={{ flex: 1 }}>
                  Filters
                </Typography>
                <Button onClick={() => setDrawer(false)}>Done</Button>
              </Stack>
              <Controls {...props} stacked />
            </Box>
          </Drawer>
        </>
      ) : (
        <Controls {...props} />
      )}
      <ChipRow {...props} />
    </Paper>
  );
}
