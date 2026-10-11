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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { useMemo, useState } from 'react';

import { BulkPasteDialog } from '@/components/BulkPasteDialog';
import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { FactColumnPicker, FactColumnsButton } from '@/features/workbench-ui/FactColumnPicker';
import { ScopeBar } from '@/features/workbench-ui/controls';
import { factGridLayout, useFactGridChrome } from '@/features/workbench-ui/gridFind';
import { useFactColumns } from '@/features/workbench-ui/useFactColumns';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type PriceRow = {
  id: number;
  sku: string | null;
  sales_model_name: string | null;
  net_price: number;
  list_price: number;
  effective_date: string;
};

const LINE_IDENTITY = { sku: 'sku', salesModel: 'sales_model_name' } as const;
const PINNED_LEFT: Partial<ColDef<PriceRow>> = { pinned: 'left' };

type PricingPasteRow = {
  sku: string;
  net_price: number;
  list_price: number;
  effective_date: string;
  currency?: string;
  customer_code?: string;
  channel_code?: string;
};

function parsePricingPaste(text: string): PricingPasteRow[] {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (!lines.length) return [];
  const first = lines[0].toLowerCase();
  const hasHeader = first.includes('sku') && (first.includes('net') || first.includes('list'));
  const dataLines = hasHeader ? lines.slice(1) : lines;
  const rows: PricingPasteRow[] = [];
  for (const line of dataLines) {
    const parts = line.split(/[,\t]/).map((p) => p.trim().replace(/^"|"$/g, ''));
    if (parts.length < 4) continue;
    const [sku, netS, listS, eff, cur, cust, ch] = parts;
    if (!sku) continue;
    const net_price = Number(netS);
    const list_price = Number(listS);
    if (!Number.isFinite(net_price) || !Number.isFinite(list_price)) continue;
    const o: PricingPasteRow = { sku, net_price, list_price, effective_date: eff };
    if (cur) o.currency = cur;
    if (cust) o.customer_code = cust;
    if (ch) o.channel_code = ch;
    rows.push(o);
  }
  return rows;
}

