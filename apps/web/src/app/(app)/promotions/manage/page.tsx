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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiGet, apiPost, apiPatch, apiDelete } from '@/lib/api';

type PromotionRow = {
  id: number;
  name: string;
  type: string;
  start_week: number;
  start_year: number;
  end_week: number;
  end_year: number;
  status: string;
  notes: string | null;
  product_count?: number;
  data_unavailable?: boolean;
};

type PromotionsResponse = {
  items: PromotionRow[];
  total: number;
  data_unavailable?: boolean;
};

type PromotionProduct = {
  id: number;
  product_sku: string;
  product_name: string;
};

type PromotionDraft = {
  name: string;
  type: string;
  start_week: string;
  start_year: string;
  end_week: string;
  end_year: string;
  status: string;
  notes: string;
};

const EMPTY_DRAFT: PromotionDraft = {
  name: '',
  type: 'discount',
  start_week: '',
  start_year: '',
  end_week: '',
  end_year: '',
  status: 'draft',
  notes: '',
};

const PROMO_TYPES = ['discount', 'bogo', 'bundle', 'rebate', 'seasonal', 'clearance', 'other'];
const PROMO_STATUSES = ['draft', 'planned', 'active', 'completed', 'cancelled'];

function statusChipColor(s: string): 'info' | 'warning' | 'success' | 'error' | 'default' {
  switch (s.toLowerCase()) {
    case 'draft':
      return 'default';
    case 'planned':
      return 'info';
    case 'active':
      return 'success';
    case 'completed':
      return 'warning';
    case 'cancelled':
      return 'error';
    default:
      return 'default';
  }
}

