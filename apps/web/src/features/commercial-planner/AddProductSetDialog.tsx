'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  Step,
  StepLabel,
  Stepper,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useState } from 'react';

import { apiPost } from '@/lib/api';
import { EntitySearchAutocomplete } from './EntitySearchAutocomplete';
import { ProductPickerDialog } from './ProductPickerDialog';
import type { ProductPick } from './ProductPickerDialog';

// ── Types ─────────────────────────────────────────────────────────────────────

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };

type PlanLine = {
  customer_id: number;
  distributor_id: number;
  product_id: number;
};

type RowDraft = ProductPick & {
  units: string;
  srp: string;
  isDuplicate: boolean;
};

export type AddProductSetDialogProps = {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  activePlanId: number | null;
  existingLines: PlanLine[];
};

const STEPS = ['Customer & defaults', 'Select products', 'Preview', 'Create'];

// ── Main component ────────────────────────────────────────────────────────────

export function AddProductSetDialog({
  open,
  onClose,
  onCreated,
  activePlanId,
  existingLines,
}: AddProductSetDialogProps) {
  const [step, setStep] = useState(0);

  // Step 1
  const [customer, setCustomer] = useState<CustomerPick | null>(null);
  const [distributor, setDistributor] = useState<DistributorPick | null>(null);
  const [defaultUnits, setDefaultUnits] = useState('0');
  const [defaultSrp, setDefaultSrp] = useState('');
  const [defaultPromoMix, setDefaultPromoMix] = useState('0.5');

  // Step 2
  const [pickerOpen, setPickerOpen] = useState(false);
  const [selectedProducts, setSelectedProducts] = useState<ProductPick[]>([]);

  // Step 3
  const [rowDrafts, setRowDrafts] = useState<RowDraft[]>([]);

  // Step 4
  const [creating, setCreating] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [summaryError, setSummaryError] = useState(false);

  const reset = () => {
    setStep(0);
    setCustomer(null);
    setDistributor(null);
    setDefaultUnits('0');
    setDefaultSrp('');
    setDefaultPromoMix('0.5');
    setSelectedProducts([]);
    setRowDrafts([]);
    setSummary(null);
    setSummaryError(false);
    setCreating(false);
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  // Build duplicate key set from existing lines
  const dupKeySet = new Set(
    existingLines.map((l) => `${l.customer_id}|${l.distributor_id}|${l.product_id}`)
  );

  const handleProductsSelected = (products: ProductPick[]) => {
    setSelectedProducts(products);
  };

  const buildRowDrafts = () => {
    if (!customer || !distributor) return;
    const drafts: RowDraft[] = selectedProducts.map((p) => ({
      ...p,
      units: defaultUnits,
      srp: defaultSrp,
      isDuplicate: dupKeySet.has(`${customer.id}|${distributor.id}|${p.id}`),
    }));
    setRowDrafts(drafts);
    setStep(2);
  };

  const updateRow = (idx: number, field: 'units' | 'srp', value: string) => {
    setRowDrafts((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], [field]: value };
      return next;
    });
  };

  const handleCreate = async () => {
    if (!activePlanId || !customer || !distributor) return;
    setCreating(true);
    setSummary(null);
    let created = 0;
    let skipped = 0;
    let failed = 0;

    const promoMix = parseFloat(defaultPromoMix) || 0.5;

    for (const row of rowDrafts) {
      if (row.isDuplicate) {
        skipped++;
        continue;
      }
      const units = parseFloat(row.units);
      if (!Number.isFinite(units) || units <= 0) {
        skipped++;
        continue;
      }
      const body: Record<string, unknown> = {
        customer_id: customer.id,
        distributor_id: distributor.id,
        product_id: row.id,
        target_units: units,
        target_srp_local: 0,
        promo_mix_pct: promoMix,
      };
      const srp = parseFloat(row.srp);
      if (Number.isFinite(srp) && srp > 0) {
        body.target_srp_local = srp;
      }
      try {
        await apiPost(`/api/v1/commercial-planner/plans/${activePlanId}/lines`, body);
        created++;
      } catch {
        failed++;
      }
    }

    setSummary(`Created ${created}, skipped ${skipped} duplicates, failed ${failed}.`);
    setSummaryError(failed > 0);
    setCreating(false);
    setStep(3);
    if (created > 0) onCreated();
  };

  const canProceedStep1 = customer != null && distributor != null;
  const canProceedStep2 = selectedProducts.length > 0;

  return (
    <>
      <Dialog open={open} onClose={handleClose} fullWidth maxWidth="lg" aria-labelledby="add-product-set-title">
        <DialogTitle id="add-product-set-title">Add product set</DialogTitle>
        <DialogContent dividers>
          <Stepper activeStep={step} sx={{ mb: 3 }}>
            {STEPS.map((label) => (
              <Step key={label}>
                <StepLabel>{label}</StepLabel>
              </Step>
            ))}
          </Stepper>

          {/* Step 0: Customer & defaults */}
          {step === 0 && (
            <Stack spacing={2}>
              <Typography variant="subtitle2">Select customer and distributor</Typography>
              <EntitySearchAutocomplete<CustomerPick>
                label="Customer"
                fetchOptions={async (q, signal) => {
                  const { apiGet } = await import('@/lib/api');
                  const res = await apiGet<{ items: CustomerPick[] }>(
                    `/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                    { signal }
                  );
                  return res.items;
                }}
                getOptionLabel={(o) => `${o.customer_code} — ${o.customer_name}`}
                value={customer}
                onChange={setCustomer}
              />
              <EntitySearchAutocomplete<DistributorPick>
                label="Distributor"
                fetchOptions={async (q, signal) => {
                  const { apiGet } = await import('@/lib/api');
                  const res = await apiGet<{ items: DistributorPick[] }>(
                    `/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(q)}`,
                    { signal }
                  );
                  return res.items;
                }}
                getOptionLabel={(o) => `${o.distributor_code} — ${o.distributor_name}`}
                value={distributor}
                onChange={setDistributor}
              />
              <Divider />
              <Typography variant="subtitle2">Batch defaults</Typography>
              <Stack direction="row" spacing={2}>
                <TextField
                  label="Default units"
                  size="small"
                  type="number"
                  value={defaultUnits}
                  onChange={(e) => setDefaultUnits(e.target.value)}
                  helperText="Applied to each line; edit per-row in preview"
                  sx={{ width: 160 }}
                />
                <TextField
                  label="Default target SRP (local)"
                  size="small"
                  type="number"
                  value={defaultSrp}
                  onChange={(e) => setDefaultSrp(e.target.value)}
                  helperText="Optional — leave blank to set to 0"
                  sx={{ width: 220 }}
                />
                <TextField
                  label="Promo mix"
                  size="small"
                  type="number"
                  value={defaultPromoMix}
                  onChange={(e) => setDefaultPromoMix(e.target.value)}
                  helperText="0.0–1.0 (0.5 = 50%)"
                  sx={{ width: 140 }}
                />
              </Stack>
            </Stack>
          )}

          {/* Step 1: Product picker (shown via nested dialog) */}
          {step === 1 && (
            <Stack spacing={2} alignItems="flex-start">
              <Typography variant="body2" color="text.secondary">
                Use the product picker to select one or more products.
              </Typography>
              <Button
                variant="outlined"
                onClick={() => setPickerOpen(true)}
                data-testid="open-product-picker-btn"
              >
                Open product picker
              </Button>
              {selectedProducts.length > 0 && (
                <Typography variant="body2">
                  {selectedProducts.length} product{selectedProducts.length === 1 ? '' : 's'} selected.
                </Typography>
              )}
            </Stack>
          )}

          {/* Step 2: Preview */}
          {step === 2 && (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Preview — edit units and SRP per row if needed
              </Typography>
              {rowDrafts.some((r) => r.isDuplicate) && (
                <Alert severity="warning" sx={{ mb: 1 }}>
                  Some rows already exist in the plan and will be skipped.
                </Alert>
              )}
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>SKU</TableCell>
                      <TableCell>Part #</TableCell>
                      <TableCell>Sales model</TableCell>
                      <TableCell>Units</TableCell>
                      <TableCell>Target SRP</TableCell>
                      <TableCell>Status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {rowDrafts.map((row, idx) => (
                      <TableRow key={row.id} selected={row.isDuplicate}>
                        <TableCell>
                          <Typography variant="body2" fontFamily="monospace">
                            {row.sku || '—'}
                          </Typography>
                        </TableCell>
                        <TableCell>{row.part_number || '—'}</TableCell>
                        <TableCell>{row.sales_model_name || row.model_name || '—'}</TableCell>
                        <TableCell>
                          {row.isDuplicate ? (
                            <Typography variant="body2" color="text.disabled">
                              {row.units}
                            </Typography>
                          ) : (
                            <TextField
                              size="small"
                              type="number"
                              value={row.units}
                              onChange={(e) => updateRow(idx, 'units', e.target.value)}
                              sx={{ width: 100 }}
                            />
                          )}
                        </TableCell>
                        <TableCell>
                          {row.isDuplicate ? (
                            <Typography variant="body2" color="text.disabled">
                              {row.srp || '—'}
                            </Typography>
                          ) : (
                            <TextField
                              size="small"
                              type="number"
                              value={row.srp}
                              onChange={(e) => updateRow(idx, 'srp', e.target.value)}
                              sx={{ width: 120 }}
                            />
                          )}
                        </TableCell>
                        <TableCell>
                          {row.isDuplicate ? (
                            <Chip label="Duplicate — will skip" size="small" color="warning" />
                          ) : (
                            <Chip label="Will create" size="small" color="success" />
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </Box>
          )}

          {/* Step 3: Done */}
          {step === 3 && (
            <Box>
              {summary && (
                <Alert severity={summaryError ? 'warning' : 'success'} sx={{ mb: 2 }}>
                  {summary}
                </Alert>
              )}
              <Button variant="outlined" onClick={handleClose}>
                Close
              </Button>
            </Box>
          )}
        </DialogContent>

        <DialogActions>
          {step < 3 && (
            <>
              <Button size="small" onClick={handleClose}>
                Cancel
              </Button>
              <Box flex={1} />
              {step > 0 && (
                <Button
                  size="small"
                  onClick={() => setStep((s) => s - 1)}
                  disabled={creating}
                >
                  Back
                </Button>
              )}
              {step === 0 && (
                <Button
                  size="small"
                  variant="contained"
                  disabled={!canProceedStep1}
                  onClick={() => setStep(1)}
                  data-testid="add-product-set-next-step1"
                >
                  Next: Select products
                </Button>
              )}
              {step === 1 && (
                <Button
                  size="small"
                  variant="contained"
                  disabled={!canProceedStep2}
                  onClick={buildRowDrafts}
                  data-testid="add-product-set-next-step2"
                >
                  Next: Preview
                </Button>
              )}
              {step === 2 && (
                <Button
                  size="small"
                  variant="contained"
                  onClick={handleCreate}
                  disabled={creating || rowDrafts.every((r) => r.isDuplicate)}
                  data-testid="add-product-set-create"
                  startIcon={creating ? <CircularProgress size={14} /> : undefined}
                >
                  {creating ? 'Creating…' : 'Create lines'}
                </Button>
              )}
            </>
          )}
        </DialogActions>
      </Dialog>

      {/* Nested product picker dialog */}
      <ProductPickerDialog
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={handleProductsSelected}
        multiSelect
        title="Select products for batch add"
      />
    </>
  );
}
