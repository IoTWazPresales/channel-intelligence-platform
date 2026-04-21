'use client';

import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  Tab,
  Tabs,
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
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';

type PriceRow = {
  id: number;
  sku: string | null;
  net_price: number;
  list_price: number;
  effective_date: string;
};

type RecRow = {
  id: number;
  sku: string | null;
  suggested_state: string;
  explanation_summary: string | null;
  confidence: string | null;
};

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
  const [tab, setTab] = useState(0);
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
  const {
    data: recs,
    isLoading: recsLoading,
    isError: recsIsError,
    error: recsError,
    refetch: refetchRecs,
  } = useQuery({
    queryKey: ['pricing-recs'],
    queryFn: ({ signal }) => apiGet<RecRow[]>('/api/v1/pricing/recommendations', { signal }),
  });

  const bulkFacts = useMutation({
    mutationFn: (rows: PricingPasteRow[]) => apiPost<{ created: number }>('/api/v1/pricing/facts/bulk', { rows }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pricing-facts'] });
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
  const delRec = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/pricing/recommendations/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pricing-recs'] }),
  });
  const clearRecs = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/pricing/recommendations/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['pricing-recs'] }),
  });

  const factCols: ColDef<PriceRow>[] = useMemo(() => {
    const busyDel = delFact.isPending || clearFacts.isPending;
    return [
      { field: 'sku', headerName: 'SKU', pinned: 'left' },
      { field: 'net_price', headerName: 'Net', type: 'numericColumn' },
      { field: 'list_price', headerName: 'List', type: 'numericColumn' },
      { field: 'effective_date', headerName: 'Effective' },
      gridDeleteColumn<PriceRow>((id) => void delFact.mutate(id), { busy: busyDel }),
    ];
  }, [delFact, delFact.isPending, clearFacts.isPending]);

  const recCols: ColDef<RecRow>[] = useMemo(() => {
    const busyDel = delRec.isPending || clearRecs.isPending;
    return [
      { field: 'sku', headerName: 'SKU' },
      { field: 'suggested_state', headerName: 'State' },
      { field: 'explanation_summary', headerName: 'Explanation', flex: 1, minWidth: 240 },
      { field: 'confidence', headerName: 'Confidence' },
      gridDeleteColumn<RecRow>((id) => void delRec.mutate(id), { busy: busyDel }),
    ];
  }, [delRec, delRec.isPending, clearRecs.isPending]);

  const factRows = facts ?? [];
  const recRows = recs ?? [];

  const busyFacts = bulkFacts.isPending || addFact.isPending || delFact.isPending || clearFacts.isPending;
  const busyRecs = delRec.isPending || clearRecs.isPending;

  return (
    <>
      <PageHeader crumbs={[{ label: 'Pricing' }]} title="Pricing & support" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1, maxWidth: 900 }}>
        <strong>Price facts</strong> are stored in <code>fact_pricing</code>. <strong>Recommendations</strong> are derived
        when the planning service has run against upstream facts.
      </Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Price facts" />
        <Tab label="Rule-based recommendations" />
      </Tabs>
      <Paper sx={{ p: 2 }}>
        {tab === 0 ? (
          <ModuleDataSection
            intro="Paste or add list/net prices per SKU (optional customer and channel codes). Unknown SKUs create placeholder products."
            isLoading={factsLoading}
            isError={factsIsError}
            error={toQueryError(factsError)}
            onRetry={() => void refetchFacts()}
            isEmpty={factRows.length === 0}
            empty={{
              title: 'No price facts',
              description: 'Use Add row or Paste upload to create price facts, or load data through Data & imports.',
              primary: { label: 'Data & imports', href: '/admin/imports' },
              secondary: { label: 'Getting started', href: '/getting-started' },
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
            <EnterpriseDataGrid rowData={factRows} columnDefs={factCols} />
          </ModuleDataSection>
        ) : (
          <ModuleDataSection
            intro="Recommendations appear when the planning service has evaluated pricing against stock and competitor context."
            isLoading={recsLoading}
            isError={recsIsError}
            error={toQueryError(recsError)}
            onRetry={() => void refetchRecs()}
            isEmpty={recRows.length === 0}
            empty={{
              title: 'No pricing recommendations',
              description: 'Populate upstream facts (inventory, pricing, competition) and refresh.',
              primary: { label: 'Inventory', href: '/inventory' },
              secondary: { label: 'Getting started', href: '/getting-started' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['pricing-recs'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every pricing recommendation row? This cannot be undone.')) return;
                  void clearRecs.mutate();
                }}
                clearAllLabel="Clear all recommendations"
                importsHref="/admin/imports"
                busy={busyRecs}
              />
            }
          >
            <EnterpriseDataGrid rowData={recRows} columnDefs={recCols} />
          </ModuleDataSection>
        )}
      </Paper>

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
