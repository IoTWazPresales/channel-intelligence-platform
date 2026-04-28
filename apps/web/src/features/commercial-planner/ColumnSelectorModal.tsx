'use client';

import {
  Box,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { useMemo, useState } from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────

type PlanLine = {
  product_spec_cpu?: string | null;
  product_spec_ram?: string | null;
  product_spec_storage?: string | null;
  product_spec_gpu?: string | null;
  product_spec_display?: string | null;
  product_spec_warranty?: string | null;
  product_spec_os?: string | null;
  product_spec_colour?: string | null;
  product_category?: string | null;
  product_form_factor?: string | null;
  product_lifecycle_status?: string | null;
  product_line?: string | null;
  product_series_name?: string | null;
  product_business_unit?: string | null;
};

export type ColumnMetadata = {
  plan_id: number;
  total_products: number;
  catalogue: Record<string, number>;
  spec_keys: Record<string, number>;
  coverage_note: string;
};

export type ColumnSelectorModalProps = {
  open: boolean;
  onClose: () => void;
  lines: PlanLine[];
  optionalVisible: Record<string, boolean>;
  onChange: (key: string, visible: boolean) => void;
  onReset: () => void;
  onPreset: (name: string) => void;
  columnMeta?: ColumnMetadata | null;
  /** Per discovered specs_json key visibility (server metadata keys). */
  specKeyVisible?: Record<string, boolean>;
  onSpecKeyToggle?: (key: string, visible: boolean) => void;
};

// ── Preset definitions ────────────────────────────────────────────────────────

const PRESETS: { name: string; label: string; tooltip: string }[] = [
  { name: 'planning', label: 'Planning', tooltip: 'Default planning columns' },
  { name: 'product_spec', label: 'Product / spec', tooltip: 'Enable CPU, RAM, GPU, storage, display spec columns' },
  { name: 'commercial', label: 'Commercial', tooltip: 'Enable effective commercial term columns' },
  { name: 'economics', label: 'Economics', tooltip: 'Enable USD output columns (sell-in, net after disti, margin, reserves)' },
];

// ── Group definitions ─────────────────────────────────────────────────────────

type ColumnDef = {
  key: string;
  label: string;
  locked?: boolean;
  alwaysOn?: boolean;
  optional?: true;
  coverageKey?: string;
  /** Spec JSONB candidate key names (used to look up in columnMeta.spec_keys). */
  specCandidateKeys?: string[];
  /** Key name in columnMeta.catalogue (may differ from client-side coverageKey). */
  catalogueServerKey?: string;
};

type GroupDef = {
  title: string;
  description?: string;
  columns: ColumnDef[];
};

const COLUMN_GROUPS: GroupDef[] = [
  {
    title: 'Identity',
    description: 'Always visible — no toggles.',
    columns: [
      { key: 'customer', label: 'Customer', locked: true },
      { key: 'distributor', label: 'Distributor', locked: true },
      { key: 'product_sku', label: 'SKU', locked: true },
      { key: 'product_part_number', label: 'Part #', locked: true },
      { key: 'product_model_sales_model', label: 'Model / Sales model', locked: true },
      { key: 'product_name', label: 'Product name', locked: true },
    ],
  },
  {
    title: 'Specs',
    description: 'CPU, RAM, storage, GPU, display always shown when present. Coverage based on current plan lines.',
    columns: [
      { key: 'product_spec_cpu', label: 'CPU', alwaysOn: true, coverageKey: 'cpu', specCandidateKeys: ['cpu', 'CPU', 'processor'] },
      { key: 'product_spec_ram', label: 'RAM', alwaysOn: true, coverageKey: 'ram', specCandidateKeys: ['ram', 'RAM', 'memory'] },
      { key: 'product_spec_storage', label: 'Storage', alwaysOn: true, coverageKey: 'storage', specCandidateKeys: ['storage', 'Storage', 'disk', 'ssd', 'hdd'] },
      { key: 'product_spec_gpu', label: 'GPU', alwaysOn: true, coverageKey: 'gpu', specCandidateKeys: ['gpu', 'GPU', 'graphics'] },
      { key: 'product_spec_display', label: 'Display', alwaysOn: true, coverageKey: 'display', specCandidateKeys: ['display', 'Display', 'screen', 'panel'] },
      { key: 'product_spec_warranty', label: 'Warranty', optional: true },
      { key: 'product_spec_os', label: 'OS', optional: true },
      { key: 'product_spec_colour', label: 'Colour', optional: true },
    ],
  },
  {
    title: 'Product catalogue',
    columns: [
      { key: 'product_category', label: 'Category', optional: true, coverageKey: 'category', catalogueServerKey: 'category' },
      { key: 'product_form_factor', label: 'Form factor', optional: true, coverageKey: 'form_factor', catalogueServerKey: 'form_factor' },
      { key: 'product_lifecycle_status', label: 'Lifecycle', optional: true, coverageKey: 'lifecycle', catalogueServerKey: 'lifecycle_status' },
      { key: 'product_line', label: 'Product line', optional: true, coverageKey: 'product_line', catalogueServerKey: 'product_line' },
      { key: 'product_series_name', label: 'Series', optional: true, coverageKey: 'series', catalogueServerKey: 'series_name' },
      { key: 'product_business_unit', label: 'Business unit', optional: true, coverageKey: 'bu', catalogueServerKey: 'business_unit' },
    ],
  },
  {
    title: 'Planning inputs',
    columns: [
      { key: 'target_units', label: 'Units', locked: true },
      { key: 'target_srp_local', label: 'Target SRP', locked: true },
      { key: 'promo_srp_local', label: 'Promo SRP', locked: true },
      { key: 'promo_mix_pct', label: 'Promo mix %', optional: true },
    ],
  },
  {
    title: 'Commercial terms',
    description: 'Effective values used for economics. Optional columns.',
    columns: [
      { key: 'effective_customer_margin_pct', label: 'Customer margin % (effective)', optional: true },
      { key: 'effective_customer_rebate_pct', label: 'Customer rebate % (effective)', optional: true },
      { key: 'effective_distributor_margin_pct', label: 'Distributor margin % (effective)', optional: true },
      { key: 'effective_vat_rate_pct', label: 'VAT % (effective)', optional: true },
      { key: 'effective_fx_rate_to_usd', label: 'FX (local per USD, effective)', optional: true },
      { key: 'effective_reserve_total_pct', label: 'Reserve total % (effective)', optional: true },
      { key: 'effective_promo_reserve_split_pct', label: 'Promo reserve split % (effective)', optional: true },
      { key: 'effective_controlled_cost_usd_per_unit', label: 'Controlled cost USD / unit (effective)', optional: true },
    ],
  },
  {
    title: 'Local currency values',
    description: 'Sell-in and distributor-net in plan currency using effective FX × USD outputs. Always on when FX is configured.',
    columns: [
      { key: 'calc_sell_in_price_local', label: 'Sell-in (local)', alwaysOn: true },
      { key: 'calc_distributor_net_local', label: 'Distributor-net (local)', alwaysOn: true },
    ],
  },
  {
    title: 'USD model outputs',
    description: 'Sell-in and margin in USD. Internal margin always on.',
    columns: [
      { key: 'calc_sell_in_price_usd', label: 'Channel sell-in USD / unit', alwaysOn: true },
      { key: 'calc_internal_gp_usd', label: 'Est. OEM net margin USD (total, all units)', alwaysOn: true },
      { key: 'calc_buy_price_usd', label: 'Est. net after distributor margin USD / unit', optional: true },
      { key: 'calc_promo_reserve_usd', label: 'Promo reserve USD', optional: true },
      { key: 'calc_non_promo_reserve_usd', label: 'Non-promo reserve USD', optional: true },
    ],
  },
  {
    title: 'Issues / status',
    description: 'Always visible.',
    columns: [{ key: 'issues', label: 'Issues', locked: true }],
  },
];

// ── Coverage helpers ───────────────────────────────────────────────────────────

/**
 * Compute coverage count for a spec field.
 * When columnMeta is provided, sums across all candidate key names in spec_keys.
 * Otherwise falls back to client-side count.
 */
function getSpecCoverage(
  candidateKeys: string[],
  columnMeta: ColumnMetadata | null | undefined,
  clientCount: number,
): { count: number; fromServer: boolean } {
  if (columnMeta) {
    const serverCount = candidateKeys.reduce(
      (acc, k) => acc + (columnMeta.spec_keys[k] ?? 0),
      0,
    );
    return { count: serverCount, fromServer: true };
  }
  return { count: clientCount, fromServer: false };
}

// ── Main component ────────────────────────────────────────────────────────────

export function ColumnSelectorModal({
  open,
  onClose,
  lines,
  optionalVisible,
  onChange,
  onReset,
  onPreset,
  columnMeta,
  specKeyVisible = {},
  onSpecKeyToggle,
}: ColumnSelectorModalProps) {
  const [search, setSearch] = useState('');

  const specCoverage = useMemo(() => {
    const total = lines.length;
    if (total === 0) return { cpu: 0, ram: 0, storage: 0, gpu: 0, display: 0, total: 0 };
    return {
      cpu: lines.filter((l) => l.product_spec_cpu?.trim()).length,
      ram: lines.filter((l) => l.product_spec_ram?.trim()).length,
      storage: lines.filter((l) => l.product_spec_storage?.trim()).length,
      gpu: lines.filter((l) => l.product_spec_gpu?.trim()).length,
      display: lines.filter((l) => l.product_spec_display?.trim()).length,
      total,
    };
  }, [lines]);

  const catalogueCoverage = useMemo(
    () => ({
      category: lines.filter((l) => l.product_category?.trim()).length,
      form_factor: lines.filter((l) => l.product_form_factor?.trim()).length,
      lifecycle: lines.filter((l) => l.product_lifecycle_status?.trim()).length,
      product_line: lines.filter((l) => l.product_line?.trim()).length,
      series: lines.filter((l) => l.product_series_name?.trim()).length,
      bu: lines.filter((l) => l.product_business_unit?.trim()).length,
      total: lines.length,
    }),
    [lines]
  );

  const needle = search.trim().toLowerCase();

  const discoveredSpecEntries = useMemo(() => {
    const keys = columnMeta?.spec_keys ? Object.keys(columnMeta.spec_keys) : [];
    return keys
      .map((k) => ({ key: k, count: columnMeta!.spec_keys[k] ?? 0 }))
      .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
  }, [columnMeta]);

  const filteredDiscovered = useMemo(() => {
    if (!needle) return discoveredSpecEntries;
    return discoveredSpecEntries.filter(
      (e) => e.key.toLowerCase().includes(needle) || `${e.count}`.includes(needle)
    );
  }, [discoveredSpecEntries, needle]);

  const filteredGroups = useMemo(() => {
    if (!needle) return COLUMN_GROUPS;
    return COLUMN_GROUPS.map((g) => ({
      ...g,
      columns: g.columns.filter((c) => c.label.toLowerCase().includes(needle) || c.key.toLowerCase().includes(needle)),
    })).filter((g) => g.columns.length > 0);
  }, [needle]);

  const totalForCoverage = columnMeta ? columnMeta.total_products : lines.length;

  const optionalSelectedCount =
    Object.values(optionalVisible).filter(Boolean).length +
    Object.values(specKeyVisible).filter(Boolean).length;

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xl" aria-labelledby="col-selector-title">
      <DialogTitle id="col-selector-title">
        <Stack direction="row" alignItems="center" spacing={2} flexWrap="wrap" useFlexGap>
          <span>Column visibility</span>
          <Chip size="small" label={`${optionalSelectedCount} optional on`} variant="outlined" />
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        {/* Search */}
        <TextField
          size="small"
          fullWidth
          placeholder="Search columns and discovered spec keys…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ mb: 2 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
          }}
        />

        {/* Preset chips */}
        {!needle && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
              View presets
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {PRESETS.map((p) => (
                <Chip
                  key={p.name}
                  label={p.label}
                  size="small"
                  variant="outlined"
                  onClick={() => onPreset(p.name)}
                  title={p.tooltip}
                  sx={{ cursor: 'pointer' }}
                />
              ))}
            </Stack>
          </Box>
        )}

        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
          {columnMeta
            ? `Coverage counts from server (${columnMeta.total_products} products in plan). Locked columns cannot be hidden.`
            : 'Coverage counts are based on current plan lines. Locked columns cannot be hidden.'}
        </Typography>

        {onSpecKeyToggle && discoveredSpecEntries.length > 0 && (
          <Box
            sx={{ mb: 2, p: 2, border: '1px solid', borderColor: 'divider', borderRadius: 1 }}
            data-testid="column-selector-discovered-specs"
          >
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              Discovered spec JSON keys
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1.5 }}>
              From server metadata for this plan. Toggle to add as optional grid columns (0/N keys stay off by
              default).
            </Typography>
            {filteredDiscovered.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No keys match this search.
              </Typography>
            ) : (
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(3, 1fr)' },
                  gap: 0.5,
                }}
              >
                {filteredDiscovered.map((e) => {
                  const total = columnMeta?.total_products ?? lines.length;
                  const coverageLabel = total > 0 ? `${e.count} / ${total} products` : null;
                  const checked = specKeyVisible[e.key] ?? false;
                  return (
                    <FormControlLabel
                      key={e.key}
                      control={
                        <Checkbox
                          size="small"
                          checked={checked}
                          onChange={() => onSpecKeyToggle(e.key, !checked)}
                          data-testid={`col-spec-toggle-${e.key}`}
                        />
                      }
                      label={
                        <Box>
                          <Typography variant="body2" component="span">
                            {e.key}
                          </Typography>
                          {coverageLabel && (
                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                              {coverageLabel}
                              {e.count === 0 ? ' — not found in selected products' : ''}
                            </Typography>
                          )}
                        </Box>
                      }
                      sx={{ m: 0, alignItems: 'flex-start' }}
                    />
                  );
                })}
              </Box>
            )}
          </Box>
        )}

        {/* Groups */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', lg: 'repeat(2, minmax(0, 1fr))' },
            gap: 2,
            alignItems: 'start',
          }}
        >
        {filteredGroups.map((group, gi) => (
          <Box key={group.title} sx={{ mb: 2 }}>
            {gi > 0 && <Divider sx={{ mb: 1.5 }} />}
            <Typography variant="subtitle2" sx={{ mb: 0.25 }}>
              {group.title}
            </Typography>
            {group.description && (
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
                {group.description}
              </Typography>
            )}
            <Stack spacing={0.25}>
              {group.columns.map((col) => {
                // Compute coverage count based on server or client data
                let coverageCount: number | undefined;
                let coverageFromServer = false;

                if (col.specCandidateKeys) {
                  // Spec column: use server spec_keys or client fallback
                  const clientCount = col.coverageKey ? (specCoverage as Record<string, number>)[col.coverageKey] ?? 0 : 0;
                  const { count, fromServer } = getSpecCoverage(col.specCandidateKeys, columnMeta, clientCount);
                  coverageCount = count;
                  coverageFromServer = fromServer;
                } else if (col.catalogueServerKey && col.coverageKey) {
                  // Catalogue column: use server catalogue or client fallback
                  if (columnMeta) {
                    coverageCount = columnMeta.catalogue[col.catalogueServerKey] ?? 0;
                    coverageFromServer = true;
                  } else {
                    coverageCount = (catalogueCoverage as Record<string, number>)[col.coverageKey];
                  }
                } else if (col.coverageKey && !col.specCandidateKeys && !col.catalogueServerKey) {
                  // Legacy: coverage from client allCoverage (non-spec, non-catalogue fields)
                  const allCoverage: Record<string, number> = { ...specCoverage, ...catalogueCoverage };
                  coverageCount = allCoverage[col.coverageKey];
                }

                const coverageLabel =
                  coverageCount != null && totalForCoverage > 0
                    ? `${coverageCount} / ${totalForCoverage} populated`
                    : null;

                if (col.locked) {
                  return (
                    <Box key={col.key} sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 0.5, py: 0.25 }}>
                      <Checkbox size="small" checked disabled sx={{ p: 0 }} />
                      <Typography variant="body2" color="text.secondary">
                        {col.label}
                      </Typography>
                      <Chip label="Locked" size="small" sx={{ fontSize: '0.65rem', height: 18 }} />
                    </Box>
                  );
                }

                if (col.alwaysOn) {
                  // For spec columns with server data: check if coverage is 0
                  const specHasServerData = col.specCandidateKeys && coverageFromServer;
                  const specCoverageIsZero = specHasServerData && (coverageCount ?? 0) === 0;

                  if (specCoverageIsZero) {
                    return (
                      <Box key={col.key} sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 0.5, py: 0.25 }}>
                        <Checkbox size="small" checked disabled sx={{ p: 0 }} />
                        <Typography variant="body2" color="text.secondary">
                          {col.label}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {`0 / ${totalForCoverage} — not in catalog`}
                        </Typography>
                      </Box>
                    );
                  }

                  return (
                    <Box key={col.key} sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 0.5, py: 0.25 }}>
                      <Checkbox size="small" checked disabled sx={{ p: 0 }} />
                      <Typography variant="body2">{col.label}</Typography>
                      <Chip label="Always on" size="small" color="info" sx={{ fontSize: '0.65rem', height: 18 }} />
                      {coverageLabel && (
                        <Typography variant="caption" color="text.secondary">
                          {coverageLabel}
                        </Typography>
                      )}
                    </Box>
                  );
                }

                return (
                  <FormControlLabel
                    key={col.key}
                    control={
                      <Checkbox
                        size="small"
                        checked={optionalVisible[col.key] ?? false}
                        onChange={() => onChange(col.key, !(optionalVisible[col.key] ?? false))}
                        data-testid={`col-toggle-${col.key}`}
                      />
                    }
                    label={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2">{col.label}</Typography>
                        {coverageLabel && (
                          <Typography variant="caption" color="text.secondary">
                            {coverageLabel}
                          </Typography>
                        )}
                      </Box>
                    }
                    sx={{ m: 0, px: 0.5 }}
                  />
                );
              })}
            </Stack>
          </Box>
        ))}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button
          size="small"
          onClick={() => {
            onReset();
            onClose();
          }}
          data-testid="col-reset-defaults"
        >
          Reset to defaults
        </Button>
        <Box flex={1} />
        <Button size="small" variant="contained" onClick={onClose}>
          Done
        </Button>
      </DialogActions>
    </Dialog>
  );
}