export default function PricingPage() {
  const qc = useQueryClient();
  const factFields = useFactColumns<PriceRow>('pricing.facts', {
    lineIdentifier: LINE_IDENTITY,
    lineIdentifierColDef: PINNED_LEFT,
  });
  const [pasteOpen, setPasteOpen] = useState(false);
  const [paste, setPaste] = useState('');
  const [addOpen, setAddOpen] = useState(false);
  const [addSku, setAddSku] = useState('');
  const [addNet, setAddNet] = useState('');
  const [addList, setAddList] = useState('');
  const [addEff, setAddEff] = useState(() => new Date().toISOString().slice(0, 10));
  const [addCur, setAddCur] = useState('USD');
  const [addCust, setAddCust] = useState('');
  const [addCh, setAddCh] = useState('');
  const [queueNote, setQueueNote] = useState<string | null>(null);

  const {
    data: facts,
    isLoading: factsLoading,
    isError: factsIsError,
    error: factsError,
    refetch: refetchFacts,
  } = useQuery({
    queryKey: ['pricing-facts'],
    queryFn: ({ signal }) => apiGet<PriceRow[]>('/api/v1/pricing/facts', { signal }),
  });
  const factChrome = useFactGridChrome('pricing.facts', {
    exportDisabled: (facts?.length ?? 0) === 0,
    layout: factGridLayout(factFields),
  });
  const bulkFacts = useMutation({
    mutationFn: (rows: PricingPasteRow[]) =>
      apiPost<{ created: number; queued_skus?: string[] }>('/api/v1/pricing/facts/bulk', { rows }),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['pricing-facts'] });
      const queued = res.queued_skus ?? [];
      const listed = queued.join(', ');
      setQueueNote(
        queued.length === 0
          ? null
          : queued.length === 1
            ? `${listed} is not in the product master. It is on the product catalogue gaps queue. No product was created.`
            : `${listed} are not in the product master. They are on the product catalogue gaps queue. No product was created.`,
      );
      setPasteOpen(false);
      setPaste('');
    },
  });

  const addFact = useMutation({
    mutationFn: () =>
      apiPost<{ id: number }>('/api/v1/pricing/facts', {
        sku: addSku.trim(),
        net_price: Number(addNet),
        list_price: Number(addList),
        effective_date: addEff.trim(),
        currency: addCur.trim() || 'USD',
        customer_code: addCust.trim() || undefined,
        channel_code: addCh.trim() || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pricing-facts'] });
      setAddOpen(false);
      setAddSku('');
      setAddNet('');
      setAddList('');
      setAddEff(new Date().toISOString().slice(0, 10));
      setAddCur('USD');
      setAddCust('');
      setAddCh('');
    },
  });

  const delFact = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/pricing/facts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pricing-facts'] }),
  });
  const clearFacts = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/pricing/facts/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pricing-facts'] }),
  });
  const factCols: ColDef<PriceRow>[] = useMemo(() => {
    const busyDel = delFact.isPending || clearFacts.isPending;
    return [
      ...factFields.identityColDefs,
      { field: 'net_price', headerName: 'Net', type: 'numericColumn' },
      { field: 'list_price', headerName: 'List', type: 'numericColumn' },
      { field: 'effective_date', headerName: 'Effective' },
      ...factFields.optionalColDefs,
      gridDeleteColumn<PriceRow>((id) => void delFact.mutate(id), { busy: busyDel }),
    ];
  }, [delFact, delFact.isPending, clearFacts.isPending, factFields.identityColDefs, factFields.optionalColDefs]);

  const factRows = facts ?? [];

  const busyFacts = bulkFacts.isPending || addFact.isPending || delFact.isPending || clearFacts.isPending;

  return (
    <>
      <PageHeader crumbs={[{ label: 'Planning' }, { label: 'Recorded prices' }]} title="Recorded prices" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1, maxWidth: 900 }}>
        List and net prices are kept here. A SKU that is not in the product master goes to product catalogue gaps.
        No product is created from a price.
      </Typography>
      {queueNote ? (
        <Alert severity="warning" sx={{ mb: 1 }} data-testid="pricing-unknown-sku">
          {queueNote}
        </Alert>
      ) : null}
      <Paper sx={{ p: 2 }}>
          <ScopeBar
            chips={[]}
            savedViews={factChrome.viewNames}
            savedView={factChrome.active}
            onSavedView={factChrome.selectView}
            filters={factChrome.filters}
            trailing={
              <>
              {factChrome.trailing}
              <FactColumnsButton
                gridId="pricing.facts"
                onClick={factFields.openPicker}
                count={factFields.optionalFields.length}
              />
              </>
            }
          />
          <ModuleDataSection
            intro="Paste or add list and net prices per SKU. Optional customer and channel codes. An unknown SKU is queued for the product catalogue and does not create a product."
            isLoading={factsLoading}
            isError={factsIsError}
            error={toQueryError(factsError)}
            onRetry={() => void refetchFacts()}
            isEmpty={factRows.length === 0}
            empty={{
              title: 'No recorded prices',
              description: 'Use Add row or Paste upload to record a price, or load a file through Import Center.',
              primary: { label: 'Import Center', href: '/admin/imports' },
              secondary: { label: 'Attention', href: '/brief' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['pricing-facts'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every price fact? This cannot be undone.')) return;
                  void clearFacts.mutate();
                }}
                onAdd={() => setAddOpen(true)}
                onUpload={() => setPasteOpen(true)}
                importsHref="/admin/imports"
                busy={busyFacts}
              />
            }
          >
            <EnterpriseDataGrid ref={factChrome.gridRef} quickFilterText={factChrome.query} rowData={factRows} columnDefs={factCols} />
          </ModuleDataSection>
      </Paper>
      <FactColumnPicker {...factFields.pickerProps} />

      <BulkPasteDialog
        open={pasteOpen}
        title="Paste price facts"
        hint={
          <>
            Columns: <code>sku, net_price, list_price, effective_date</code> plus optional{' '}
            <code>currency, customer_code, channel_code</code>. Tab or comma separated. Example:{' '}
            <code>SKU-001,169.99,199.99,2026-04-12,USD,CUST-1001,RET</code>
          </>
        }
        placeholder="sku,net_price,list_price,effective_date,currency,customer_code,channel_code"
        value={paste}
        onChange={setPaste}
        onClose={() => !bulkFacts.isPending && setPasteOpen(false)}
        onSubmit={() => bulkFacts.mutate(parsePricingPaste(paste))}
        busy={bulkFacts.isPending}
        error={bulkFacts.error as Error | null}
      />

      <Dialog open={addOpen} onClose={() => !addFact.isPending && setAddOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Add price fact</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField label="SKU" required value={addSku} onChange={(e) => setAddSku(e.target.value)} fullWidth />
            <TextField label="Net price" required type="number" value={addNet} onChange={(e) => setAddNet(e.target.value)} fullWidth />
            <TextField label="List price" required type="number" value={addList} onChange={(e) => setAddList(e.target.value)} fullWidth />
            <TextField label="Effective date" required type="date" value={addEff} onChange={(e) => setAddEff(e.target.value)} fullWidth InputLabelProps={{ shrink: true }} />
            <TextField label="Currency" value={addCur} onChange={(e) => setAddCur(e.target.value)} fullWidth />
            <TextField label="Customer code (optional)" value={addCust} onChange={(e) => setAddCust(e.target.value)} fullWidth />
            <TextField label="Channel code (optional)" value={addCh} onChange={(e) => setAddCh(e.target.value)} fullWidth />
            {addFact.isError ? (
              <Alert severity="warning" data-testid="pricing-add-unknown-sku">
                {toQueryError(addFact.error)?.message}
              </Alert>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)} disabled={addFact.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={
              addFact.isPending ||
              !addSku.trim() ||
              !addNet.trim() ||
              !addList.trim() ||
              !Number.isFinite(Number(addNet)) ||
              !Number.isFinite(Number(addList))
            }
            onClick={() => addFact.mutate()}
          >
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
