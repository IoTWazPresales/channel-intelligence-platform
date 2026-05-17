'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Drawer,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { CellValueChangedEvent, ColDef, GridOptions } from 'ag-grid-community';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { PageHeader } from '@/components/PageHeader';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { apiDelete, apiGet, apiPatch, apiPost } from '@/lib/api';

type ListingRow = {
  id: number;
  product_sku: string;
  product_name: string;
  retailer: string;
  listing_url: string | null;
  expected_price: number | null;
  last_price_seen: number | null;
  availability: string;
  status: string;
  data_unavailable?: boolean;
};

type ListingsResponse = {
  items: ListingRow[];
  total: number;
  data_unavailable?: boolean;
};

type ListingDraft = {
  product_sku: string;
  product_name: string;
  retailer: string;
  listing_url: string;
  expected_price: string;
  last_price_seen: string;
  availability: string;
  status: string;
};

const EMPTY_DRAFT: ListingDraft = {
  product_sku: '',
  product_name: '',
  retailer: '',
  listing_url: '',
  expected_price: '',
  last_price_seen: '',
  availability: 'unknown',
  status: 'active',
};

function availabilityChipColor(a: string): 'success' | 'warning' | 'error' | 'default' {
  switch (a.toLowerCase()) {
    case 'in_stock':
    case 'in stock':
      return 'success';
    case 'low_stock':
    case 'low stock':
      return 'warning';
    case 'out_of_stock':
    case 'out of stock':
      return 'error';
    default:
      return 'default';
  }
}

