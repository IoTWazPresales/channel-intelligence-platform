'use client';

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material';
import type { ReactNode } from 'react';

export function BulkPasteDialog({
  open,
  title,
  hint,
  placeholder,
  value,
  onChange,
  onClose,
  onSubmit,
  submitLabel = 'Import',
  busy,
  error,
}: {
  open: boolean;
  title: string;
  hint?: ReactNode;
  placeholder?: string;
  value: string;
  onChange: (v: string) => void;
  onClose: () => void;
  onSubmit: () => void;
  submitLabel?: string;
  busy?: boolean;
  error?: Error | null;
}) {
  return (
    <Dialog open={open} onClose={() => !busy && onClose()} fullWidth maxWidth="md">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        {hint ? (
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            {hint}
          </Typography>
        ) : null}
        <TextField
          multiline
          minRows={10}
          fullWidth
          value={value}
          onChange={(ev) => onChange(ev.target.value)}
          placeholder={placeholder}
        />
        {error ? (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error.message}
          </Alert>
        ) : null}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button variant="contained" disabled={busy || !value.trim()} onClick={onSubmit}>
          {submitLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
