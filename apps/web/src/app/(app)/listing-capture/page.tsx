'use client';

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import type { ColDef } from 'ag-grid-community';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useRef, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { PageHeader } from '@/components/PageHeader';
import { apiGet, apiPost, apiPostFormData } from '@/lib/api';

type Listing = {
  id: number;
  customer_id: number;
  product_id: number | null;
  url: string;
  marketplace: string;
  status: string;
  source: string;
  external_id: string | null;
};

type Proposal = {
  id: number;
  customer_id: number;
  marketplace: string;
  external_id: string;
  product_id: number | null;
  status: string;
};

export default function ListingCapturePage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState(0);
  const [open, setOpen] = useState(false);
  const [customerId, setCustomerId] = useState('1');
  const [url, setUrl] = useState('');
  const [marketplace, setMarketplace] = useState('takealot');
  const [productId, setProductId] = useState('');
  const [confirmUrl, setConfirmUrl] = useState('');
  const [confirmSeed, setConfirmSeed] = useState<Proposal | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['listing-capture', 'listings'],
    queryFn: ({ signal }) =>
      apiGet<{ items: Listing[]; total: number; data_unavailable?: boolean }>(
        '/api/v1/listing-capture/listings?page_size=200',
        { signal },
      ),
  });

  const { data: proposals, refetch: refetchProposals } = useQuery({
    queryKey: ['listing-capture', 'proposals'],
    queryFn: ({ signal }) =>
      apiGet<{ items: Proposal[] }>('/api/v1/listing-capture/proposals', { signal }),
    enabled: tab === 1,
  });

  const createMut = useMutation({
    mutationFn: () =>
      apiPost('/api/v1/listing-capture/listings', {
        customer_id: Number(customerId),
        url,
        marketplace,
        product_id: productId.trim() ? Number(productId) : null,
      }),
    onSuccess: async () => {
      setOpen(false);
      setUrl('');
      await qc.invalidateQueries({ queryKey: ['listing-capture', 'listings'] });
    },
  });

  const importMut = useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      return apiPostFormData<{ created: number; row_flags: unknown[] }>(
        '/api/v1/listing-capture/listings/import-csv',
        fd,
      );
    },
    onSuccess: async () => {
      await refetch();
    },
  });

  const confirmMut = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/listing-capture/proposals/${confirmSeed!.id}/confirm`, { url: confirmUrl }),
    onSuccess: async () => {
      setConfirmSeed(null);
      setConfirmUrl('');
      await refetch();
      await refetchProposals();
    },
  });

  const cols = useMemo<ColDef<Listing>[]>(
    () => [
      { field: 'id', width: 70 },
      { field: 'customer_id', headerName: 'Customer', width: 100 },
      { field: 'product_id', headerName: 'Product', width: 100 },
      { field: 'marketplace', width: 110 },
      { field: 'status', width: 120 },
      { field: 'source', width: 120 },
      { field: 'url', flex: 1, minWidth: 200 },
    ],
    [],
  );

  const proposalCols = useMemo<ColDef<Proposal>[]>(
    () => [
      { field: 'id', width: 70 },
      { field: 'customer_id', width: 100 },
      { field: 'marketplace', width: 110 },
      { field: 'external_id', headerName: 'External ID', flex: 1 },
      { field: 'product_id', width: 100 },
      {
        headerName: 'Action',
        width: 120,
        cellRenderer: (p: { data?: Proposal }) => (
          <Button size="small" onClick={() => p.data && setConfirmSeed(p.data)}>
            Confirm
          </Button>
        ),
      },
    ],
    [],
  );

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Channel Intelligence' }, { label: 'Listing Capture' }]}
        title="Listing Capture v0"
        action={
          <Stack direction="row" spacing={1}>
            <Button size="small" variant="outlined" onClick={() => refetch()}>
              Refresh
            </Button>
            <Button size="small" variant="contained" onClick={() => setOpen(true)}>
              Register URL
            </Button>
            <Button size="small" variant="outlined" onClick={() => fileRef.current?.click()}>
              Import CSV
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = '';
                if (f) importMut.mutate(f);
              }}
            />
          </Stack>
        }
      />
      <Alert severity="info" sx={{ mb: 2 }}>
        Capture-only registry. Poller is registered but gated off by default. No live HTTP in this unit.
        Migration `20260709_0069` must be applied by Warren before writes succeed on cip.
      </Alert>
      {data?.data_unavailable ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Listing tables unavailable (migration not applied yet). Read surfaces stay empty.
        </Alert>
      ) : null}
      <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 1 }}>
        <Tab label="Registry" />
        <Tab label="Feed proposals" />
      </Tabs>
      {isError ? <Alert severity="error">{String((error as Error)?.message)}</Alert> : null}
      {importMut.isSuccess ? (
        <Alert severity="success" sx={{ mb: 1 }}>
          Imported {importMut.data.created}; flagged rows: {importMut.data.row_flags?.length ?? 0}
        </Alert>
      ) : null}
      {tab === 0 ? (
        isLoading ? (
          <Typography>Loading…</Typography>
        ) : (
          <EnterpriseDataGrid
            rowData={data?.items ?? []}
            columnDefs={cols}
            height={480}
            gridOptions={{ getRowId: (p) => String(p.data.id) }}
          />
        )
      ) : (
        <EnterpriseDataGrid
          rowData={proposals?.items ?? []}
          columnDefs={proposalCols}
          height={480}
          gridOptions={{ getRowId: (p) => String(p.data.id) }}
        />
      )}

      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Register listing</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <TextField size="small" label="Customer id" value={customerId} onChange={(e) => setCustomerId(e.target.value)} />
            <TextField size="small" label="URL" value={url} onChange={(e) => setUrl(e.target.value)} fullWidth />
            <TextField size="small" label="Marketplace" value={marketplace} onChange={(e) => setMarketplace(e.target.value)} helperText="takealot | evetech" />
            <TextField size="small" label="Product id (optional)" value={productId} onChange={(e) => setProductId(e.target.value)} />
            {createMut.isError ? <Alert severity="error">{String((createMut.error as Error)?.message)}</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={!url.trim() || createMut.isPending} onClick={() => createMut.mutate()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!confirmSeed} onClose={() => setConfirmSeed(null)} fullWidth maxWidth="sm">
        <DialogTitle>Confirm feed proposal</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1 }}>
            {confirmSeed?.marketplace} · {confirmSeed?.external_id}
          </Typography>
          <TextField
            size="small"
            label="Listing URL"
            value={confirmUrl}
            onChange={(e) => setConfirmUrl(e.target.value)}
            fullWidth
          />
          {confirmMut.isError ? <Alert severity="error">{String((confirmMut.error as Error)?.message)}</Alert> : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmSeed(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!confirmUrl.trim() || confirmMut.isPending}
            onClick={() => confirmMut.mutate()}
          >
            Confirm → create listing
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