export default function RetailerListingsPage() {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [draft, setDraft] = useState<ListingDraft>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [drawerRow, setDrawerRow] = useState<ListingRow | null>(null);

  const {
    data: listingsData,
    isLoading,
  } = useQuery({
    queryKey: ['retailer-listings'],
    queryFn: ({ signal }) => apiGet<ListingsResponse>('/api/v1/retailer-listings', { signal }),
  });

  const dataUnavailable = listingsData?.data_unavailable === true;
  const rows = listingsData?.items ?? [];

  const createListing = useMutation({
    mutationFn: () =>
      apiPost<ListingRow>('/api/v1/retailer-listings', {
        product_sku: draft.product_sku.trim(),
        product_name: draft.product_name.trim(),
        retailer: draft.retailer.trim(),
        listing_url: draft.listing_url.trim() || null,
        expected_price: draft.expected_price.trim() ? Number(draft.expected_price) : null,
        last_price_seen: draft.last_price_seen.trim() ? Number(draft.last_price_seen) : null,
        availability: draft.availability,
        status: draft.status,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['retailer-listings'] });
      setAddOpen(false);
      setDraft(EMPTY_DRAFT);
      setEditingId(null);
    },
  });

  const patchListing = useMutation({
    mutationFn: (id: number) =>
      apiPatch<ListingRow>(`/api/v1/retailer-listings/${id}`, {
        product_sku: draft.product_sku.trim(),
        product_name: draft.product_name.trim(),
        retailer: draft.retailer.trim(),
        listing_url: draft.listing_url.trim() || null,
        expected_price: draft.expected_price.trim() ? Number(draft.expected_price) : null,
        last_price_seen: draft.last_price_seen.trim() ? Number(draft.last_price_seen) : null,
        availability: draft.availability,
        status: draft.status,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['retailer-listings'] });
      setAddOpen(false);
      setDraft(EMPTY_DRAFT);
      setEditingId(null);
    },
  });

  const delListing = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/retailer-listings/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['retailer-listings'] }),
  });

  const onCellEdit = useCallback(
    async (e: CellValueChangedEvent<ListingRow>) => {
      const id = e.data?.id;
      const field = e.colDef.field;
      if (id == null || !field || e.oldValue === e.newValue) return;
      try {
        await apiPatch(`/api/v1/retailer-listings/${id}`, { [field]: e.newValue });
        await qc.invalidateQueries({ queryKey: ['retailer-listings'] });
      } catch (err) {
        console.error(err);
        await qc.invalidateQueries({ queryKey: ['retailer-listings'] });
      }
    },
    [qc],
  );

  const cols: ColDef<ListingRow>[] = useMemo(
    () => [
      { field: 'product_sku', headerName: 'Product SKU', minWidth: 130, editable: false },
      { field: 'product_name', headerName: 'Product Name', flex: 1, minWidth: 200, editable: true },
      { field: 'retailer', headerName: 'Retailer', minWidth: 150, editable: true },
      { field: 'listing_url', headerName: 'Listing URL', minWidth: 220, editable: true },
      {
        field: 'expected_price',
        headerName: 'Expected Price',
        minWidth: 130,
        type: 'numericColumn',
        editable: true,
      },
      {
        field: 'last_price_seen',
        headerName: 'Last Price Seen',
        minWidth: 140,
        type: 'numericColumn',
        editable: true,
      },
      {
        field: 'availability',
        headerName: 'Availability',
        minWidth: 130,
        editable: false,
        cellRenderer: ({ value }: { value: string }) => (
          <Chip size="small" label={value} color={availabilityChipColor(value)} />
        ),
      },
      { field: 'status', headerName: 'Status', minWidth: 100, editable: false },
      {
        headerName: '',
        colId: '__detail',
        minWidth: 90,
        editable: false,
        sortable: false,
        filter: false,
        cellRenderer: ({ data }: { data: ListingRow }) =>
          data ? (
            <Button size="small" onClick={() => setDrawerRow(data)}>
              Open
            </Button>
          ) : null,
      },
      gridDeleteColumn<ListingRow>((id) => void delListing.mutate(id), { busy: delListing.isPending }),
    ],
    [delListing],
  );

  const gridOptions: GridOptions<ListingRow> = useMemo(
    () => ({ singleClickEdit: true, onCellValueChanged: onCellEdit }),
    [onCellEdit],
  );

  const openEdit = (row: ListingRow) => {
    setEditingId(row.id);
    setDraft({
      product_sku: row.product_sku,
      product_name: row.product_name,
      retailer: row.retailer,
      listing_url: row.listing_url ?? '',
      expected_price: row.expected_price != null ? String(row.expected_price) : '',
      last_price_seen: row.last_price_seen != null ? String(row.last_price_seen) : '',
      availability: row.availability,
      status: row.status,
    });
    setAddOpen(true);
  };

  const isMutating = createListing.isPending || patchListing.isPending;

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Products', href: '/admin/products' }, { label: 'Retailer listings' }]}
        title="Retailer listings"
      />

      {dataUnavailable ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          The <strong>retailer_listings</strong> table needs to be migrated before data is available. This page will
          populate automatically once the migration is complete.
        </Alert>
      ) : null}

      <Stack direction="row" spacing={1} sx={{ mb: 1.5 }}>
        <Button
          variant="contained"
          onClick={() => {
            setEditingId(null);
            setDraft(EMPTY_DRAFT);
            setAddOpen(true);
          }}
        >
          Add listing
        </Button>
      </Stack>

      <Paper sx={{ p: 2 }}>
        {isLoading ? (
          <Typography color="text.secondary">Loading listings…</Typography>
        ) : (
          <>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {rows.length} listing{rows.length !== 1 ? 's' : ''}
            </Typography>
            <EnterpriseDataGrid rowData={rows} columnDefs={cols} gridOptions={gridOptions} height={480} />
          </>
        )}
      </Paper>

      <Dialog
        open={addOpen}
        onClose={() => !isMutating && setAddOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{editingId ? 'Edit listing' : 'New listing'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Product SKU"
              value={draft.product_sku}
              onChange={(e) => setDraft((p) => ({ ...p, product_sku: e.target.value }))}
              required
              disabled={editingId != null}
            />
            <TextField
              label="Product name"
              value={draft.product_name}
              onChange={(e) => setDraft((p) => ({ ...p, product_name: e.target.value }))}
              required
            />
            <TextField
              label="Retailer"
              value={draft.retailer}
              onChange={(e) => setDraft((p) => ({ ...p, retailer: e.target.value }))}
              required
            />
            <TextField
              label="Listing URL"
              value={draft.listing_url}
              onChange={(e) => setDraft((p) => ({ ...p, listing_url: e.target.value }))}
            />
            <TextField
              label="Expected price"
              type="number"
              value={draft.expected_price}
              onChange={(e) => setDraft((p) => ({ ...p, expected_price: e.target.value }))}
            />
            <TextField
              label="Last price seen"
              type="number"
              value={draft.last_price_seen}
              onChange={(e) => setDraft((p) => ({ ...p, last_price_seen: e.target.value }))}
            />
            <TextField
              label="Availability"
              value={draft.availability}
              onChange={(e) => setDraft((p) => ({ ...p, availability: e.target.value }))}
            />
            <TextField
              label="Status"
              value={draft.status}
              onChange={(e) => setDraft((p) => ({ ...p, status: e.target.value }))}
            />
          </Stack>
          {createListing.isError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {(createListing.error as Error).message}
            </Alert>
          ) : null}
          {patchListing.isError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {(patchListing.error as Error).message}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddOpen(false)} disabled={isMutating}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={isMutating || !draft.product_sku.trim() || !draft.product_name.trim() || !draft.retailer.trim()}
            onClick={() => {
              if (editingId) {
                patchListing.mutate(editingId);
              } else {
                createListing.mutate();
              }
            }}
          >
            {editingId ? 'Save' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      <Drawer anchor="right" open={Boolean(drawerRow)} onClose={() => setDrawerRow(null)}>
        <Box sx={{ width: 420, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1.5 }}>
            Listing details
          </Typography>
          {drawerRow ? (
            <Stack spacing={1.5}>
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2">Product</Typography>
                <Typography variant="body2">
                  <strong>SKU:</strong> {drawerRow.product_sku}
                </Typography>
                <Typography variant="body2">
                  <strong>Name:</strong> {drawerRow.product_name}
                </Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2">Retailer</Typography>
                <Typography variant="body2">{drawerRow.retailer}</Typography>
                {drawerRow.listing_url ? (
                  <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                    <strong>URL:</strong> {drawerRow.listing_url}
                  </Typography>
                ) : null}
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2">Pricing</Typography>
                <Typography variant="body2">
                  <strong>Expected:</strong>{' '}
                  {drawerRow.expected_price != null ? drawerRow.expected_price.toLocaleString() : '—'}
                </Typography>
                <Typography variant="body2">
                  <strong>Last seen:</strong>{' '}
                  {drawerRow.last_price_seen != null ? drawerRow.last_price_seen.toLocaleString() : '—'}
                </Typography>
              </Paper>
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2">Status</Typography>
                <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                  <Chip size="small" label={drawerRow.availability} color={availabilityChipColor(drawerRow.availability)} />
                  <Chip size="small" label={drawerRow.status} variant="outlined" />
                </Stack>
              </Paper>
              <Stack direction="row" spacing={1}>
                <Button size="small" variant="outlined" onClick={() => openEdit(drawerRow)}>
                  Edit
                </Button>
                <Button
                  size="small"
                  color="error"
                  onClick={() => {
                    if (window.confirm('Delete this listing?')) {
                      delListing.mutate(drawerRow.id);
                      setDrawerRow(null);
                    }
                  }}
                >
                  Delete
                </Button>
              </Stack>
            </Stack>
          ) : null}
        </Box>
      </Drawer>
    </>
  );
}
