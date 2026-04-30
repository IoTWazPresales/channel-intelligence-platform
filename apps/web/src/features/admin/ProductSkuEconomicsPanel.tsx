'use client';

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { apiGet, apiPatch, apiPost } from '@/lib/api';

export type SkuAssumptionRow = {
  id: number;
  product_id: number;
  product_sku: string;
  product_name: string;
  landed_cost_usd: number;
  vat_rate_pct: number;
  fx_rate_to_usd: number;
  reserve_total_pct: number;
  promo_reserve_split_pct: number;
};

type Props = {
  productId: number;
  productSku: string;
};

/** Single-product SKU economics (commercial_sku_assumption) for Product admin drawer. */
export function ProductSkuEconomicsPanel({ productId, productSku }: Props) {
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['commercial-planner', 'sku-assumptions', 'by-product', productId],
    queryFn: ({ signal }) =>
      apiGet<SkuAssumptionRow[]>(`/api/v1/commercial-planner/sku-assumptions?product_id=${productId}`, { signal }),
    enabled: productId > 0,
  });

  const row = data?.length === 1 ? data[0] : undefined;
  const [dlgOpen, setDlgOpen] = useState(false);
  const [controlled, setControlled] = useState('100');
  const [vat, setVat] = useState('0.15');
  const [fx, setFx] = useState('1');
  const [resTot, setResTot] = useState('0.10');
  const [resSplit, setResSplit] = useState('0.5');
  const [editId, setEditId] = useState<number | null>(null);

  useEffect(() => {
    if (row) {
      setEditId(row.id);
      setControlled(String(row.landed_cost_usd));
      setVat(String(row.vat_rate_pct));
      setFx(String(row.fx_rate_to_usd));
      setResTot(String(row.reserve_total_pct));
      setResSplit(String(row.promo_reserve_split_pct));
    } else {
      setEditId(null);
      setControlled('100');
      setVat('0.15');
      setFx('1');
      setResTot('0.10');
      setResSplit('0.5');
    }
  }, [row]);

  const save = useMutation({
    mutationFn: async () => {
      const payload = {
        landed_cost_usd: Number(controlled),
        vat_rate_pct: Number(vat),
        fx_rate_to_usd: Number(fx),
        reserve_total_pct: Number(resTot),
        promo_reserve_split_pct: Number(resSplit),
      };
      if (editId != null) {
        return apiPatch<SkuAssumptionRow>(`/api/v1/commercial-planner/sku-assumptions/${editId}`, payload);
      }
      return apiPost<SkuAssumptionRow>('/api/v1/commercial-planner/sku-assumptions', {
        product_id: productId,
        ...payload,
      });
    },
    onSuccess: async () => {
      setDlgOpen(false);
      await qc.invalidateQueries({ queryKey: ['commercial-planner', 'sku-assumptions'] });
      await qc.invalidateQueries({ queryKey: ['plan-readiness'] });
      await refetch();
    },
  });

  return (
    <Paper variant="outlined" sx={{ p: 1.25, mb: 1.5 }} data-testid="product-sku-economics-panel">
      <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
        SKU economics inputs
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        These SKU-level inputs feed Commercial Planner economics. They are <strong>not</strong> populated from DAP.
        Bulk edit all products in{' '}
        <Link href="/commercial-planner">Commercial planner</Link> → Planner defaults. True landed cost (logistics) is
        handled separately later.
      </Typography>
      {isLoading ? (
        <Typography variant="body2" color="text.secondary">
          Loading SKU economics…
        </Typography>
      ) : isError ? (
        <Alert severity="error">{String((error as Error)?.message ?? 'Failed to load')}</Alert>
      ) : !row ? (
        <Stack spacing={1}>
          <Typography variant="body2" color="text.secondary" data-testid="product-sku-economics-empty">
            No SKU economics inputs configured.
          </Typography>
          <Button size="small" variant="outlined" onClick={() => setDlgOpen(true)} data-testid="product-sku-economics-create">
            Create SKU economics
          </Button>
        </Stack>
      ) : (
        <Stack spacing={0.75}>
          <Typography variant="body2">
            <strong>Controlled cost / PM bottom (stored amount):</strong> USD {Number(row.landed_cost_usd).toFixed(2)}
          </Typography>
          <Typography variant="body2">
            <strong>VAT % (decimal):</strong> {row.vat_rate_pct}
          </Typography>
          <Typography variant="body2">
            <strong>FX (local currency units per 1 USD):</strong> {row.fx_rate_to_usd}
          </Typography>
          <Typography variant="body2">
            <strong>Reserve total %:</strong> {row.reserve_total_pct}
          </Typography>
          <Typography variant="body2">
            <strong>Campaign / support reserve split:</strong> {row.promo_reserve_split_pct}
          </Typography>
          <Button size="small" variant="outlined" onClick={() => setDlgOpen(true)} data-testid="product-sku-economics-edit">
            Edit SKU economics
          </Button>
        </Stack>
      )}

      <Dialog open={dlgOpen} onClose={() => !save.isPending && setDlgOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{row ? 'Edit SKU economics' : 'Create SKU economics'}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Product: {productSku} (id {productId})
            </Typography>
            <TextField
              label="Controlled cost / PM bottom — USD amount (landed_cost_usd, >0)"
              value={controlled}
              onChange={(e) => setControlled(e.target.value)}
              size="small"
              fullWidth
            />
            <TextField label="VAT rate (0–1 decimal)" value={vat} onChange={(e) => setVat(e.target.value)} size="small" fullWidth />
            <TextField
              label="FX: plan/local currency units per 1 USD (>0)"
              value={fx}
              onChange={(e) => setFx(e.target.value)}
              size="small"
              fullWidth
            />
            <TextField
              label="Reserve total % (0–1)"
              value={resTot}
              onChange={(e) => setResTot(e.target.value)}
              size="small"
              fullWidth
            />
            <TextField
              label="Campaign / support reserve split (0–1)"
              value={resSplit}
              onChange={(e) => setResSplit(e.target.value)}
              size="small"
              fullWidth
            />
            {save.isError ? <Alert severity="error">Save failed. Check values and duplicates.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlgOpen(false)} disabled={save.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={save.isPending || !Number.isFinite(Number(controlled))}
            onClick={() => void save.mutateAsync().catch(() => undefined)}
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
