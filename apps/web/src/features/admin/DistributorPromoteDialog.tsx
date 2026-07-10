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

export type DistributorPromoteTarget = {
  id: number;
  distributor_code: string;
  distributor_name: string;
};

type PreviewResponse = {
  dry_run: boolean;
  applied: boolean;
  can_confirm: boolean;
  distributor_id: number;
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
    distributor_id: number;
    code: string;
    distributor_status: string | null;
    note?: string;
  } | null;
  warnings: string[];
};

type ConfirmResponse = {
  applied: boolean;
  old_code: string;
  new_code: string;
  new_status: string;
};

type Props = {
  open: boolean;
  distributor: DistributorPromoteTarget | null;
  onClose: () => void;
};

function isTmpDist(code: string): boolean {
  return code.trim().toUpperCase().startsWith('TMP-DIST-');
}

export function distributorPromoteActionVisible(row: {
  distributor_code?: string;
  code?: string;
  merged_into_distributor_id?: number | null;
}): boolean {
  if (row.merged_into_distributor_id != null) return false;
  const code = row.distributor_code || row.code || '';
  return isTmpDist(code);
}

export function DistributorPromoteDialog({ open, distributor, onClose }: Props) {
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
  }, [open, distributor?.id]);

  const previewMut = useMutation({
    mutationFn: async () => {
      if (!distributor) throw new Error('No distributor');
      const code = newCode.trim();
      if (!code) throw new Error('New business code is required');
      if (isTmpDist(code)) throw new Error('New code must not be TMP-DIST-*');
      return apiPost<PreviewResponse>(`/api/v1/distributors/${distributor.id}/promote`, {
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
      if (!distributor) throw new Error('No distributor');
      return apiPost<ConfirmResponse>(`/api/v1/distributors/${distributor.id}/promote`, {
        new_code: newCode.trim(),
        confirm: true,
        note: note.trim() || undefined,
      });
    },
    onSuccess: (data) => {
      setSuccess(data);
      setError(null);
      void qc.invalidateQueries({ queryKey: ['admin-distributors'] });
    },
    onError: (err) => setError(safeDisplayError(err)),
  });

  const canConfirm = Boolean(preview?.can_confirm) && ack && !confirmMut.isPending && !success;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth data-testid="distributor-promote-dialog">
      <DialogTitle>Promote provisional distributor</DialogTitle>
      <DialogContent dividers>
        {!distributor ? null : (
          <Stack spacing={2}>
            <Typography variant="body2">
              {distributor.distributor_name} · <strong>{distributor.distributor_code}</strong>
            </Typography>
            <TextField
              label="New business code"
              value={newCode}
              onChange={(e) => {
                setNewCode(e.target.value);
                setPreview(null);
                setAck(false);
              }}
              fullWidth
              required
              inputProps={{ maxLength: 64, 'data-testid': 'dist-promote-new-code' }}
            />
            <TextField
              label="Steward note (optional)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              fullWidth
              multiline
              minRows={2}
              inputProps={{ maxLength: 512 }}
            />
            {error ? <Alert severity="error">{error}</Alert> : null}
            {success ? (
              <Alert severity="success" data-testid="dist-promote-success">
                Promoted {success.old_code} → {success.new_code} ({success.new_status})
              </Alert>
            ) : null}
            {preview && !success ? (
              <Stack spacing={1}>
                {(preview.warnings || []).map((w) => (
                  <Alert key={w} severity="warning">
                    {w}
                  </Alert>
                ))}
                {preview.collision ? (
                  <Alert severity="error">
                    Collision with distributor #{preview.collision.distributor_id} ({preview.collision.code})
                  </Alert>
                ) : null}
                <FormControlLabel
                  control={
                    <Checkbox
                      checked={ack}
                      onChange={(e) => setAck(e.target.checked)}
                      disabled={!preview.can_confirm}
                      data-testid="dist-promote-ack"
                    />
                  }
                  label="I understand the old TMP code is retired"
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
              data-testid="dist-promote-preview-btn"
            >
              Preview
            </Button>
            <Button
              variant="contained"
              disabled={!canConfirm}
              onClick={() => confirmMut.mutate()}
              data-testid="dist-promote-confirm-btn"
            >
              Confirm promote
            </Button>
          </>
        ) : null}
      </DialogActions>
    </Dialog>
  );
}
