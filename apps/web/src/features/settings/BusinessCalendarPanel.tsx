'use client';

import {
  Alert,
  Box,
  Button,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { apiGet, apiPost, apiPut, safeDisplayError } from '@/lib/api';

/**
 * Warren 2026-10-19: the business calendar is set once here and every screen that groups by
 * week, month, quarter or year follows it. Companies use different calendars, so calendar months
 * with any financial-year start, 4-4-5 style week calendars and a fully custom list are offered.
 */
export type CalendarType = 'gregorian' | 'retail_445' | 'retail_454' | 'retail_544' | 'custom';

export type BusinessCalendarConfig = {
  type: CalendarType;
  fiscal_year_start_month: number;
  week_start_day: number;
  year_end_rule: 'last' | 'nearest';
  fiscal_year_named_by: 'start' | 'end';
  custom_periods: Array<{ start: string; fiscal_year: number; quarter: number; label?: string | null }>;
};

type ProfileSlice = {
  business_calendar?: BusinessCalendarConfig;
  vat_rate_pct?: number;
  sales_value_vat_basis?: 'ex_vat' | 'inc_vat';
};

type PreviewBucket = { start: string; end: string; label: string; quarter: number | null };
type Preview = {
  year: PreviewBucket;
  quarters: PreviewBucket[];
  months: PreviewBucket[];
  weeks: number;
};

const TYPE_LABELS: Record<CalendarType, string> = {
  gregorian: 'Calendar months',
  retail_445: 'Weeks, 4-4-5 per quarter',
  retail_454: 'Weeks, 4-5-4 per quarter',
  retail_544: 'Weeks, 5-4-4 per quarter',
  custom: 'Custom periods (I list them)',
};
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const WEEK_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

const DEFAULT_CONFIG: BusinessCalendarConfig = {
  type: 'gregorian',
  fiscal_year_start_month: 1,
  week_start_day: 0,
  year_end_rule: 'last',
  fiscal_year_named_by: 'end',
  custom_periods: [],
};

/** One period per line: first day, financial year, quarter, optional label. */
export function parseCustomPeriods(text: string): {
  periods: BusinessCalendarConfig['custom_periods'];
  errors: string[];
} {
  const periods: BusinessCalendarConfig['custom_periods'] = [];
  const errors: string[] = [];
  text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .forEach((line, i) => {
      const [start, fy, q, ...rest] = line.split(/[,;\t]/).map((s) => s.trim());
      const fiscalYear = Number(fy);
      const quarter = Number(q);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(start ?? '') || !Number.isInteger(fiscalYear) || ![1, 2, 3, 4].includes(quarter)) {
        errors.push(`Line ${i + 1}: write it as 2026-01-05, 2026, 1, Jan`);
        return;
      }
      periods.push({ start, fiscal_year: fiscalYear, quarter, label: rest.join(' ').trim() || null });
    });
  return { periods, errors };
}

function periodsToText(periods: BusinessCalendarConfig['custom_periods']): string {
  return periods.map((p) => [p.start, p.fiscal_year, p.quarter, p.label ?? ''].filter((v) => v !== '').join(', ')).join('\n');
}

