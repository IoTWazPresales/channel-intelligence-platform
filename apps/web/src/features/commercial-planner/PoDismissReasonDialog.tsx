'use client';

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useEffect, useState } from 'react';

export function PoDismissReasonDialog({
  open,
  title,
  description,
  defaultReason,
  confirmLabel = 'Dismiss',
  isPending,
  error,
  onClose,
  onConfirm,
}: {
  open: boolean;
  title: string;
  description?: string;
  defaultReason: string;
  confirmLabel?: string;
  isPending?: boolean;
  error?: string | null;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState(defaultReason);

  useEffect(() => {
    if (open) setReason(defaultReason);
  }, [open, defaultReason]);

  return (
    <Dialog open={open} onClose={isPending ? undefined : onClose} maxWidth="xs" fullWidth data-testid="po-dismiss-reason-dialog">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {description ? (
            <Typography variant="body2" color="text.secondary">
              {description}
            </Typography>
          ) : null}
          <TextField
            size="small"
            label="Reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            multiline
            rows={2}
            fullWidth
            autoFocus
            data-testid="po-dismiss-reason-input"
          />
          {error ? <Alert severity="error">{error}</Alert> : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button size="small" onClick={onClose} disabled={isPending}>
          Cancel
        </Button>
        <Button
          size="small"
          color="warning"
          variant="contained"
          disabled={isPending || !reason.trim()}
          onClick={() => onConfirm(reason.trim())}
          data-testid="po-dismiss-reason-submit"
        >
          {isPending ? 'Dismissing…' : confirmLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
