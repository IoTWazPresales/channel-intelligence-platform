'use client';

import {
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  InputAdornment,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { useCallback, useEffect, useState } from 'react';

import { apiGet } from '@/lib/api';

export type ProductPick = {
  id: number;
  sku: string;
  name: string;
  part_number: string | null;
  sales_model_name: string | null;
  model_name: string | null;
  category: string | null;
  product_line: string | null;
  series_name: string | null;
  lifecycle_status: string | null;
};

type ProductListResponse = { items: ProductPick[] };

export type ProductPickerDialogProps = {
  open: boolean;
  onClose: () => void;
  onSelect: (products: ProductPick[]) => void;
  multiSelect?: boolean;
  title?: string;
};

export function ProductPickerDialog({
  open,
  onClose,
  onSelect,
  multiSelect = false,
  title = 'Select product',
}: ProductPickerDialogProps) {
  const [q, setQ] = useState('');
  const [isActiveOnly, setIsActiveOnly] = useState(true);
  const [products, setProducts] = useState<ProductPick[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const doFetch = useCallback(
    async (query: string, activeOnly: boolean, signal: AbortSignal) => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ page: '1', page_size: '50' });
        if (query.trim()) params.set('q', query.trim());
        if (activeOnly) params.set('is_active', 'true');
        const res = await apiGet<ProductListResponse>(`/api/v1/products?${params.toString()}`, { signal });
        if (!signal.aborted) setProducts(res.items);
      } catch {
        if (!signal.aborted) setProducts([]);
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!open) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => doFetch(q, isActiveOnly, ctrl.signal), 400);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [open, q, isActiveOnly, doFetch]);

  useEffect(() => {
    if (!open) {
      setQ('');
      setSelected(new Set());
    }
  }, [open]);

  const toggleSelect = (product: ProductPick) => {
    if (!multiSelect) {
      onSelect([product]);
      onClose();
      return;
    }
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(product.id)) next.delete(product.id);
      else next.add(product.id);
      return next;
    });
  };

  const handleConfirm = () => {
    const picks = products.filter((p) => selected.has(p.id));
    onSelect(picks);
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg" aria-labelledby="product-picker-title">
      <DialogTitle id="product-picker-title">
        <Stack direction="row" alignItems="center" spacing={2}>
          <span>{title}</span>
          {multiSelect && selected.size > 0 && (
            <Chip label={`${selected.size} selected`} size="small" color="primary" />
          )}
        </Stack>
      </DialogTitle>
      <DialogContent dividers>
        <Stack direction="row" spacing={2} sx={{ mb: 2 }} alignItems="center">
          <TextField
            size="small"
            placeholder="Search SKU, model, name…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            sx={{ flex: 1 }}
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
          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={isActiveOnly}
                onChange={(e) => setIsActiveOnly(e.target.checked)}
              />
            }
            label="Active only"
            sx={{ m: 0 }}
            title="Filters catalogue rows where is_active is true (separate from lifecycle_status)."
          />
        </Stack>

        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          Active only uses the products API <code>is_active=true</code> filter (not lifecycle status).
        </Typography>

        <Box sx={{ position: 'relative', minHeight: 320, overflowX: 'auto' }}>
          {loading && (
            <Box
              sx={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: 'action.hover',
                zIndex: 1,
                opacity: 0.85,
              }}
            >
              <CircularProgress size={32} />
            </Box>
          )}
          {products.length === 0 && !loading ? (
            <Typography color="text.secondary" sx={{ py: 2 }}>
              No products found.
            </Typography>
          ) : (
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  {multiSelect && <TableCell padding="checkbox" />}
                  <TableCell>SKU</TableCell>
                  <TableCell>Part #</TableCell>
                  <TableCell>Sales model</TableCell>
                  <TableCell>Model</TableCell>
                  <TableCell>Name</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell>Lifecycle</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {products.map((p) => {
                  const isSelected = selected.has(p.id);
                  return (
                    <TableRow
                      key={p.id}
                      hover
                      selected={isSelected}
                      onClick={() => toggleSelect(p)}
                      sx={{ cursor: 'pointer' }}
                      data-testid={`product-row-${p.id}`}
                    >
                      {multiSelect && (
                        <TableCell
                          padding="checkbox"
                          onClick={(e) => {
                            e.stopPropagation();
                          }}
                        >
                          <Checkbox
                            size="small"
                            checked={isSelected}
                            onChange={() => toggleSelect(p)}
                            inputProps={{ 'aria-label': `Select ${p.sku}` }}
                          />
                        </TableCell>
                      )}
                      <TableCell>
                        <Typography variant="body2" fontFamily="monospace">
                          {p.sku || '—'}
                        </Typography>
                      </TableCell>
                      <TableCell>{p.part_number || '—'}</TableCell>
                      <TableCell>{p.sales_model_name || '—'}</TableCell>
                      <TableCell>{p.model_name || '—'}</TableCell>
                      <TableCell>{p.name || '—'}</TableCell>
                      <TableCell>{p.category || '—'}</TableCell>
                      <TableCell>{p.lifecycle_status || '—'}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </Box>
      </DialogContent>
      {multiSelect && (
        <DialogActions>
          <Button size="small" onClick={onClose}>
            Cancel
          </Button>
          <Button
            size="small"
            variant="contained"
            disabled={selected.size === 0}
            onClick={handleConfirm}
          >
            Add {selected.size > 0 ? `${selected.size} product${selected.size === 1 ? '' : 's'}` : '…'}
          </Button>
        </DialogActions>
      )}
    </Dialog>
  );
}
