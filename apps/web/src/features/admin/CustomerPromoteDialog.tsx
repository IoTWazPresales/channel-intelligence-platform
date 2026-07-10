'use client';

import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { apiPost, safeDisplayError } from '@/lib/api';

export type CustomerPromoteTarget = {
  id: number;
  customer_code: string;
  customer_name: string;
  customer_status: string;
};

type PreviewResponse = {
  dry_run: boolean;
  applied: boolean;
  can_confirm: boolean;
  customer_id: number;
  new_code: string;
  promote_target_status: string;
  eligibility: {
    eligible: boolean;
    reasons: string[];
    admin_mint_edge: boolean;
    old_code: string;
    old_status: string | null;
  };
  collision: {
    customer_id: number;
    code: string;
    customer_status: string | null;
    merged_into_customer_id: number | null;
    note?: string;
  } | null;
  warnings: string[];
};

type ConfirmResponse = {
  applied: boolean;
  customer_id: number;
  old_code: string;
  new_code: string;
  old_status: string | null;
  new_status: string;
  promoted_at: string;
  warnings?: string[];
};

type Props = {
  open: boolean;
  customer: CustomerPromoteTarget | null;
  onClose: () => void;
};

function isTmpCust(code: string): boolean {
  return code.trim().toUpperCase().startsWith('TMP-CUST-');
}

export function customerPromoteActionVisible(row: {
  customer_code: string;
  merged_into_customer_id?: number | null;
}): boolean {
  if (row.merged_into_customer_id != null) return false;
  return isTmpCust(row.customer_code || '');
}

export function CustomerPromoteDialog({ open, customer, onClose }: Props) {
  const qc = useQueryClient();
  const [newCode, setNewCode] = useState('');
  const [note, setNote] = useState('');
  const [ack, setAck] = useState(false);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<ConfirmResponse | null>(null);

  useEffect(() => {
    if (!open) return;
    setNewCode('');
    setNote('');
    setAck(false);
    setPreview(null);
    setError(null);
    setSuccess(null);
  }, [open, customer?.id]);

  const previewMut = useMutation({
    mutationFn: async () => {
      if (!customer) throw new Error('No customer');
      const code = newCode.trim();
      if (!code) throw new Error('New business code is required');
      if (isTmpCust(code)) throw new Error('New code must be a real business code, not TMP-CUST-*');
      return apiPost<PreviewResponse>(`/api/v1/customers/${customer.id}/promote`, {
        new_code: code,
        confirm: false,
        note: note.trim() || undefined,
      });
    },
    onSuccess: (data) => {
      setPreview(data);
      setError(null);
      setAck(false);
    },
    onError: (err) => {
      setPreview(null);
      setError(safeDisplayError(err));
    },
  });

  const confirmMut = useMutation({
    mutationFn: async () => {
      if (!customer) throw new Error('No customer');
      return apiPost<ConfirmResponse>(`/api/v1/customers/${customer.id}/promote`, {
        new_code: newCode.trim(),
        confirm: true,
        note: note.trim() || undefined,
      });
    },
    onSuccess: (data) => {
      setSuccess(data);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['customers'] });
      void qc.invalidateQueries({ queryKey: ['admin-customers'] });
    },
    onError: (err) => setError(safeDisplayError(err)),
  });

  const canConfirm =
    Boolean(preview?.can_confirm) && ack && !confirmMut.isPending && !success;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="customer-promote-dialog">
      <DialogTitle>Promote provisional customer</DialogTitle>
      <DialogContent dividers>
        {!customer ? null : (
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <Typography variant="body2">
              {customer.customer_name} · <strong>{customer.customer_code}</strong> · status{' '}
              {customer.customer_status}
            </Typography>
            <TextField
              label="New business code"
              value={newCode}
              onChange={(e) => {
                setNewCode(e.target.value);
                setPreview(null);
                setAck(false);
              }}
              required
              fullWidth
              inputProps={{ maxLength: 64, 'data-testid': 'promote-new-code' }}
              helperText="Same customer id — reassigns code only. Not TMP-CUST-*."
            />
            <TextField
              label="Steward note (optional)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              fullWidth
              multiline
              minRows={2}
              inputProps={{ maxLength: 512, 'data-testid': 'promote-note' }}
            />

            {error ? (
              <Alert severity="error" data-testid="promote-error">
                {error}
              </Alert>
            ) : null}

            {success ? (
              <Alert severity="success" data-testid="promote-success">
                Promoted {success.old_code} → {success.new_code} (status {success.new_status})
              </Alert>
            ) : null}

            {preview && !success ? (
              <Stack spacing={1} data-testid="promote-preview">
                <Typography variant="subtitle2">
                  Preview · target status {preview.promote_target_status} · can_confirm=
                  {String(preview.can_confirm)}
                </Typography>
                {!preview.eligibility.eligible ? (
                  <Alert severity="warning" data-testid="promote-ineligible">
                    Not eligible: {(preview.eligibility.reasons || []).join(', ') || 'unknown'}
                  </Alert>
                ) : null}
                {preview.collision ? (
                  <Alert severity="error" data-testid="promote-collision">
                    Code collision with customer #{preview.collision.customer_id} (
                    {preview.collision.code}, status {preview.collision.customer_status}).
                    {preview.collision.note ? ` ${preview.collision.note}` : ''}
                  </Alert>
                ) : null}
                {(preview.warnings || []).map((w) => (
                  <Alert key={w} severity="warning" data-testid="promote-warning">
                    {w}
                  </Alert>
                ))}
                {preview.eligibility.admin_mint_edge ? (
                  <Alert severity="info" data-testid="promote-admin-mint-edge">
                    Admin-mint edge: this TMP row is already status=active. Confirm carefully.
                  </Alert>
                ) : null}
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={ack}
                      onChange={(e) => setAck(e.target.checked)}
                      disabled={!preview.can_confirm}
                      data-testid="promote-ack"
                    />
                  }
                  label="I understand the old TMP code is retired and future imports using it may mint a duplicate"
                />
              </Stack>
            ) : null}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{success ? 'Close' : 'Cancel'}</Button>
        {!success ? (
          <>
            <Button
              onClick={() => previewMut.mutate()}
              disabled={!newCode.trim() || previewMut.isPending}
              data-testid="promote-preview-btn"
            >
              {previewMut.isPending ? 'Previewing…' : 'Preview'}
            </Button>
            <Button
              variant="contained"
              disabled={!canConfirm}
              onClick={() => confirmMut.mutate()}
              data-testid="promote-confirm-btn"
            >
              {confirmMut.isPending ? 'Promoting…' : 'Confirm promote'}
            </Button>
          </>
        ) : null}
      </DialogActions>
    </Dialog>
  );
}
