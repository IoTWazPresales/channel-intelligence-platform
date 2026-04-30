'use client';

import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useRef, useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import {
  COMMON_SKU_COST_ISO_CODES,
  SKU_COST_CURRENCY_OTHER,
  resolveCostCurrencyFromSelect,
  splitCostCurrencyForSelect,
  validateSkuEconomicsInputs,
} from '@/features/commercial-planner/skuEconomicsCurrencyUi';
import { apiDelete, apiDownloadBlob, apiGet, apiPatch, apiPost, apiPostFormData } from '@/lib/api';

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
  controlled_cost_amount: number;
  controlled_cost_currency_code: string;
  vat_rate_pct: number;
  fx_plan_currency_per_cost_currency: number;
  reserve_total_pct: number;
  promo_reserve_split_pct: number;
};

type SkuImportPreviewRow = {
  source_row: number;
  sku: string | null;
  part_number: string | null;
  sales_model: string | null;
  model_name: string | null;
  product_id: number | null;
  product_sku: string | null;
  product_name: string | null;
  match_method: string | null;
  action: string;
  messages: string[];
  blocking: boolean;
  current: Record<string, unknown> | null;
  proposed: Record<string, unknown> | null;
};

type SkuImportPreviewResponse = {
  parse_errors: string[];
  rows: SkuImportPreviewRow[];
  summary: { creates: number; updates: number; errors: number; blocking_errors: number };
  can_apply: boolean;
};

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };
type ProductPick = { id: number; sku: string; name: string };
type PlanRow = { id: number; currency_code: string };

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

  const { data: plansForCcy } = useQuery({
    queryKey: ['commercial-planner', 'plans'],
    queryFn: ({ signal }) => apiGet<PlanRow[]>('/api/v1/commercial-planner/plans', { signal }),
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
  const [controlledCost, setControlledCost] = useState('100');
  const [skuCcySelect, setSkuCcySelect] = useState('USD');
  const [skuCcyOther, setSkuCcyOther] = useState('');
  const [vat, setVat] = useState('0.15');
  const [fx, setFx] = useState('1');
  const [resTot, setResTot] = useState('0.10');
  const [resSplit, setResSplit] = useState('0.5');
  const [editSkuId, setEditSkuId] = useState<number | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [importPreview, setImportPreview] = useState<SkuImportPreviewResponse | null>(null);
  const [importApplySummary, setImportApplySummary] = useState<{ applied_creates: number; applied_updates: number } | null>(
    null
  );
  const [importConfirm, setImportConfirm] = useState(false);
  const [importFileLabel, setImportFileLabel] = useState<string | null>(null);
  const lastImportFileRef = useRef<File | null>(null);

  const planCurrencyHint = useMemo(() => {
    const raw = (plansForCcy?.[0]?.currency_code ?? '').trim();
    return raw || null;
  }, [plansForCcy]);

  const resolvedSkuCcy = useMemo(
    () => resolveCostCurrencyFromSelect(skuCcySelect, skuCcyOther),
    [skuCcySelect, skuCcyOther],
  );
  const skuFxLabel = planCurrencyHint
    ? `FX: ${planCurrencyHint} per 1 ${resolvedSkuCcy}`
    : 'FX: plan/local currency units per 1 controlled-cost currency';
  const skuValidationErrors = useMemo(
    () =>
      validateSkuEconomicsInputs({
        controlled_cost_amount: Number(controlledCost),
        controlled_cost_currency_code: resolvedSkuCcy,
        fx_plan_currency_per_cost_currency: Number(fx),
        vat_rate_pct: Number(vat),
        reserve_total_pct: Number(resTot),
        promo_reserve_split_pct: Number(resSplit),
      }),
    [controlledCost, resolvedSkuCcy, fx, vat, resTot, resSplit],
  );

  const invalidateAll = () => {
    void qc.invalidateQueries({ queryKey: ['commercial-planner'] });
    void qc.invalidateQueries({ queryKey: ['commercial-plan-lines'] });
    void qc.invalidateQueries({ queryKey: ['commercial-plan-summary'] });
    void qc.invalidateQueries({ queryKey: ['commercial-plan-suggestions'] });
    void qc.invalidateQueries({ queryKey: ['plan-readiness'] });
    void qc.invalidateQueries({ queryKey: ['admin-products'] });
  };

  const previewSkuImport = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return apiPostFormData<SkuImportPreviewResponse>('/api/v1/commercial-planner/sku-assumptions/import-preview', fd);
    },
    onSuccess: (data) => {
      setImportPreview(data);
      setImportApplySummary(null);
      setImportConfirm(false);
    },
  });

  const applySkuImport = useMutation({
    mutationFn: async (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('confirm', 'true');
      return apiPostFormData<{ applied_creates: number; applied_updates: number; summary: unknown }>(
        '/api/v1/commercial-planner/sku-assumptions/import-apply',
        fd
      );
    },
    onSuccess: (data) => {
      setImportApplySummary({ applied_creates: data.applied_creates, applied_updates: data.applied_updates });
      setImportPreview(null);
      setImportFileLabel(null);
      setImportConfirm(false);
      invalidateAll();
    },
  });

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
        controlled_cost_amount: Number(controlledCost),
        controlled_cost_currency_code: resolvedSkuCcy,
        vat_rate_pct: Number(vat),
        fx_plan_currency_per_cost_currency: Number(fx),
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
      setEditSkuId(null);
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
    setControlledCost(String(row.controlled_cost_amount));
    const sp = splitCostCurrencyForSelect(row.controlled_cost_currency_code);
    setSkuCcySelect(sp.selectValue);
    setSkuCcyOther(sp.otherIso);
    setVat(String(row.vat_rate_pct));
    setFx(String(row.fx_plan_currency_per_cost_currency));
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
          <Button
            size="small"
            variant="contained"
            onClick={() => {
              setSkuDlg('add');
              setEditSkuId(null);
              setSkuPick(null);
              setControlledCost('100');
              setSkuCcySelect('USD');
              setSkuCcyOther('');
              setVat('0.15');
              setFx('1');
              setResTot('0.10');
              setResSplit('0.5');
            }}
          >
            Add
          </Button>
        </Stack>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          One row per product: <strong>controlled cost / PM bottom</strong> (amount +{' '}
          <code>controlled_cost_currency_code</code>), <strong>VAT rate</strong> (0–1),{' '}
          <strong>FX: plan currency units per 1 controlled-cost currency</strong>, total <strong>reserve %</strong>, and{' '}
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
        <Alert severity="warning" sx={{ mb: 1, py: 0.5 }} data-testid="planner-defaults-sku-bulk-dap-copy">
          <Typography variant="caption" component="div">
            <strong>Controlled cost / PM bottom</strong> must come from an approved cost source. DAP and Rand landed evidence
            are <strong>not</strong> used as controlled cost. Do not add DAP columns to this template.
          </Typography>
        </Alert>
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          Bulk template: match products by <code>sku</code> first, then <code>part_number</code>, then a unique{' '}
          <code>sales_model</code> + <code>model_name</code> pair. Percent fields accept decimals 0–1 (e.g. 0.15) or percent
          points 1–100 (e.g. 15); values between 1 and 100 are divided by 100. Optional columns{' '}
          <code>notes</code>, <code>source_reference</code>, <code>valid_from</code>, <code>valid_to</code> are ignored for
          persistence.
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
          <Button
            size="small"
            variant="outlined"
            data-testid="sku-economics-download-template"
            onClick={() =>
              void apiDownloadBlob('/api/v1/commercial-planner/sku-assumptions/import-template', 'sku_economics_template.csv')
            }
          >
            Download template
          </Button>
          <Button
            size="small"
            variant="outlined"
            data-testid="sku-economics-upload-trigger"
            disabled={previewSkuImport.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            Upload SKU economics file
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = '';
              if (!f) return;
              lastImportFileRef.current = f;
              setImportFileLabel(f.name);
              previewSkuImport.mutate(f);
            }}
          />
          {importFileLabel ? (
            <Typography variant="caption" color="text.secondary">
              Selected: {importFileLabel}
            </Typography>
          ) : null}
        </Stack>
        {previewSkuImport.isError ? (
          <Alert severity="error" sx={{ mb: 1 }}>
            Preview failed: {previewSkuImport.error instanceof Error ? previewSkuImport.error.message : 'Unknown error'}
          </Alert>
        ) : null}
        {importApplySummary ? (
          <Alert
            severity="success"
            sx={{ mb: 1 }}
            onClose={() => setImportApplySummary(null)}
            data-testid="sku-import-apply-summary"
          >
            Applied: {importApplySummary.applied_creates} created, {importApplySummary.applied_updates} updated.
          </Alert>
        ) : null}
        {importPreview?.parse_errors?.length ? (
          <Alert severity="error" sx={{ mb: 1 }}>
            {importPreview.parse_errors.map((err) => (
              <Typography key={err} variant="caption" display="block">
                {err}
              </Typography>
            ))}
          </Alert>
        ) : null}
        {importPreview && !importPreview.parse_errors.length ? (
          <Stack spacing={1} sx={{ mb: 1 }}>
            <Typography variant="body2" color="text.secondary">
              Preview: {importPreview.summary.creates} create(s), {importPreview.summary.updates} update(s),{' '}
              {importPreview.summary.blocking_errors} blocking error(s).
            </Typography>
            <FormControlLabel
              control={
                <Checkbox
                  checked={importConfirm}
                  onChange={(e) => setImportConfirm(e.target.checked)}
                  disabled={!importPreview.can_apply || applySkuImport.isPending}
                  data-testid="sku-import-confirm-checkbox"
                />
              }
              label="I confirm applying these SKU economics changes to the database."
            />
            <Button
              size="small"
              variant="contained"
              color="primary"
              data-testid="sku-import-apply-btn"
              disabled={
                !importPreview.can_apply ||
                !importConfirm ||
                applySkuImport.isPending ||
                !lastImportFileRef.current
              }
              onClick={() => {
                const f = lastImportFileRef.current;
                if (f) applySkuImport.mutate(f);
              }}
            >
              Apply import
            </Button>
            {applySkuImport.isError ? (
              <Alert severity="error">
                Apply failed: {applySkuImport.error instanceof Error ? applySkuImport.error.message : ''}
              </Alert>
            ) : null}
            <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell>Row</TableCell>
                    <TableCell>Product</TableCell>
                    <TableCell>Match</TableCell>
                    <TableCell>Current CC</TableCell>
                    <TableCell>Proposed CC</TableCell>
                    <TableCell>FX</TableCell>
                    <TableCell>VAT</TableCell>
                    <TableCell>Reserves</TableCell>
                    <TableCell>Action</TableCell>
                    <TableCell>Messages</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {importPreview.rows.map((r) => (
                    <TableRow key={r.source_row}>
                      <TableCell>{r.source_row}</TableCell>
                      <TableCell>{`${r.product_sku || r.sku || '—'} — ${r.product_name || ''}`}</TableCell>
                      <TableCell>{r.match_method ?? '—'}</TableCell>
                      <TableCell>
                        {r.current
                          ? `${String(r.current.controlled_cost_amount)} ${String(r.current.controlled_cost_currency_code)}`
                          : '—'}
                      </TableCell>
                      <TableCell>
                        {r.proposed
                          ? `${String(r.proposed.controlled_cost_amount)} ${String(r.proposed.controlled_cost_currency_code)}`
                          : '—'}
                      </TableCell>
                      <TableCell>{r.proposed ? String(r.proposed.fx_plan_currency_per_cost_currency) : '—'}</TableCell>
                      <TableCell>{r.proposed ? String(r.proposed.vat_rate_pct) : '—'}</TableCell>
                      <TableCell>
                        {r.proposed
                          ? `${String(r.proposed.reserve_total_pct)} / ${String(r.proposed.promo_reserve_split_pct)}`
                          : '—'}
                      </TableCell>
                      <TableCell>{r.action}</TableCell>
                      <TableCell>{r.messages.join('; ') || '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Stack>
        ) : null}
        <TextField size="small" label="Filter" value={skuQ} onChange={(e) => setSkuQ(e.target.value)} sx={{ mb: 1, minWidth: 240 }} />
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Product</TableCell>
              <TableCell>PM bottom / controlled cost (amount + ccy)</TableCell>
              <TableCell>VAT (0–1)</TableCell>
              <TableCell>FX (plan per 1 cost ccy)</TableCell>
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
                  <TableCell>
                    {r.controlled_cost_amount} {(r.controlled_cost_currency_code || 'USD').trim()}
                  </TableCell>
                  <TableCell>{r.vat_rate_pct}</TableCell>
                  <TableCell>{r.fx_plan_currency_per_cost_currency}</TableCell>
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
            <Typography variant="body2" color="text.secondary">
              <strong>Controlled cost / PM bottom</strong> is the internal SKU cost basis for economics — not from DAP
              or lineup, and not logistics-inclusive landed cost.
            </Typography>
            <TextField
              label="Controlled cost amount (>0)"
              value={controlledCost}
              onChange={(e) => setControlledCost(e.target.value)}
            />
            <FormControl fullWidth data-testid="planner-defaults-sku-ccy-select">
              <InputLabel id="planner-sku-ccy-label">Controlled cost currency</InputLabel>
              <Select
                labelId="planner-sku-ccy-label"
                label="Controlled cost currency"
                value={skuCcySelect}
                onChange={(e) => setSkuCcySelect(String(e.target.value))}
              >
                {COMMON_SKU_COST_ISO_CODES.map((c) => (
                  <MenuItem key={c} value={c}>
                    {c}
                  </MenuItem>
                ))}
                <MenuItem value={SKU_COST_CURRENCY_OTHER}>Other (enter ISO code)</MenuItem>
              </Select>
            </FormControl>
            {skuCcySelect === SKU_COST_CURRENCY_OTHER ? (
              <TextField
                label="Other ISO currency code"
                value={skuCcyOther}
                onChange={(e) => setSkuCcyOther(e.target.value.toUpperCase())}
                inputProps={{ maxLength: 8 }}
              />
            ) : null}
            <TextField label="VAT rate (0–1)" value={vat} onChange={(e) => setVat(e.target.value)} />
            <TextField label={skuFxLabel} value={fx} onChange={(e) => setFx(e.target.value)} />
            <Typography variant="caption" color="text.secondary" display="block">
              {planCurrencyHint
                ? `Example: if plan currency is ${planCurrencyHint} and controlled cost is ${resolvedSkuCcy}, enter ${planCurrencyHint} per 1 ${resolvedSkuCcy}.`
                : 'Plan currency hint uses the first commercial plan in this workspace when available.'}
            </Typography>
            <Alert severity="info" sx={{ py: 0.5 }} data-testid="planner-defaults-fx-manual-notice">
              <Typography variant="caption" component="div">
                FX is manually entered and locked on this assumption until you change it. Latest-rate automation will
                require an FX provider and an explicit accept/lock step — not silent refresh on every visit.
              </Typography>
            </Alert>
            <TextField label="Reserve total (0–1)" value={resTot} onChange={(e) => setResTot(e.target.value)} />
            <TextField
              label="Campaign / support reserve split (0–1)"
              value={resSplit}
              onChange={(e) => setResSplit(e.target.value)}
            />
            {skuValidationErrors.length ? (
              <Alert severity="warning" data-testid="planner-defaults-sku-validation">
                {skuValidationErrors.map((e) => (
                  <Typography key={e} variant="caption" display="block">
                    {e}
                  </Typography>
                ))}
              </Alert>
            ) : null}
            {saveSku.isError ? <Alert severity="error">Save failed. Check values and duplicates.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSkuDlg(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!skuPick || saveSku.isPending || skuValidationErrors.length > 0}
            onClick={() => void saveSku.mutateAsync().catch(() => undefined)}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