export function BusinessCalendarPanel({ canEdit }: { canEdit: boolean }) {
  const qc = useQueryClient();
  const profile = useQuery({
    queryKey: ['auth', 'tenant-commercial-profile'],
    queryFn: () => apiGet<ProfileSlice>('/api/v1/auth/tenant-commercial-profile'),
    staleTime: 30_000,
  });
  const [cfg, setCfg] = useState<BusinessCalendarConfig>(DEFAULT_CONFIG);
  const [customText, setCustomText] = useState('');
  const [vatRate, setVatRate] = useState('15');
  const [vatBasis, setVatBasis] = useState<'ex_vat' | 'inc_vat'>('ex_vat');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const d = profile.data;
    if (!d) return;
    if (d.business_calendar) {
      setCfg({ ...DEFAULT_CONFIG, ...d.business_calendar });
      setCustomText(periodsToText(d.business_calendar.custom_periods ?? []));
    }
    if (typeof d.vat_rate_pct === 'number') setVatRate(String(Math.round(d.vat_rate_pct * 10000) / 100));
    if (d.sales_value_vat_basis) setVatBasis(d.sales_value_vat_basis);
  }, [profile.data]);

  const custom = useMemo(() => parseCustomPeriods(customText), [customText]);
  const draft = useMemo<BusinessCalendarConfig>(
    () => ({ ...cfg, custom_periods: cfg.type === 'custom' ? custom.periods : cfg.custom_periods }),
    [cfg, custom.periods],
  );
  const draftKey = JSON.stringify(draft);
  const [debouncedKey, setDebouncedKey] = useState(draftKey);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedKey(draftKey), 300);
    return () => clearTimeout(t);
  }, [draftKey]);

  const preview = useQuery({
    queryKey: ['business-calendar-preview', debouncedKey],
    queryFn: () =>
      apiPost<Preview>('/api/v1/auth/business-calendar/preview', { business_calendar: JSON.parse(debouncedKey) }),
    enabled: !(cfg.type === 'custom' && (custom.errors.length > 0 || custom.periods.length === 0)),
    retry: false,
  });

  const save = useMutation({
    mutationFn: () =>
      apiPut('/api/v1/auth/tenant-commercial-profile', {
        business_calendar: draft,
        vat_rate_pct: Number(vatRate) / 100,
        sales_value_vat_basis: vatBasis,
      }),
    onSuccess: (data) => {
      setSaved(true);
      qc.setQueryData(['auth', 'tenant-commercial-profile'], data);
      void qc.invalidateQueries({ queryKey: ['sell-through'] });
    },
    onError: () => setSaved(false),
  });

  const isRetail = cfg.type.startsWith('retail_');
  const set = (patch: Partial<BusinessCalendarConfig>) => {
    setSaved(false);
    setCfg((c) => ({ ...c, ...patch }));
  };

  return (
    <Box data-testid="business-calendar-panel">
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        Business calendar and sales value
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        How days roll up into weeks, months, quarters and years on every screen that groups by period, and how
        sales value is shown. The preview shows the year that contains today.
      </Typography>
      <Stack spacing={2} maxWidth={560}>
        {!canEdit ? <Alert severity="info">Admin role required to edit — showing current values read-only.</Alert> : null}
        <FormControl fullWidth disabled={!canEdit}>
          <InputLabel id="bc-type-label">Calendar</InputLabel>
          <Select
            labelId="bc-type-label"
            label="Calendar"
            value={cfg.type}
            onChange={(e) => set({ type: e.target.value as CalendarType })}
            inputProps={{ 'data-testid': 'bc-type' }}
          >
            {(Object.keys(TYPE_LABELS) as CalendarType[]).map((t) => (
              <MenuItem key={t} value={t}>
                {TYPE_LABELS[t]}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        {cfg.type !== 'custom' ? (
          <FormControl fullWidth disabled={!canEdit}>
            <InputLabel id="bc-start-label">{isRetail ? 'Year starts after the end of' : 'Financial year starts in'}</InputLabel>
            <Select
              labelId="bc-start-label"
              label={isRetail ? 'Year starts after the end of' : 'Financial year starts in'}
              value={isRetail ? ((cfg.fiscal_year_start_month + 10) % 12) + 1 : cfg.fiscal_year_start_month}
              onChange={(e) => {
                const m = Number(e.target.value);
                set({ fiscal_year_start_month: isRetail ? (m % 12) + 1 : m });
              }}
            >
              {MONTHS.map((m, i) => (
                <MenuItem key={m} value={i + 1}>
                  {m}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        ) : null}
        <FormControl fullWidth disabled={!canEdit}>
          <InputLabel id="bc-week-label">Weeks start on</InputLabel>
          <Select
            labelId="bc-week-label"
            label="Weeks start on"
            value={cfg.week_start_day}
            onChange={(e) => set({ week_start_day: Number(e.target.value) })}
          >
            {WEEK_DAYS.map((d, i) => (
              <MenuItem key={d} value={i}>
                {d}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        {isRetail ? (
          <FormControl fullWidth disabled={!canEdit}>
            <InputLabel id="bc-rule-label">Year ends on</InputLabel>
            <Select
              labelId="bc-rule-label"
              label="Year ends on"
              value={cfg.year_end_rule}
              onChange={(e) => set({ year_end_rule: e.target.value as 'last' | 'nearest' })}
            >
              <MenuItem value="last">The last full week in that month</MenuItem>
              <MenuItem value="nearest">The week ending nearest the month end</MenuItem>
            </Select>
          </FormControl>
        ) : null}
        <FormControl fullWidth disabled={!canEdit}>
          <InputLabel id="bc-named-label">Name a year after</InputLabel>
          <Select
            labelId="bc-named-label"
            label="Name a year after"
            value={cfg.fiscal_year_named_by}
            onChange={(e) => set({ fiscal_year_named_by: e.target.value as 'start' | 'end' })}
          >
            <MenuItem value="end">The calendar year it ends in</MenuItem>
            <MenuItem value="start">The calendar year it starts in</MenuItem>
          </Select>
        </FormControl>
        {cfg.type === 'custom' ? (
          <TextField
            label="Periods: first day, financial year, quarter, label"
            multiline
            minRows={6}
            value={customText}
            disabled={!canEdit}
            onChange={(e) => {
              setSaved(false);
              setCustomText(e.target.value);
            }}
            placeholder={'2026-01-05, 2026, 1, Jan\n2026-02-02, 2026, 1, Feb\n2026-03-02, 2026, 1, Mar'}
            helperText={custom.errors[0] ?? 'One period per line. A period runs until the next one starts.'}
            error={custom.errors.length > 0}
            inputProps={{ 'data-testid': 'bc-custom-periods' }}
          />
        ) : null}
        <Stack direction="row" spacing={2}>
          <TextField
            label="VAT rate %"
            type="number"
            value={vatRate}
            disabled={!canEdit}
            onChange={(e) => {
              setSaved(false);
              setVatRate(e.target.value);
            }}
            sx={{ width: 140 }}
          />
          <FormControl sx={{ minWidth: 260 }} disabled={!canEdit}>
            <InputLabel id="bc-vat-label">Show sales value</InputLabel>
            <Select
              labelId="bc-vat-label"
              label="Show sales value"
              value={vatBasis}
              onChange={(e) => {
                setSaved(false);
                setVatBasis(e.target.value as 'ex_vat' | 'inc_vat');
              }}
            >
              <MenuItem value="ex_vat">Excluding VAT</MenuItem>
              <MenuItem value="inc_vat">Including VAT</MenuItem>
            </Select>
          </FormControl>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          Each customer&apos;s prices are converted from the basis they report in. Screens can switch per view.
        </Typography>

        {preview.isError ? <Alert severity="warning">{safeDisplayError(preview.error)}</Alert> : null}
        {preview.data ? (
          <Box data-testid="bc-preview">
            <Typography variant="body2" sx={{ mb: 0.5 }}>
              <strong>{preview.data.year.label}</strong>: {preview.data.year.start} to {preview.data.year.end} ·{' '}
              {preview.data.weeks} weeks
            </Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Quarter</TableCell>
                  <TableCell>From</TableCell>
                  <TableCell>To</TableCell>
                  <TableCell>Months / periods</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {preview.data.quarters.map((q) => (
                  <TableRow key={q.start}>
                    <TableCell>{q.label}</TableCell>
                    <TableCell>{q.start}</TableCell>
                    <TableCell>{q.end}</TableCell>
                    <TableCell>
                      {preview.data.months
                        .filter((m) => m.start >= q.start && m.start <= q.end)
                        .map((m) => m.label)
                        .join(' · ')}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        ) : null}
        {save.isError ? <Alert severity="error">{safeDisplayError(save.error)}</Alert> : null}
        {saved ? <Alert severity="success">Saved. Screens use the new calendar from their next load.</Alert> : null}
        {canEdit ? (
          <Box>
            <Button
              variant="contained"
              disabled={save.isPending || (cfg.type === 'custom' && custom.errors.length > 0)}
              onClick={() => save.mutate()}
              data-testid="bc-save"
            >
              Save calendar and VAT
            </Button>
          </Box>
        ) : null}
      </Stack>
    </Box>
  );
}
