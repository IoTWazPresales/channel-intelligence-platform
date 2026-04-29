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
import { useEffect, useState } from 'react';

import { apiGet, apiPatch, apiPost } from '@/lib/api';

export type DistributorTermRow = {
  id: number;
  distributor_id: number;
  distributor_code: string;
  distributor_name: string;
  distributor_margin_pct: number;
};

type Props = {
  distributorId: number;
  distributorCode: string;
};

export function DistributorCommercialTermsPanel({ distributorId, distributorCode }: Props) {
  const qc = useQueryClient();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['commercial-planner', 'distributor-terms', 'by-distributor', distributorId],
    queryFn: ({ signal }) =>
      apiGet<DistributorTermRow[]>(`/api/v1/commercial-planner/distributor-terms?distributor_id=${distributorId}`, {
        signal,
      }),
    enabled: distributorId > 0,
  });

  const term = data?.length === 1 ? data[0] : undefined;
  const [dlgOpen, setDlgOpen] = useState(false);
  const [margin, setMargin] = useState('0.08');

  useEffect(() => {
    if (term) setMargin(String(term.distributor_margin_pct));
    else setMargin('0.08');
  }, [term]);

  const save = useMutation({
    mutationFn: async () => {
      const m = Number(margin);
      if (term) {
        return apiPatch<DistributorTermRow>(`/api/v1/commercial-planner/distributor-terms/${term.id}`, {
          distributor_margin_pct: m,
        });
      }
      return apiPost<DistributorTermRow>('/api/v1/commercial-planner/distributor-terms', {
        distributor_id: distributorId,
        distributor_margin_pct: m,
      });
    },
    onSuccess: async () => {
      setDlgOpen(false);
      await qc.invalidateQueries({ queryKey: ['commercial-planner', 'distributor-terms'] });
      await refetch();
    },
  });

  return (
    <Paper variant="outlined" sx={{ p: 1.25, mb: 1.25 }} data-testid="distributor-commercial-terms-panel">
      <Typography variant="subtitle2" sx={{ mb: 0.75 }}>
        Commercial terms
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        This default feeds Commercial Planner economics. Plan-line overrides may still be applied later. Configure on
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
          <Typography variant="body2" color="text.secondary" data-testid="distributor-terms-empty">
            No commercial terms configured for this distributor.
          </Typography>
          <Button size="small" variant="outlined" onClick={() => setDlgOpen(true)} data-testid="distributor-terms-create">
            Create commercial terms
          </Button>
        </Stack>
      ) : (
        <Stack spacing={1}>
          <Typography variant="body2">
            <strong>Distributor margin %:</strong> {(term.distributor_margin_pct * 100).toFixed(2)}%
          </Typography>
          <Button size="small" variant="outlined" onClick={() => setDlgOpen(true)} data-testid="distributor-terms-edit">
            Edit commercial terms
          </Button>
        </Stack>
      )}

      <Dialog open={dlgOpen} onClose={() => !save.isPending && setDlgOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{term ? 'Edit commercial terms' : 'Create commercial terms'}</DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <Typography variant="caption" color="text.secondary">
              Distributor: {distributorCode} (id {distributorId})
            </Typography>
            <TextField
              label="Distributor margin (decimal, e.g. 0.08 for 8%)"
              value={margin}
              onChange={(e) => setMargin(e.target.value)}
              size="small"
              fullWidth
            />
            {save.isError ? <Alert severity="error">Save failed. Check the margin value.</Alert> : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlgOpen(false)} disabled={save.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            disabled={save.isPending || !Number.isFinite(Number(margin))}
            onClick={() => save.mutate()}
          >
            {save.isPending ? 'Saving…' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
