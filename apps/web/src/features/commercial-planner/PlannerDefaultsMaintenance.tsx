'use client';

import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
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
import { useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';

type CustomerTerm = {
  id: number;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  customer_margin_pct: number;
  customer_rebate_pct: number;
};

type DistributorTerm = {
  id: number;
  distributor_id: number;
  distributor_code: string;
  distributor_name: string;
  distributor_margin_pct: number;
};

type SkuAssumption = {
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

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };
type ProductPick = { id: number; sku: string; name: string };

type CustomerListResponse = { items: CustomerPick[] };
type DistributorListResponse = { items: DistributorPick[] };
type ProductListResponse = { items: ProductPick[] };

async function fetchCustomers(q: string, signal: AbortSignal): Promise<CustomerPick[]> {
  const res = await apiGet<CustomerListResponse>(
    `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q)}`,
    { signal }
  );
  return res.items;
}

async function fetchDistributors(q: string, signal: AbortSignal): Promise<DistributorPick[]> {
  const res = await apiGet<DistributorListResponse>(
    `/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(q)}`,
    { signal }
  );
  return res.items;
}

async function fetchProducts(q: string, signal: AbortSignal): Promise<ProductPick[]> {
  const res = await apiGet<ProductListResponse>(
    `/api/v1/products?page=1&page_size=25&q=${encodeURIComponent(q)}`,
    { signal }
  );
  return res.items;
}

export function PlannerDefaultsMaintenance() {
  const qc = useQueryClient();
  const [custQ, setCustQ] = useState('');
  const [distQ, setDistQ] = useState('');
  const [skuQ, setSkuQ] = useState('');

  const { data: customerTerms, isError: ce } = useQuery({
    queryKey: ['commercial-planner', 'customer-terms', custQ],
    queryFn: ({ signal }) =>
      apiGet<CustomerTerm[]>(`/api/v1/commercial-planner/customer-terms?q=${encodeURIComponent(custQ)}`, { signal }),
  });
  const { data: distributorTerms, isError: de } = useQuery({
    queryKey: ['commercial-planner', 'distributor-terms', distQ],
    queryFn: ({ signal }) =>
      apiGet<DistributorTerm[]>(`/api/v1/commercial-planner/distributor-terms?q=${encodeURIComponent(distQ)}`, {
        signal,
      }),
  });
  const { data: skuAssumptions, isError: se } = useQuery({
    queryKey: ['commercial-planner', 'sku-assumptions', skuQ],
    queryFn: ({ signal }) =>
      apiGet<SkuAssumption[]>(`/api/v1/commercial-planner/sku-assumptions?q=${encodeURIComponent(skuQ)}`, { signal }),
  });

  const [custDlg, setCustDlg] = useState<'add' | 'edit' | null>(null);
  const [custPick, setCustPick] = useState<CustomerPick | null>(null);
  const [custMargin, setCustMargin] = useState('0.12');
  const [custRebate, setCustRebate] = useState('0.03');
  const [editCustId, setEditCustId] = useState<number | null>(null);

  const [distDlg, setDistDlg] = useState<'add' | 'edit' | null>(null);
  const [distPick, setDistPick] = useState<DistributorPick | null>(null);
  const [distMargin, setDistMargin] = useState('0.08');
  const [editDistId, setEditDistId] = useState<number | null>(null);

  const [skuDlg, setSkuDlg] = useState<'add' | 'edit' | null>(null);
  const [skuPick, setSkuPick] = useState<ProductPick | null>(null);
  const [landed, setLanded] = useState('100');
  const [vat, setVat] = useState('0.15');
  const [fx, setFx] = useState('1');
  const [resTot, setResTot] = useState('0.10');
  const [resSplit, setResSplit] = useState('0.5');
  const [editSkuId, setEditSkuId] = useState<number | null>(null);

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ['commercial-planner'] });
    void qc.invalidateQueries({ queryKey: ['commercial-plan-lines'] });
    void qc.invalidateQueries({ queryKey: ['commercial-plan-summary'] });
    void qc.invalidateQueries({ queryKey: ['commercial-plan-suggestions'] });
  };

  const saveCustomerTerm = useMutation({
    mutationFn: async () => {
      const margin = Number(custMargin);
      const rebate = Number(custRebate);
      if (editCustId != null) {
        return apiPatch<CustomerTerm>(`/api/v1/commercial-planner/customer-terms/${editCustId}`, {
          customer_margin_pct: margin,
          customer_rebate_pct: rebate,
        });
      }
      return apiPost<CustomerTerm>('/api/v1/commercial-planner/customer-terms', {
        customer_id: custPick!.id,
        customer_margin_pct: margin,
        customer_rebate_pct: rebate,
      });
    },
    onSuccess: () => {
      setCustDlg(null);
      setCustPick(null);
      setEditCustId(null);
      invalidateAll();
    },
  });

  const saveDistTerm = useMutation({
    mutationFn: async () => {
      const pct = Number(distMargin);
      if (editDistId != null) {
        return apiPatch<DistributorTerm>(`/api/v1/commercial-planner/distributor-terms/${editDistId}`, {
          distributor_margin_pct: pct,
        });
      }
      return apiPost<DistributorTerm>('/api/v1/commercial-planner/distributor-terms', {
        distributor_id: distPick!.id,
        distributor_margin_pct: pct,
      });
    },
    onSuccess: () => {
      setDistDlg(null);
      setDistPick(null);
      setEditDistId(null);
      invalidateAll();
    },
  });

  const saveSku = useMutation({
    mutationFn: async () => {
      const payload = {
        landed_cost_usd: Number(landed),
        vat_rate_pct: Number(vat),
        fx_rate_to_usd: Number(fx),
        reserve_total_pct: Number(resTot),
        promo_reserve_split_pct: Number(resSplit),
      };
      if (editSkuId != null) {
        return apiPatch<SkuAssumption>(`/api/v1/commercial-planner/sku-assumptions/${editSkuId}`, payload);
      }
      return apiPost<SkuAssumption>('/api/v1/commercial-planner/sku-assumptions', {
        product_id: skuPick!.id,
        ...payload,
      });
    },
    onSuccess: () => {
      setSkuDlg(null);
      setSkuPick(null);
      invalidateAll();
    },
  });

  const delCust = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/commercial-planner/customer-terms/${id}`),
    onSuccess: invalidateAll,
  });
  const delDist = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/commercial-planner/distributor-terms/${id}`),
    onSuccess: invalidateAll,
  });
  const delSku = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/commercial-planner/sku-assumptions/${id}`),
    onSuccess: invalidateAll,
  });

  const openEditCustomer = (row: CustomerTerm) => {
    setEditCustId(row.id);
    setCustPick({ id: row.customer_id, customer_code: row.customer_code, customer_name: row.customer_name });
    setCustMargin(String(row.customer_margin_pct));
    setCustRebate(String(row.customer_rebate_pct));
    setCustDlg('edit');
  };

  const openEditDistributor = (row: DistributorTerm) => {
    setEditDistId(row.id);
    setDistPick({
      id: row.distributor_id,
      distributor_code: row.distributor_code,
      distributor_name: row.distributor_name,
    });
    setDistMargin(String(row.distributor_margin_pct));
    setDistDlg('edit');
  };

  const openEditSku = (row: SkuAssumption) => {
    setEditSkuId(row.id);
    setSkuPick({ id: row.product_id, sku: row.product_sku, name: row.product_name });
    setLanded(String(row.landed_cost_usd));
    setVat(String(row.vat_rate_pct));
    setFx(String(row.fx_rate_to_usd));
    setResTot(String(row.reserve_total_pct));
    setResSplit(String(row.promo_reserve_split_pct));
    setSkuDlg('edit');
  };

  return (
    <Stack spacing={3}>
      {ce || de || se ? (
        <Alert severity="error">Could not load planner defaults. Check API connectivity and permissions.</Alert>
      ) : null}

      <Alert severity="info" data-testid="planner-defaults-guide">
        <Typography variant="body2" component="div" sx={{ '& strong': { fontWeight: 600 } }}>
          These tables are the <strong>authoritative defaults</strong> the calculator uses when a plan line does not set an explicit
          override. Click <strong>Add</strong> in each section, search for a master record, then enter percentages or dollars. After
          changes, open <strong>Plans & lines</strong> and run <strong>Recalculate</strong> so line-level stored outputs reflect the new
          assumptions. Missing rows produce honest <code>missing_*</code> flags until you add them.
        </Typography>
      </Alert>

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
          <Typography variant="subtitle1">Customer commercial terms</Typography>
          <Button size="small" variant="contained" onClick={() => { setCustDlg('add'); setEditCustId(null); setCustPick(null); setCustMargin('0.12'); setCustRebate('0.03'); }}>
            Add
          </Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          One row per customer: default <strong>margin</strong> and <strong>rebate</strong> as fractions (0–1). Plan lines can still override
          per line.
        </Typography>
        <TextField size="small" label="Filter" value={custQ} onChange={(e) => setCustQ(e.target.value)} sx={{ mb: 1, minWidth: 240 }} />
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Customer</TableCell>
              <TableCell>Margin %</TableCell>
              <TableCell>Rebate %</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(customerTerms ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={4}>
                  <Typography variant="body2" color="text.secondary">
                    No customer defaults yet. Click <strong>Add</strong>, search for a customer, then set margin and rebate.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              (customerTerms ?? []).map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    {r.customer_code} — {r.customer_name}
                  </TableCell>
                  <TableCell>{r.customer_margin_pct}</TableCell>
                  <TableCell>{r.customer_rebate_pct}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEditCustomer(r)}>
                      Edit
                    </Button>
                    <Button size="small" color="error" onClick={() => void delCust.mutate(r.id)}>
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
          <Typography variant="subtitle1">Distributor commercial terms</Typography>
          <Button size="small" variant="contained" onClick={() => { setDistDlg('add'); setEditDistId(null); setDistPick(null); setDistMargin('0.08'); }}>
            Add
          </Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          One row per distributor: default <strong>distributor margin</strong> (0–1) applied in channel economics unless overridden on a
          line.
        </Typography>
        <TextField size="small" label="Filter" value={distQ} onChange={(e) => setDistQ(e.target.value)} sx={{ mb: 1, minWidth: 240 }} />
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Distributor</TableCell>
              <TableCell>Margin %</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(distributorTerms ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={3}>
                  <Typography variant="body2" color="text.secondary">
                    No distributor defaults yet. Click <strong>Add</strong>, search for a distributor, then set margin.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              (distributorTerms ?? []).map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    {r.distributor_code} — {r.distributor_name}
                  </TableCell>
                  <TableCell>{r.distributor_margin_pct}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEditDistributor(r)}>
                      Edit
                    </Button>
                    <Button size="small" color="error" onClick={() => void delDist.mutate(r.id)}>
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
          <Typography variant="subtitle1">SKU assumptions (controlled cost, VAT, FX, reserves)</Typography>
          <Button size="small" variant="contained" onClick={() => { setSkuDlg('add'); setEditSkuId(null); setSkuPick(null); setLanded('100'); setVat('0.15'); setFx('1'); setResTot('0.10'); setResSplit('0.5'); }}>
            Add
          </Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          One row per product: <strong>controlled cost / PM bottom</strong> (amount stored in today&apos;s economics currency
          in <code>landed_cost_usd</code>), <strong>VAT rate</strong> (0–1),{' '}
          <strong>FX: local or plan currency units per 1 USD</strong>, total <strong>reserve %</strong>, and{' '}
          <strong>campaign/support reserve split</strong> (share of the reserve bucket). These inputs feed Commercial Planner
          economics. <strong>DAP evidence is not used as controlled cost.</strong> True landed cost (logistics, duties,
          freight, etc.) will be handled in a later phase — not in this field.
        </Typography>
        <Alert severity="info" sx={{ mb: 1, py: 0.5 }} data-testid="planner-defaults-sku-economics-disclaimers">
          <Typography variant="caption" component="div">
            DAP / sell-in evidence stays on the lineup and workbench — it does not populate SKU economics inputs. Logistics
            and true landed cost are separate from PM bottom.
          </Typography>
        </Alert>
        <TextField size="small" label="Filter" value={skuQ} onChange={(e) => setSkuQ(e.target.value)} sx={{ mb: 1, minWidth: 240 }} />
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Product</TableCell>
              <TableCell>PM bottom / controlled cost (stored USD amount)</TableCell>
              <TableCell>VAT (0–1)</TableCell>
              <TableCell>FX (local CCY per 1 USD)</TableCell>
              <TableCell>Reserve total (0–1)</TableCell>
              <TableCell>Campaign / support split (0–1)</TableCell>
              <TableCell align="right">Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(skuAssumptions ?? []).length === 0 ? (
              <TableRow>
                <TableCell colSpan={7}>
                  <Typography variant="body2" color="text.secondary">
                    No SKU assumptions yet. Click <strong>Add</strong>, search for a product, then enter controlled cost and rate fields.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              (skuAssumptions ?? []).map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    {r.product_sku} — {r.product_name}
                  </TableCell>
                  <TableCell>{r.landed_cost_usd}</TableCell>
                  <TableCell>{r.vat_rate_pct}</TableCell>
                  <TableCell>{r.fx_rate_to_usd}</TableCell>
                  <TableCell>{r.reserve_total_pct}</TableCell>
                  <TableCell>{r.promo_reserve_split_pct}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openEditSku(r)}>
                      Edit
                    </Button>
                    <Button size="small" color="error" onClick={() => void delSku.mutate(r.id)}>
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={custDlg != null} onClose={() => !saveCustomerTerm.isPending && setCustDlg(null)} fullWidth maxWidth="sm">
        <DialogTitle>{custDlg === 'edit' ? 'Edit customer term' : 'Add customer term'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {custDlg === 'add' ? (
              <EntitySearchAutocomplete<CustomerPick>
                label="Customer"
                value={custPick}
                onChange={setCustPick}
                fetchOptions={fetchCustomers}
                getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
                disabled={saveCustomerTerm.isPending}
                helperText="Search customers; only one default row is allowed per customer."
              />
            ) : (
              <Typography variant="body2" color="text.secondary">
                Customer: {custPick ? `${custPick.customer_code} — ${custPick.customer_name}` : ''}
              </Typography>
            )}
            <TextField label="Customer margin (0–1)" value={custMargin} onChange={(e) => setCustMargin(e.target.value)} />
            <TextField label="Customer rebate (0–1)" value={custRebate} onChange={(e) => setCustRebate(e.target.value)} />
            {saveCustomerTerm.isError ? <Alert severity="error">Save failed. Check values and duplicates.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCustDlg(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={(!custPick && editCustId == null) || saveCustomerTerm.isPending}
            onClick={() => void saveCustomerTerm.mutateAsync().catch(() => undefined)}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={distDlg != null} onClose={() => !saveDistTerm.isPending && setDistDlg(null)} fullWidth maxWidth="sm">
        <DialogTitle>{distDlg === 'edit' ? 'Edit distributor term' : 'Add distributor term'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {distDlg === 'add' ? (
              <EntitySearchAutocomplete<DistributorPick>
                label="Distributor"
                value={distPick}
                onChange={setDistPick}
                fetchOptions={fetchDistributors}
                getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
                disabled={saveDistTerm.isPending}
                helperText="Search distributors; one default row per distributor."
              />
            ) : (
              <Typography variant="body2" color="text.secondary">
                Distributor: {distPick ? `${distPick.distributor_code} — ${distPick.distributor_name}` : ''}
              </Typography>
            )}
            <TextField label="Distributor margin (0–1)" value={distMargin} onChange={(e) => setDistMargin(e.target.value)} />
            {saveDistTerm.isError ? <Alert severity="error">Save failed. Check values and duplicates.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDistDlg(null)}>Cancel</Button>
          <Button variant="contained" disabled={!distPick || saveDistTerm.isPending} onClick={() => void saveDistTerm.mutateAsync().catch(() => undefined)}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={skuDlg != null} onClose={() => !saveSku.isPending && setSkuDlg(null)} fullWidth maxWidth="sm">
        <DialogTitle>{skuDlg === 'edit' ? 'Edit SKU assumption' : 'Add SKU assumption'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {skuDlg === 'add' ? (
              <EntitySearchAutocomplete<ProductPick>
                label="Product"
                value={skuPick}
                onChange={setSkuPick}
                fetchOptions={fetchProducts}
                getOptionLabel={(o) => `${o.sku || '—'} — ${o.name || ''}`}
                disabled={saveSku.isPending}
                helperText="Search products; one SKU assumption row per product."
              />
            ) : (
              <Typography variant="body2" color="text.secondary">
                Product: {skuPick ? `${skuPick.sku} — ${skuPick.name}` : ''}
              </Typography>
            )}
            <TextField
              label="Controlled cost — USD amount stored as landed_cost_usd (>0)"
              value={landed}
              onChange={(e) => setLanded(e.target.value)}
            />
            <TextField label="VAT rate (0–1)" value={vat} onChange={(e) => setVat(e.target.value)} />
            <TextField
              label="FX: local/plan currency units per 1 USD (>0)"
              value={fx}
              onChange={(e) => setFx(e.target.value)}
            />
            <TextField label="Reserve total (0–1)" value={resTot} onChange={(e) => setResTot(e.target.value)} />
            <TextField
              label="Campaign / support reserve split (0–1)"
              value={resSplit}
              onChange={(e) => setResSplit(e.target.value)}
            />
            {saveSku.isError ? <Alert severity="error">Save failed. Check values and duplicates.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSkuDlg(null)}>Cancel</Button>
          <Button variant="contained" disabled={!skuPick || saveSku.isPending} onClick={() => void saveSku.mutateAsync().catch(() => undefined)}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
