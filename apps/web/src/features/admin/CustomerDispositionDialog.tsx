'use client';

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { apiPost, safeDisplayError } from '@/lib/api';

type Disposition = 'parked' | 'excluded' | 'clear';

type RowResult = {
  customer_id: number | null;
  tmp_code: string | null;
  status: string;
  reasons: string[];
  outcome?: string | null;
  no_code_disposition?: string | null;
};

type BatchResponse = {
  dry_run: boolean;
  disposition: Disposition;
  rows: RowResult[];
  summary: { ready: number; applied: number; blocked: number; skipped: number; total: number };
};

type Props = {
  open: boolean;
  onClose: () => void;
  customerIds: number[];
};

export function CustomerDispositionDialog({ open, onClose, customerIds }: Props) {
  const qc = useQueryClient();
  const [disposition, setDisposition] = useState<Disposition>('parked');
  const [note, setNote] = useState('');
  const [step, setStep] = useState<'input' | 'preview' | 'result'>('input');
  const [preview, setPreview] = useState<BatchResponse | null>(null);
  const [result, setResult] = useState<BatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setDisposition('parked');
    setNote('');
    setStep('input');
    setPreview(null);
    setResult(null);
    setError(null);
  }, [open]);

  const previewMut = useMutation({
    mutationFn: async () => {
      if (!customerIds.length) throw new Error('Select at least one customer');
      if (customerIds.length > 500) throw new Error('Max 500 per batch');
      return apiPost<BatchResponse>('/api/v1/customers/disposition/batch', {
        customer_ids: customerIds,
        disposition,
        note: note.trim() || undefined,
        dry_run: true,
      });
    },
    onSuccess: (data) => {
      setPreview(data);
      setResult(null);
      setError(null);
      setStep('preview');
    },
    onError: (err) => setError(safeDisplayError(err)),
  });

  const confirmMut = useMutation({
    mutationFn: async () =>
      apiPost<BatchResponse>('/api/v1/customers/disposition/batch', {
        customer_ids: customerIds,
        disposition,
        note: note.trim() || undefined,
        dry_run: false,
      }),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      setStep('result');
      void qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
    onError: (err) => setError(safeDisplayError(err)),
  });

  const displayRows = result?.rows ?? preview?.rows ?? [];
  const readyN = preview?.summary.ready ?? 0;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth data-testid="customer-disposition-dialog">
      <DialogTitle>Park / exclude provisional customers</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Typography variant="body2" color="text.secondary">
            Marks TMP rows that should not receive a permanent code. Does not change customer
            status (provisional reuse stays intact). {customerIds.length} selected.
          </Typography>
          {step === 'input' ? (
            <>
              <FormControl>
                <RadioGroup
                  value={disposition}
                  onChange={(e) => setDisposition(e.target.value as Disposition)}
                  data-testid="disposition-radio"
                >
                  <FormControlLabel value="parked" control={<Radio />} label="Parked (defer decision)" />
                  <FormControlLabel value="excluded" control={<Radio />} label="Excluded (never mint)" />
                  <FormControlLabel value="clear" control={<Radio />} label="Clear disposition" />
                </RadioGroup>
              </FormControl>
              <TextField
                label="Note (optional)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                fullWidth
                inputProps={{ 'data-testid': 'disposition-note' }}
              />
            </>
          ) : null}
          {error ? (
            <Alert severity="error" data-testid="disposition-error">
              {error}
            </Alert>
          ) : null}
          {(step === 'preview' || step === 'result') && displayRows.length ? (
            <Stack spacing={1} data-testid={step === 'result' ? 'disposition-result' : 'disposition-preview'}>
              <Typography variant="subtitle2">
                {step === 'result' ? 'Result' : 'Preview'} · ready {preview?.summary.ready ?? 0} ·
                blocked {result?.summary.blocked ?? preview?.summary.blocked ?? 0} · skipped{' '}
                {result?.summary.skipped ?? preview?.summary.skipped ?? 0}
                {step === 'result' ? ` · applied ${result?.summary.applied ?? 0}` : ''}
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>TMP code</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Reasons</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {displayRows.map((r, i) => (
                    <TableRow key={`${r.customer_id}-${i}`}>
                      <TableCell>{r.customer_id ?? '—'}</TableCell>
                      <TableCell>{r.tmp_code || '—'}</TableCell>
                      <TableCell>{r.status}</TableCell>
                      <TableCell>{(r.reasons || []).join(', ') || '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Stack>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{step === 'result' ? 'Close' : 'Cancel'}</Button>
        {step === 'input' ? (
          <Button
            variant="contained"
            disabled={!customerIds.length || previewMut.isPending}
            onClick={() => previewMut.mutate()}
            data-testid="disposition-preview-btn"
          >
            {previewMut.isPending ? 'Previewing…' : 'Preview'}
          </Button>
        ) : null}
        {step === 'preview' ? (
          <>
            <Button onClick={() => { setStep('input'); setPreview(null); }}>Back</Button>
            <Button
              variant="contained"
              disabled={readyN === 0 || confirmMut.isPending}
              onClick={() => confirmMut.mutate()}
              data-testid="disposition-confirm-btn"
            >
              {confirmMut.isPending ? 'Applying…' : `Apply ${readyN} ready`}
            </Button>
          </>
        ) : null}
      </DialogActions>
    </Dialog>
  );
}
