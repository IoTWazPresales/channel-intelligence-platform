'use client';

import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import {
  Alert,
  Autocomplete,
  Box,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useMemo, useState } from 'react';

/**
 * Shared, importer-agnostic column-mapping table for the "one file header -> one
 * canonical target" family (DSI / shipment). Provides the parity features that were
 * previously only on Product Master: a mapping summary, a mapped/unmapped filter,
 * in-row "what is this mapped to" status, and a searchable target dropdown with
 * descriptions and a duplicate ("also mapped from") warning — without PM's disposition
 * model.
 *
 * Presentational + local filter state only. The parent owns data fetching and the
 * save/validate mutations; this component reports draft changes via `onChange`.
 */

export type CanonicalTargetOption = {
  value: string;
  label: string;
  description?: string;
};

export type MappingBlockingError = { code: string; message: string };

export type MappingAdjustmentNotice = { code?: string; message?: string };

/**
 * A "must map at least one of" requirement, mirroring server-side mapping gates.
 * Used to render live "still needs" chips so gaps are visible before saving.
 */
export type CanonicalRequiredGroup = {
  id: string;
  label: string;
  anyOf: string[];
  /**
   * When true, the group counts as satisfied without a column mapping
   * (e.g. DSI per-file distributor banner stamps).
   */
  externallySatisfied?: boolean;
};

export type CanonicalColumnMappingPanelProps = {
  fileHeaders: string[];
  /** header -> canonical target (only mapped headers present). */
  draft: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  targetOptions: CanonicalTargetOption[];
  columnSamples?: Record<string, string[]>;
  blockingErrors?: MappingBlockingError[];
  adjustmentNotices?: MappingAdjustmentNotice[];
  requiredGroups?: CanonicalRequiredGroup[];
  /** Render samples for a column; defaults to a comma join. */
  formatSamples?: (samples: string[] | undefined) => string;
  /** True when the draft differs from the last-saved server mapping. */
  dirty?: boolean;
  disabled?: boolean;
  /** When set, emits stable test ids: `${testIdPrefix}-samples-${header}` and `-map-`. */
  testIdPrefix?: string;
};

type RowFilter = 'all' | 'mapped' | 'unmapped';

const UNMAPPED_OPTION: CanonicalTargetOption = { value: '', label: '— Unmapped —' };

/**
 * A target option enriched with the dropdown section it belongs to for a given row.
 * Sections are dynamic (depend on what is already mapped + which requirements are
 * still open), mirroring Product Master's status-aware target grouping.
 */
type SectionedOption = CanonicalTargetOption & { sectionLabel: string; sortTier: number };

const SECTION = {
  CLEAR: { label: 'Clear mapping', tier: -10 },
  SELECTED: { label: 'Selected for this column', tier: 0 },
  STILL_NEEDED: { label: 'Still needed', tier: 10 },
  AVAILABLE: { label: 'Available to map', tier: 50 },
  ALREADY_MAPPED: { label: 'Already mapped in this file', tier: 90 },
} as const;

function defaultFormatSamples(samples: string[] | undefined): string {
  if (!samples?.length) return '—';
  const parts = samples.map((s) => (s.length > 48 ? `${s.slice(0, 45)}…` : s)).filter(Boolean);
  return parts.length ? parts.join(', ') : '—';
}

