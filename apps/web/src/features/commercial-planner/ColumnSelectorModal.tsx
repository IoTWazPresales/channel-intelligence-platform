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

export type ColumnSelectorModalProps = {
  open: boolean;
  onClose: () => void;
  lines: PlanLine[];
  optionalVisible: Record<string, boolean>;
  onChange: (key: string, visible: boolean) => void;
  onReset: () => void;
  onPreset: (name: string) => void;
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
      { key: 'product_spec_cpu', label: 'CPU', alwaysOn: true, coverageKey: 'cpu' },
      { key: 'product_spec_ram', label: 'RAM', alwaysOn: true, coverageKey: 'ram' },
      { key: 'product_spec_storage', label: 'Storage', alwaysOn: true, coverageKey: 'storage' },
      { key: 'product_spec_gpu', label: 'GPU', alwaysOn: true, coverageKey: 'gpu' },
      { key: 'product_spec_display', label: 'Display', alwaysOn: true, coverageKey: 'display' },
      { key: 'product_spec_warranty', label: 'Warranty', optional: true },
      { key: 'product_spec_os', label: 'OS', optional: true },
      { key: 'product_spec_colour', label: 'Colour', optional: true },
    ],
  },
  {
    title: 'Product catalogue',
    columns: [
      { key: 'product_category', label: 'Category', optional: true, coverageKey: 'category' },
      { key: 'product_form_factor', label: 'Form factor', optional: true, coverageKey: 'form_factor' },
      { key: 'product_lifecycle_status', label: 'Lifecycle', optional: true, coverageKey: 'lifecycle' },
      { key: 'product_line', label: 'Product line', optional: true, coverageKey: 'product_line' },
      { key: 'product_series_name', label: 'Series', optional: true, coverageKey: 'series' },
      { key: 'product_business_unit', label: 'Business unit', optional: true, coverageKey: 'bu' },
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
      { key: 'calc_internal_gp_usd', label: 'Est. internal margin USD / unit', alwaysOn: true },
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

// ── Main component ────────────────────────────────────────────────────────────

export function ColumnSelectorModal({
  open,
  onClose,
  lines,
  optionalVisible,
  onChange,
  onReset,
  onPreset,
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

  const allCoverage: Record<string, number> = {
    ...specCoverage,
    ...catalogueCoverage,
  };

  const needle = search.trim().toLowerCase();

  const filteredGroups = useMemo(() => {
    if (!needle) return COLUMN_GROUPS;
    return COLUMN_GROUPS.map((g) => ({
      ...g,
      columns: g.columns.filter((c) => c.label.toLowerCase().includes(needle) || c.key.toLowerCase().includes(needle)),
    })).filter((g) => g.columns.length > 0);
  }, [needle]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md" aria-labelledby="col-selector-title">
      <DialogTitle id="col-selector-title">Column visibility</DialogTitle>
      <DialogContent dividers>
        {/* Search */}
        <TextField
          size="small"
          fullWidth
          placeholder="Search columns…"
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
          Coverage counts are based on current plan lines. Locked columns cannot be hidden.
        </Typography>

        {/* Groups */}
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
                const coverageCount = col.coverageKey != null ? allCoverage[col.coverageKey] : undefined;
                const total = lines.length;
                const coverageLabel =
                  coverageCount != null && total > 0 ? `${coverageCount} / ${total} populated` : null;

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
