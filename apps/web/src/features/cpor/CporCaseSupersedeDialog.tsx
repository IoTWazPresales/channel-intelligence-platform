'use client';

import {
  Alert,
  Autocomplete,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';

type CaseOption = {
  id: number;
  case_code: string;
  case_name: string | null;
  status: string;
  window_start: string | null;
  window_end: string | null;
  superseded_by_case_id?: number | null;
};

type SupersedePreview = {
  loser: { id: number; case_code: string; status: string; line_count: number };
  winner: { id: number; case_code: string; status: string; line_count: number };
  already_superseded: boolean;
  blockers: { code: string; message: string }[];
  warnings: { code: string; message: string }[];
  effects: string[];
};

type Props = {
  open: boolean;
  onClose: () => void;
  caseId: number;
  caseCode: string;
  customerId: number | null | undefined;
  onSuperseded?: () => void | Promise<void>;
};

function optionLabel(c: CaseOption): string {
  const name = c.case_name ? ` · ${c.case_name}` : '';
  const win = c.window_start || c.window_end ? ` · ${c.window_start ?? '…'} → ${c.window_end ?? '…'}` : '';
  return `${c.case_code}${name} · ${c.status}${win}`;
}

/**
 * BACKLOG-138 — preview → confirm writer for `cpor_case.superseded_by_case_id`.
 * Pointer-only: status is never changed here; readers filter `IS NULL`.
 */
export function CporCaseSupersedeDialog({ open, onClose, caseId, caseCode, customerId, onSuperseded }: Props) {
  const qc = useQueryClient();
  const [winner, setWinner] = useState<CaseOption | null>(null);
  const [reason, setReason] = useState('');

  useEffect(() => {
    if (!open) {
      setWinner(null);
      setReason('');
    }
  }, [open]);

  const candidates = useQuery({
    queryKey: ['cpor', 'cases', 'supersede-candidates', customerId ?? 'all'],
    enabled: open,
    queryFn: () =>
      apiGet<CaseOption[]>(
        customerId != null ? `/api/v1/cpor/cases?customer_id=${customerId}&test_data=all` : '/api/v1/cpor/cases?test_data=all'
      ),
  });

  const preview = useQuery({
    queryKey: ['cpor', 'case', caseId, 'supersede-preview', winner?.id ?? null],
    enabled: open && winner != null,
    queryFn: () =>
      apiPost<SupersedePreview>(`/api/v1/cpor/cases/${caseId}/supersede/preview`, {
        winner_case_id: winner!.id,
      }),
  });

  const confirm = useMutation({
    mutationFn: () =>
      apiPost(`/api/v1/cpor/cases/${caseId}/supersede`, {
        winner_case_id: winner!.id,
        confirm: true,
        reason: reason.trim() || null,
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['cpor', 'case', caseId] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', 'book'] });
      await onSuperseded?.();
      onClose();
    },
  });

  const options = (candidates.data ?? []).filter(
    (c) => c.id !== caseId && c.superseded_by_case_id == null && c.status !== 'cancelled' && c.status !== 'rejected'
  );
  const blocked = (preview.data?.blockers.length ?? 0) > 0;
  const canConfirm = winner != null && preview.isSuccess && !blocked && !preview.data?.already_superseded;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="cpor-supersede-dialog">
      <DialogTitle>Supersede {caseCode}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            Point this case at its replacement. Nothing is deleted and the lifecycle status stays as it is; the
            case drops out of the settlement book, owed/paid recon, norms, comparables and promo-plan drafts.
            Reversible.
          </Typography>
          <Autocomplete
            options={options}
            value={winner}
            onChange={(_e, v) => setWinner(v)}
            getOptionLabel={optionLabel}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            loading={candidates.isLoading}
            noOptionsText={customerId != null ? 'No other live cases for this customer' : 'No live cases'}
            renderInput={(params) => (
              <TextField
                {...params}
                size="small"
                label="Replacement case"
                inputProps={{ ...params.inputProps, 'data-testid': 'cpor-supersede-winner-input' }}
              />
            )}
          />
          <TextField
            size="small"
            label="Reason (optional)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            inputProps={{ 'data-testid': 'cpor-supersede-reason' }}
          />
          {preview.isError ? (
            <Alert severity="error">{String((preview.error as Error)?.message ?? 'Preview failed')}</Alert>
          ) : null}
          {preview.data ? (
            <Stack spacing={1} data-testid="cpor-supersede-preview">
              {preview.data.already_superseded ? (
                <Alert severity="info">Already superseded by {preview.data.winner.case_code}.</Alert>
              ) : null}
              {preview.data.blockers.map((b) => (
                <Alert key={b.code} severity="error" data-testid={`cpor-supersede-blocker-${b.code}`}>
                  {b.message}
                </Alert>
              ))}
              {preview.data.warnings.map((w) => (
                <Alert key={w.code} severity="warning" data-testid={`cpor-supersede-warning-${w.code}`}>
                  {w.message}
                </Alert>
              ))}
              <Typography variant="caption" color="text.secondary">
                {preview.data.loser.case_code} ({preview.data.loser.line_count} lines, {preview.data.loser.status}) →{' '}
                {preview.data.winner.case_code} ({preview.data.winner.line_count} lines, {preview.data.winner.status})
              </Typography>
            </Stack>
          ) : null}
          {confirm.isError ? (
            <Alert severity="error">{String((confirm.error as Error)?.message ?? 'Supersede failed')}</Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={confirm.isPending}>
          Cancel
        </Button>
        <Button
          variant="contained"
          color="warning"
          disabled={!canConfirm || confirm.isPending || preview.isFetching}
          onClick={() => confirm.mutate()}
          data-testid="cpor-supersede-confirm"
        >
          {confirm.isPending ? 'Superseding…' : 'Confirm supersede'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