export function CanonicalColumnMappingPanel({
  fileHeaders,
  draft,
  onChange,
  targetOptions,
  columnSamples,
  blockingErrors,
  adjustmentNotices,
  requiredGroups,
  formatSamples = defaultFormatSamples,
  dirty = false,
  disabled = false,
  testIdPrefix,
}: CanonicalColumnMappingPanelProps) {
  const [rowFilter, setRowFilter] = useState<RowFilter>('all');

  const targetSet = useMemo(() => new Set(targetOptions.map((t) => t.value)), [targetOptions]);
  const labelByValue = useMemo(() => {
    const m: Record<string, string> = {};
    for (const t of targetOptions) m[t.value] = t.label;
    return m;
  }, [targetOptions]);

  const mappedHeaders = useMemo(
    () => fileHeaders.filter((h) => Boolean(draft[h]) && targetSet.has(draft[h])),
    [fileHeaders, draft, targetSet]
  );
  const mappedCount = mappedHeaders.length;
  const unmappedCount = fileHeaders.length - mappedCount;

  /** target value -> headers that map to it (for duplicate "also mapped from" warnings). */
  const headersByTarget = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const h of mappedHeaders) {
      const t = draft[h];
      (m[t] ??= []).push(h);
    }
    return m;
  }, [mappedHeaders, draft]);

  const mappedTargetValues = useMemo(() => new Set(mappedHeaders.map((h) => draft[h])), [mappedHeaders, draft]);
  const groupStatus = useMemo(
    () =>
      (requiredGroups ?? []).map((g) => ({
        ...g,
        satisfied: Boolean(g.externallySatisfied) || g.anyOf.some((t) => mappedTargetValues.has(t)),
      })),
    [requiredGroups, mappedTargetValues]
  );

  /** Targets that satisfy a requirement that is not yet met → "still needed" section. */
  const stillNeededTargets = useMemo(() => {
    const s = new Set<string>();
    for (const g of groupStatus) {
      if (g.satisfied) continue;
      for (const t of g.anyOf) s.add(t);
    }
    return s;
  }, [groupStatus]);

  /**
   * Build the dropdown options for a single row, assigning each target to a dynamic,
   * status-aware section and sorting so MUI groupBy renders contiguous headers.
   */
  const buildRowOptions = (header: string): SectionedOption[] => {
    const current = draft[header] ?? '';
    const opts: SectionedOption[] = [
      { ...UNMAPPED_OPTION, sectionLabel: SECTION.CLEAR.label, sortTier: SECTION.CLEAR.tier },
    ];
    for (const t of targetOptions) {
      const usedByOthers = (headersByTarget[t.value] ?? []).some((x) => x !== header);
      let section: { label: string; tier: number } = SECTION.AVAILABLE;
      if (t.value === current) section = SECTION.SELECTED;
      else if (usedByOthers) section = SECTION.ALREADY_MAPPED;
      else if (stillNeededTargets.has(t.value)) section = SECTION.STILL_NEEDED;
      opts.push({ ...t, sectionLabel: section.label, sortTier: section.tier });
    }
    return opts.sort((a, b) => (a.sortTier !== b.sortTier ? a.sortTier - b.sortTier : a.label.localeCompare(b.label)));
  };

  const visibleHeaders = useMemo(() => {
    if (rowFilter === 'mapped') return fileHeaders.filter((h) => Boolean(draft[h]) && targetSet.has(draft[h]));
    if (rowFilter === 'unmapped') return fileHeaders.filter((h) => !draft[h] || !targetSet.has(draft[h]));
    return fileHeaders;
  }, [rowFilter, fileHeaders, draft, targetSet]);

  const selectedValue = (header: string): string => {
    const v = draft[header] ?? '';
    return v && targetSet.has(v) ? v : '';
  };

  const setTarget = (header: string, value: string) => {
    const next = { ...draft };
    if (!value) delete next[header];
    else next[header] = value;
    onChange(next);
  };

  return (
    <Stack spacing={1.5}>
      {blockingErrors?.length ? (
        <Alert severity="error">
          <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
            Fix mapping before validating
          </Typography>
          <Stack component="ul" sx={{ m: 0, pl: 2 }}>
            {blockingErrors.map((e) => (
              <Typography key={e.code} component="li" variant="body2">
                {e.message}
              </Typography>
            ))}
          </Stack>
        </Alert>
      ) : null}

      {adjustmentNotices?.length ? (
        <Alert severity="info">
          {adjustmentNotices.map((n) => (
            <Typography key={n.code ?? n.message} variant="body2">
              {n.message}
            </Typography>
          ))}
        </Alert>
      ) : null}

      {dirty ? (
        <Alert severity="warning">You have unsaved mapping changes. Save before running validation.</Alert>
      ) : null}

      <Paper variant="outlined" sx={{ p: 1.5, bgcolor: 'action.hover' }}>
        <Typography variant="caption" fontWeight={600} display="block" gutterBottom>
          Mapping summary
        </Typography>
        <Stack direction="row" flexWrap="wrap" gap={1} useFlexGap>
          <Chip size="small" color="success" variant="outlined" label={`Mapped: ${mappedCount}`} />
          <Chip
            size="small"
            color={unmappedCount > 0 ? 'default' : 'success'}
            variant="outlined"
            label={`Unmapped: ${unmappedCount}`}
          />
          {groupStatus.map((g) => (
            <Chip
              key={g.id}
              size="small"
              color={g.satisfied ? 'success' : 'warning'}
              label={`${g.label}: ${
                g.satisfied ? (g.externallySatisfied ? 'OK (file stamp)' : 'OK') : 'needs mapping'
              }`}
            />
          ))}
        </Stack>
      </Paper>

      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <FormControl size="small" sx={{ minWidth: 200 }}>
          <InputLabel id={`${testIdPrefix ?? 'canon'}-row-filter`}>Show columns</InputLabel>
          <Select
            labelId={`${testIdPrefix ?? 'canon'}-row-filter`}
            label="Show columns"
            value={rowFilter}
            onChange={(e) => setRowFilter(e.target.value as RowFilter)}
          >
            <MenuItem value="all">All columns ({fileHeaders.length})</MenuItem>
            <MenuItem value="mapped">Mapped only ({mappedCount})</MenuItem>
            <MenuItem value="unmapped">Unmapped only ({unmappedCount})</MenuItem>
          </Select>
        </FormControl>
        <Typography variant="caption" color="text.secondary">
          Showing {visibleHeaders.length} of {fileHeaders.length}
        </Typography>
      </Stack>

      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ fontWeight: 600 }}>File column</TableCell>
            <TableCell sx={{ fontWeight: 600, minWidth: 280 }}>Maps to</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {visibleHeaders.map((h) => {
            const current = selectedValue(h);
            const rowOptions = buildRowOptions(h);
            const currentOption = rowOptions.find((o) => o.value === current) ?? rowOptions[0];
            const currentDuplicates = current ? (headersByTarget[current] ?? []).filter((x) => x !== h) : [];
            return (
              <TableRow key={h}>
                <TableCell>
                  <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
                    <Typography fontWeight={600}>{h}</Typography>
                    {current ? (
                      <Chip
                        size="small"
                        color={currentDuplicates.length ? 'warning' : 'success'}
                        variant="outlined"
                        label={labelByValue[current] ?? current}
                      />
                    ) : (
                      <Chip size="small" variant="outlined" label="Unmapped" />
                    )}
                  </Stack>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                    data-testid={testIdPrefix ? `${testIdPrefix}-samples-${h}` : undefined}
                  >
                    Examples: {formatSamples(columnSamples?.[h])}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Autocomplete<SectionedOption>
                    size="small"
                    disabled={disabled}
                    options={rowOptions}
                    value={currentOption}
                    groupBy={(opt) => opt.sectionLabel}
                    getOptionLabel={(opt) => opt.label}
                    isOptionEqualToValue={(a, b) => a.value === b.value}
                    onChange={(_, opt) => setTarget(h, opt?.value ?? '')}
                    renderOption={(props, opt) => {
                      const { key, ...liProps } = props as { key?: string } & Record<string, unknown>;
                      const dups = opt.value ? (headersByTarget[opt.value] ?? []).filter((x) => x !== h) : [];
                      return (
                        <li key={opt.value || 'unmapped'} {...liProps}>
                          <Stack direction="row" alignItems="flex-start" spacing={0.5} sx={{ width: '100%', py: 0.25 }}>
                            <Box sx={{ flex: 1, minWidth: 0 }}>
                              <Stack direction="row" alignItems="center" spacing={0.5} flexWrap="wrap" useFlexGap>
                                <Typography variant="body2">{opt.label}</Typography>
                                {opt.value && stillNeededTargets.has(opt.value) && dups.length === 0 ? (
                                  <Chip size="small" color="warning" variant="outlined" label="Needed" sx={{ height: 18 }} />
                                ) : null}
                              </Stack>
                              {opt.description ? (
                                <Typography variant="caption" color="text.secondary" display="block">
                                  {opt.description}
                                </Typography>
                              ) : null}
                              {dups.length ? (
                                <Typography variant="caption" color="warning.main" display="block">
                                  Also mapped from: {dups.join(', ')}
                                </Typography>
                              ) : null}
                            </Box>
                            {opt.description ? (
                              <Tooltip title={opt.description}>
                                <InfoOutlinedIcon sx={{ fontSize: 18, color: 'text.secondary', mt: 0.25 }} />
                              </Tooltip>
                            ) : null}
                          </Stack>
                        </li>
                      );
                    }}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Target"
                        placeholder="Search targets…"
                        inputProps={{
                          ...params.inputProps,
                          'data-testid': testIdPrefix ? `${testIdPrefix}-map-${h}` : undefined,
                        }}
                        helperText={
                          currentDuplicates.length
                            ? `Also mapped from: ${currentDuplicates.join(', ')}`
                            : undefined
                        }
                        FormHelperTextProps={
                          currentDuplicates.length ? { sx: { color: 'warning.main', mx: 0 } } : undefined
                        }
                      />
                    )}
                  />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Stack>
  );
}
