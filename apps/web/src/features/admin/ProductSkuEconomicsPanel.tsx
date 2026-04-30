'use client';

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import {
  COMMON_SKU_COST_ISO_CODES,
  SKU_COST_CURRENCY_OTHER,
  resolveCostCurrencyFromSelect,
  splitCostCurrencyForSelect,
  validateSkuEconomicsInputs,
} from '@/features/commercial-planner/skuEconomicsCurrencyUi';
import { apiGet, apiPatch, apiPost } from '@/lib/api';

export type SkuAssumptionRow = {
  id: number;
  product_id: number;
  product_sku: string;
  product_name: string;
  controlled_cost_amount: number;
  controlled_cost_currency_code: string;
  vat_rate_pct: number;
  fx_plan_currency_per_cost_currency: number;
  reserve_total_pct: number;
  promo_reserve_split_pct: number;
};

type PlanRow = { id: number; currency_code: string };

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

  const { data: plans } = useQuery({
    queryKey: ['commercial-planner', 'plans'],
    queryFn: ({ signal }) => apiGet<PlanRow[]>('/api/v1/commercial-planner/plans', { signal }),
  });

  const planCurrencyHint = useMemo(() => {
    const raw = (plans?.[0]?.currency_code ?? '').trim();
    return raw || null;
  }, [plans]);

  const row = data?.length === 1 ? data[0] : undefined;
  const [dlgOpen, setDlgOpen] = useState(false);
  const [controlled, setControlled] = useState('100');
  const [ccySelect, setCcySelect] = useState<string>('USD');
  const [ccyOther, setCcyOther] = useState('');
  const [vat, setVat] = useState('0.15');
  const [fx, setFx] = useState('1');
  const [resTot, setResTot] = useState('0.10');
  const [resSplit, setResSplit] = useState('0.5');
  const [editId, setEditId] = useState<number | null>(null);

  useEffect(() => {
    if (row) {
      setEditId(row.id);
      setControlled(String(row.controlled_cost_amount));
      const sp = splitCostCurrencyForSelect(row.controlled_cost_currency_code);
      setCcySelect(sp.selectValue);
      setCcyOther(sp.otherIso);
      setVat(String(row.vat_rate_pct));
      setFx(String(row.fx_plan_currency_per_cost_currency));
      setResTot(String(row.reserve_total_pct));
      setResSplit(String(row.promo_reserve_split_pct));
    } else {
      setEditId(null);
      setControlled('100');
      setCcySelect('USD');
      setCcyOther('');
      setVat('0.15');
      setFx('1');
      setResTot('0.10');
      setResSplit('0.5');
    }
  }, [row]);

  const resolvedCcy = useMemo(() => resolveCostCurrencyFromSelect(ccySelect, ccyOther), [ccySelect, ccyOther]);

  const fxLabelDynamic = planCurrencyHint
    ? `FX: ${planCurrencyHint} per 1 ${resolvedCcy}`
    : 'FX: plan/local currency units per 1 controlled-cost currency';

  const validationErrors = useMemo(() => {
    return validateSkuEconomicsInputs({
      controlled_cost_amount: Number(controlled),
      controlled_cost_currency_code: resolvedCcy,
      fx_plan_currency_per_cost_currency: Number(fx),
      vat_rate_pct: Number(vat),
      reserve_total_pct: Number(resTot),
      promo_reserve_split_pct: Number(resSplit),
    });
  }, [controlled, resolvedCcy, fx, vat, resTot, resSplit]);

  const save = useMutation({
    mutationFn: async () => {
      const payload = {
        controlled_cost_amount: Number(controlled),
        controlled_cost_currency_code: resolvedCcy,
        vat_rate_pct: Number(vat),
        fx_plan_currency_per_cost_currency: Number(fx),
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
            <strong>Controlled cost / PM bottom:</strong> {Number(row.controlled_cost_amount).toFixed(2)}{' '}
            {(row.controlled_cost_currency_code || 'USD').trim()}
          </Typography>
          <Typography variant="body2">
            <strong>VAT % (decimal):</strong> {row.vat_rate_pct}
          </Typography>
          <Typography variant="body2">
            <strong>FX (plan per 1 cost ccy):</strong> {row.fx_plan_currency_per_cost_currency}
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
            <Typography variant="body2" color="text.secondary">
              <strong>Controlled cost / PM bottom</strong> is the internal SKU cost basis used by Commercial Planner
              economics. It is <strong>not</strong> populated from DAP or lineup evidence. It does{' '}
              <strong>not</strong> include logistics unless a future logistics model explicitly adds it.
            </Typography>
            <TextField
              label="Controlled cost amount (>0)"
              value={controlled}
              onChange={(e) => setControlled(e.target.value)}
              size="small"
              fullWidth
            />
            <FormControl size="small" fullWidth data-testid="product-sku-economics-ccy-select">
              <InputLabel id="sku-ccy-label">Controlled cost currency</InputLabel>
              <Select
                labelId="sku-ccy-label"
                label="Controlled cost currency"
                value={ccySelect}
                onChange={(e) => setCcySelect(String(e.target.value))}
              >
                {COMMON_SKU_COST_ISO_CODES.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
                <MenuItem value={SKU_COST_CURRENCY_OTHER}>Other (enter ISO code)</MenuItem>
              </Select>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                Currency of the PM bottom / controlled cost (not necessarily the same as plan currency).
              </Typography>
            </FormControl>
            {ccySelect === SKU_COST_CURRENCY_OTHER ? (
              <TextField
                label="Other ISO currency code"
                value={ccyOther}
                onChange={(e) => setCcyOther(e.target.value.toUpperCase())}
                size="small"
                fullWidth
                inputProps={{ maxLength: 8 }}
              />
            ) : null}
            <TextField label="VAT rate (0–1 decimal)" value={vat} onChange={(e) => setVat(e.target.value)} size="small" fullWidth />
            <TextField
              label={fxLabelDynamic}
              value={fx}
              onChange={(e) => setFx(e.target.value)}
              size="small"
              fullWidth
            />
            <Typography variant="caption" color="text.secondary" display="block">
              {planCurrencyHint ? (
                <>
                  Example: if plan currency is {planCurrencyHint} and controlled cost is {resolvedCcy}, enter{' '}
                  {planCurrencyHint} per 1 {resolvedCcy}.
                </>
              ) : (
                <>
                  Example: if plan currency is ZAR and controlled cost is USD, enter ZAR per 1 USD. (First commercial
                  plan in the workspace is used as a hint when available.)
                </>
              )}
            </Typography>
            <Alert severity="info" sx={{ py: 0.5 }} data-testid="product-sku-economics-fx-manual-notice">
              <Typography variant="caption" component="div">
                FX is a <strong>manually entered</strong> planning bridge for this assumption. The rate used in
                calculations stays on this row and is auditable. Latest FX automation will fetch a provider rate, then
                let you accept and lock it — not silently on every page load — when an FX provider is configured.
              </Typography>
            </Alert>
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
            {validationErrors.length ? (
              <Alert severity="warning" data-testid="product-sku-economics-validation">
                {validationErrors.map((e) => (
                  <Typography key={e} variant="caption" display="block">
                    {e}
                  </Typography>
                ))}
              </Alert>
            ) : null}
            {save.isError ? <Alert severity="error">Save failed. Check values and duplicates.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlgOpen(false)} disabled={save.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={save.isPending || validationErrors.length > 0}
            onClick={() => void save.mutateAsync().catch(() => undefined)}
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