export default function PromotionManagePage() {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [draft, setDraft] = useState<PromotionDraft>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [drawerRow, setDrawerRow] = useState<PromotionRow | null>(null);

  const { data: promosData, isLoading } = useQuery({
    queryKey: ['promotions-manage'],
    queryFn: ({ signal }) => apiGet<PromotionsResponse>('/api/v1/promotions', { signal }),
  });

  const dataUnavailable = promosData?.data_unavailable === true;
  const rows = promosData?.items ?? [];

  const selectedPromoId = drawerRow?.id ?? null;
  const { data: promoProducts } = useQuery({
    queryKey: ['promotion-products', selectedPromoId],
    queryFn: ({ signal }) =>
      apiGet<{ items: PromotionProduct[] }>(`/api/v1/promotions/${selectedPromoId}/products`, { signal }),
    enabled: selectedPromoId != null,
  });

  const createPromo = useMutation({
    mutationFn: () =>
      apiPost<PromotionRow>('/api/v1/promotions', {
        name: draft.name.trim(),
        type: draft.type,
        start_week: draft.start_week ? Number(draft.start_week) : null,
        start_year: draft.start_year ? Number(draft.start_year) : null,
        end_week: draft.end_week ? Number(draft.end_week) : null,
        end_year: draft.end_year ? Number(draft.end_year) : null,
        status: draft.status,
        notes: draft.notes.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['promotions-manage'] });
      setCreateOpen(false);
      setDraft(EMPTY_DRAFT);
      setEditingId(null);
    },
  });

  const patchPromo = useMutation({
    mutationFn: (id: number) =>
      apiPatch<PromotionRow>(`/api/v1/promotions/${id}`, {
        name: draft.name.trim(),
        type: draft.type,
        start_week: draft.start_week ? Number(draft.start_week) : null,
        start_year: draft.start_year ? Number(draft.start_year) : null,
        end_week: draft.end_week ? Number(draft.end_week) : null,
        end_year: draft.end_year ? Number(draft.end_year) : null,
        status: draft.status,
        notes: draft.notes.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['promotions-manage'] });
      setCreateOpen(false);
      setDraft(EMPTY_DRAFT);
      setEditingId(null);
    },
  });

  const delPromo = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/promotions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['promotions-manage'] }),
  });

  const openEdit = (row: PromotionRow) => {
    setEditingId(row.id);
    setDraft({
      name: row.name,
      type: row.type,
      start_week: String(row.start_week),
      start_year: String(row.start_year),
      end_week: String(row.end_week),
      end_year: String(row.end_year),
      status: row.status,
      notes: row.notes ?? '',
    });
    setCreateOpen(true);
  };

  const isMutating = createPromo.isPending || patchPromo.isPending;

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Commercial' }, { label: 'Promotion planner' }]}
        title="Promotion planner"
      />

      {dataUnavailable ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          The <strong>dim_promotion</strong> table needs to be migrated before promotion data is available. This page
          will scaffold the UI; data will populate automatically once the migration is complete.
        </Alert>
      ) : (
        <Alert severity="info" sx={{ mb: 2 }}>
          Manage promotion periods and participating products. Linked to <strong>fact_promotion_plan</strong> and{' '}
          <strong>dim_promotion</strong>.
        </Alert>
      )}

      <Stack direction="row" spacing={1} sx={{ mb: 2 }}>
        <Button
          variant="contained"
          onClick={() => {
            setEditingId(null);
            setDraft(EMPTY_DRAFT);
            setCreateOpen(true);
          }}
        >
          Create promotion
        </Button>
      </Stack>

      <Paper variant="outlined">
        <Box sx={{ p: 2, overflowX: 'auto' }}>
          {isLoading ? (
            <Typography color="text.secondary">Loading promotions…</Typography>
          ) : rows.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              No promotions found. Create one to get started.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Name</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Start</TableCell>
                  <TableCell>End</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Products</TableCell>
                  <TableCell>Notes</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell>
                      <Button size="small" variant="text" onClick={() => setDrawerRow(row)}>
                        {row.name}
                      </Button>
                    </TableCell>
                    <TableCell>{row.type}</TableCell>
                    <TableCell>
                      W{row.start_week} / {row.start_year}
                    </TableCell>
                    <TableCell>
                      W{row.end_week} / {row.end_year}
                    </TableCell>
                    <TableCell>
                      <Chip size="small" label={row.status} color={statusChipColor(row.status)} />
                    </TableCell>
                    <TableCell>{row.product_count ?? '—'}</TableCell>
                    <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row.notes ?? '—'}
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.5}>
                        <Button size="small" onClick={() => openEdit(row)}>
                          Edit
                        </Button>
                        <Button
                          size="small"
                          color="error"
                          disabled={delPromo.isPending}
                          onClick={() => {
                            if (window.confirm('Delete this promotion?')) delPromo.mutate(row.id);
                          }}
                        >
                          Delete
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Box>
      </Paper>

      <Dialog
        open={createOpen}
        onClose={() => !isMutating && setCreateOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{editingId ? 'Edit promotion' : 'New promotion'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Promotion name"
              value={draft.name}
              onChange={(e) => setDraft((p) => ({ ...p, name: e.target.value }))}
              required
            />
            <FormControl fullWidth>
              <InputLabel id="promo-type">Type</InputLabel>
              <Select
                labelId="promo-type"
                label="Type"
                value={draft.type}
                onChange={(e) => setDraft((p) => ({ ...p, type: String(e.target.value) }))}
              >
                {PROMO_TYPES.map((t) => (
                  <MenuItem key={t} value={t}>
                    {t}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Stack direction="row" spacing={2}>
              <TextField
                label="Start week"
                type="number"
                value={draft.start_week}
                onChange={(e) => setDraft((p) => ({ ...p, start_week: e.target.value }))}
                sx={{ flex: 1 }}
              />
              <TextField
                label="Start year"
                type="number"
                value={draft.start_year}
                onChange={(e) => setDraft((p) => ({ ...p, start_year: e.target.value }))}
                sx={{ flex: 1 }}
              />
            </Stack>
            <Stack direction="row" spacing={2}>
              <TextField
                label="End week"
                type="number"
                value={draft.end_week}
                onChange={(e) => setDraft((p) => ({ ...p, end_week: e.target.value }))}
                sx={{ flex: 1 }}
              />
              <TextField
                label="End year"
                type="number"
                value={draft.end_year}
                onChange={(e) => setDraft((p) => ({ ...p, end_year: e.target.value }))}
                sx={{ flex: 1 }}
              />
            </Stack>
            <FormControl fullWidth>
              <InputLabel id="promo-status">Status</InputLabel>
              <Select
                labelId="promo-status"
                label="Status"
                value={draft.status}
                onChange={(e) => setDraft((p) => ({ ...p, status: String(e.target.value) }))}
              >
                {PROMO_STATUSES.map((s) => (
                  <MenuItem key={s} value={s}>
                    {s}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="Notes"
              multiline
              rows={3}
              value={draft.notes}
              onChange={(e) => setDraft((p) => ({ ...p, notes: e.target.value }))}
            />
          </Stack>
          {createPromo.isError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {(createPromo.error as Error).message}
            </Alert>
          ) : null}
          {patchPromo.isError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {(patchPromo.error as Error).message}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)} disabled={isMutating}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={isMutating || !draft.name.trim()}
            onClick={() => {
              if (editingId) {
                patchPromo.mutate(editingId);
              } else {
                createPromo.mutate();
              }
            }}
          >
            {editingId ? 'Save' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>

      <Drawer anchor="right" open={Boolean(drawerRow)} onClose={() => setDrawerRow(null)}>
        <Box sx={{ width: 440, p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1.5 }}>
            Promotion details
          </Typography>
          {drawerRow ? (
            <Stack spacing={1.5}>
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2">Overview</Typography>
                <Typography variant="body2">
                  <strong>Name:</strong> {drawerRow.name}
                </Typography>
                <Typography variant="body2">
                  <strong>Type:</strong> {drawerRow.type}
                </Typography>
                <Typography variant="body2">
                  <strong>Period:</strong> W{drawerRow.start_week}/{drawerRow.start_year} – W{drawerRow.end_week}/
                  {drawerRow.end_year}
                </Typography>
                <Chip
                  size="small"
                  label={drawerRow.status}
                  color={statusChipColor(drawerRow.status)}
                  sx={{ mt: 0.5 }}
                />
              </Paper>
              {drawerRow.notes ? (
                <Paper variant="outlined" sx={{ p: 1.25 }}>
                  <Typography variant="subtitle2">Notes</Typography>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                    {drawerRow.notes}
                  </Typography>
                </Paper>
              ) : null}
              <Paper variant="outlined" sx={{ p: 1.25 }}>
                <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
                  Participating products
                </Typography>
                {(promoProducts?.items ?? []).length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No products linked to this promotion yet.
                  </Typography>
                ) : (
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>SKU</TableCell>
                        <TableCell>Name</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(promoProducts?.items ?? []).map((p) => (
                        <TableRow key={p.id}>
                          <TableCell>{p.product_sku}</TableCell>
                          <TableCell>{p.product_name}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </Paper>
              <Stack direction="row" spacing={1}>
                <Button size="small" variant="outlined" onClick={() => openEdit(drawerRow)}>
                  Edit
                </Button>
                <Button
                  size="small"
                  color="error"
                  disabled={delPromo.isPending}
                  onClick={() => {
                    if (window.confirm('Delete this promotion?')) {
                      delPromo.mutate(drawerRow.id);
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
