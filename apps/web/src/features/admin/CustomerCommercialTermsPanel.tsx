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
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { apiGet, apiPatch, apiPost } from '@/lib/api';

export type CustomerTermRow = {
  id: number;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  customer_margin_pct: number;
  customer_rebate_pct: number;
};

type Props = {
  customerId: number;
  customerCode: string;
};

export function CustomerCommercialTermsPanel({ customerId, customerCode }: Props) {
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['commercial-planner', 'customer-terms', 'by-customer', customerId],
    queryFn: ({ signal }) =>
      apiGet<CustomerTermRow[]>(`/api/v1/commercial-planner/customer-terms?customer_id=${customerId}`, { signal }),
    enabled: customerId > 0,
  });

  const term = data?.length === 1 ? data[0] : undefined;

  const [dlgOpen, setDlgOpen] = useState(false);
  const [margin, setMargin] = useState('0.12');
  const [rebate, setRebate] = useState('0.03');

  useEffect(() => {
    if (term) {
      setMargin(String(term.customer_margin_pct));
      setRebate(String(term.customer_rebate_pct));
    } else {
      setMargin('0.12');
      setRebate('0.03');
    }
  }, [term]);

  const save = useMutation({
    mutationFn: async () => {
      const m = Number(margin);
      const r = Number(rebate);
      if (term) {
        return apiPatch<CustomerTermRow>(`/api/v1/commercial-planner/customer-terms/${term.id}`, {
          customer_margin_pct: m,
          customer_rebate_pct: r,
        });
      }
      return apiPost<CustomerTermRow>('/api/v1/commercial-planner/customer-terms', {
        customer_id: customerId,
        customer_margin_pct: m,
        customer_rebate_pct: r,
      });
    },
    onSuccess: async () => {
      setDlgOpen(false);
      await qc.invalidateQueries({ queryKey: ['commercial-planner', 'customer-terms'] });
      await refetch();
    },
  });

  return (
    <Paper variant="outlined" sx={{ p: 1.25, mb: 1.5 }} data-testid="customer-commercial-terms-panel">
      <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
        Commercial terms
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        These defaults feed Commercial Planner economics. Plan-line overrides may still be applied later. Configure on
        this page or bulk edit in Commercial Planner → Planner defaults.
      </Typography>
      {isLoading ? (
        <Typography variant="body2" color="text.secondary">
          Loading commercial terms…
        </Typography>
      ) : isError ? (
        <Alert severity="error">{String((error as Error)?.message ?? 'Failed to load terms')}</Alert>
      ) : !term ? (
        <Stack spacing={1}>
          <Typography variant="body2" color="text.secondary" data-testid="customer-terms-empty">
            No commercial terms configured for this customer.
          </Typography>
          <Button size="small" variant="outlined" onClick={() => setDlgOpen(true)} data-testid="customer-terms-create">
            Create commercial terms
          </Button>
        </Stack>
      ) : (
        <Stack spacing={1}>
          <Typography variant="body2">
            <strong>Customer margin %:</strong> {(term.customer_margin_pct * 100).toFixed(2)}%
          </Typography>
          <Typography variant="body2">
            <strong>Customer rebate / support %:</strong> {(term.customer_rebate_pct * 100).toFixed(2)}%
          </Typography>
          <Button size="small" variant="outlined" onClick={() => setDlgOpen(true)} data-testid="customer-terms-edit">
            Edit commercial terms
          </Button>
        </Stack>
      )}

      <Dialog open={dlgOpen} onClose={() => !save.isPending && setDlgOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{term ? 'Edit commercial terms' : 'Create commercial terms'}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Customer: {customerCode} (id {customerId})
            </Typography>
            <TextField
              label="Customer margin (decimal, e.g. 0.12 for 12%)"
              value={margin}
              onChange={(e) => setMargin(e.target.value)}
              size="small"
              fullWidth
            />
            <TextField
              label="Customer rebate / support (decimal)"
              value={rebate}
              onChange={(e) => setRebate(e.target.value)}
              size="small"
              fullWidth
            />
            {save.isError ? <Alert severity="error">Save failed. Check values (margin + rebate must stay below 0.92).</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlgOpen(false)} disabled={save.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={save.isPending || !Number.isFinite(Number(margin)) || !Number.isFinite(Number(rebate))}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
