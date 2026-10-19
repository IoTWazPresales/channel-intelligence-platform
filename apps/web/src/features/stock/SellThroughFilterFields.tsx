'use client';

import AddIcon from '@mui/icons-material/Add';
import CloseIcon from '@mui/icons-material/Close';
import { Autocomplete, Box, Button, IconButton, Popover, TextField, Tooltip } from '@mui/material';
import { useCallback, useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { apiGet } from '@/lib/api';

import type { SellThroughFilterState } from './sellThroughFilters';

export type SellThroughDimension = { key: string; label: string; group: string; values: string[] };

type ProductPick = { id: number; sku: string; name: string; sales_model_name?: string | null };

const productLabel = (o: ProductPick) => {
  const name = o.sales_model_name || o.name;
  return name ? `${name} (${o.sku})` : o.sku;
};

/**
 * Product (one SKU) and the added filters of the Sell-through bar (Warren 2026-10-19). "+ Filter"
 * offers every product field, Product Master spec, customer field and store that has values; each
 * added filter is a searchable multi-select like Customers, with a button to remove it.
 */
export function SellThroughFilterFields({
  filters,
  dimensions,
  maxDimensions,
  onChange,
}: {
  filters: SellThroughFilterState;
  dimensions: SellThroughDimension[];
  maxDimensions: number;
  onChange: (patch: Partial<SellThroughFilterState>) => void;
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const byKey = new Map(dimensions.map((d) => [d.key, d]));
  const added = new Set(filters.dims.map((d) => d.key));
  const available = dimensions.filter((d) => !added.has(d.key));

  const fetchProducts = useCallback(async (query: string, signal: AbortSignal) => {
    const q = query.trim();
    const res = await apiGet<{ items: ProductPick[] }>(
      `/api/v1/products?page=1&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ''}`,
      { signal },
    );
    return res.items ?? [];
  }, []);

  const setValues = (key: string, values: string[]) =>
    onChange({ dims: filters.dims.map((d) => (d.key === key ? { key, values } : d)) });

  return (
    <>
      <Box sx={{ minWidth: 240, flex: '1 1 240px' }} data-testid="sellthrough-product-filter">
        <EntitySearchAutocomplete<ProductPick>
          label="Product (one SKU)"
          value={filters.product ? ({ id: filters.product.id, sku: filters.product.label, name: '' } as ProductPick) : null}
          onChange={(p) => onChange({ product: p ? { id: p.id, label: p.name ? productLabel(p) : p.sku } : null })}
          getOptionLabel={(o) => (o.name ? productLabel(o) : o.sku)}
          fetchOptions={fetchProducts}
        />
      </Box>
      {filters.dims.map((d) => {
        const dim = byKey.get(d.key);
        const label = dim?.label ?? d.key.replace(/^[a-z]+:/, '');
        return (
          <Box key={d.key} sx={{ display: 'flex', alignItems: 'center', minWidth: 200, flex: '1 1 200px' }}>
            <Autocomplete
              multiple
              size="small"
              limitTags={2}
              options={dim?.values ?? d.values}
              value={d.values}
              onChange={(_e, vals) => setValues(d.key, vals)}
              renderInput={(p) => <TextField {...p} label={label} placeholder={d.values.length ? '' : 'All'} />}
              sx={{ flex: 1 }}
              data-testid={`sellthrough-dim-${d.key}`}
            />
            <Tooltip title={`Remove ${label}`}>
              <IconButton
                size="small"
                aria-label={`Remove ${label} filter`}
                onClick={() => onChange({ dims: filters.dims.filter((x) => x.key !== d.key) })}
              >
                <CloseIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        );
      })}
      <Button
        size="small"
        startIcon={<AddIcon />}
        disabled={filters.dims.length >= maxDimensions || !available.length}
        onClick={(e) => setAnchor(e.currentTarget)}
        data-testid="sellthrough-add-filter"
        title={filters.dims.length >= maxDimensions ? `Up to ${maxDimensions} extra filters` : undefined}
      >
        Filter
      </Button>
      <Popover
        open={Boolean(anchor)}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Box sx={{ p: 1.5, width: 320 }}>
          <Autocomplete
            open
            autoFocus
            size="small"
            options={available}
            groupBy={(o) => o.group}
            getOptionLabel={(o) => o.label}
            onChange={(_e, d) => {
              if (d) onChange({ dims: [...filters.dims, { key: d.key, values: [] }] });
              setAnchor(null);
            }}
            renderInput={(p) => <TextField {...p} autoFocus label="Add a filter" placeholder="Search: RAM, Business unit, Store…" />}
            data-testid="sellthrough-add-filter-search"
            slotProps={{ popper: { disablePortal: true } }}
          />
          <Box sx={{ height: 300 }} />
        </Box>
      </Popover>
    </>
  );
}
