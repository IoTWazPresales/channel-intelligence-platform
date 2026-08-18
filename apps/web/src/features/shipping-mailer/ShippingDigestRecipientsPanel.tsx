'use client';

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiDelete, apiGet, apiPatch, apiPost, safeDisplayError } from '@/lib/api';

import {
  looksLikeEmail,
  RECIPIENTS_PATH,
  SHIPPING_MAILER_RECIPIENTS_QUERY_KEY,
  type ShippingMailerRecipient,
  type ShippingMailerRecipientList,
} from './types';

function formatStamp(value: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toISOString().slice(0, 16).replace('T', ' ');
}

export function ShippingDigestRecipientsPanel() {
  const qc = useQueryClient();
  const [address, setAddress] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [clientError, setClientError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ShippingMailerRecipient | null>(null);

  const listQuery = useQuery({
    queryKey: SHIPPING_MAILER_RECIPIENTS_QUERY_KEY,
    queryFn: ({ signal }) => apiGet<ShippingMailerRecipientList>(RECIPIENTS_PATH, { signal }),
  });

  const addMutation = useMutation({
    mutationFn: () =>
      apiPost<ShippingMailerRecipient>(RECIPIENTS_PATH, {
        address: address.trim(),
        display_name: displayName.trim() || null,
      }),
    onSuccess: async () => {
      setAddress('');
      setDisplayName('');
      setClientError(null);
      await qc.invalidateQueries({ queryKey: SHIPPING_MAILER_RECIPIENTS_QUERY_KEY });
    },
  });

  const patchMutation = useMutation({
    mutationFn: (payload: { id: number; enabled: boolean }) =>
      apiPatch<ShippingMailerRecipient>(`${RECIPIENTS_PATH}/${payload.id}`, { enabled: payload.enabled }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: SHIPPING_MAILER_RECIPIENTS_QUERY_KEY });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => apiDelete(`${RECIPIENTS_PATH}/${id}`),
    onSuccess: async () => {
      setDeleteTarget(null);
      await qc.invalidateQueries({ queryKey: SHIPPING_MAILER_RECIPIENTS_QUERY_KEY });
    },
  });

  const items = listQuery.data?.items ?? [];
  const mutationError =
    addMutation.error || patchMutation.error || deleteMutation.error
      ? safeDisplayError(addMutation.error || patchMutation.error || deleteMutation.error)
      : null;

  const onAdd = () => {
    setClientError(null);
    if (!looksLikeEmail(address)) {
      setClientError('Enter a valid email address.');
      return;
    }
    addMutation.mutate();
  };

  return (
    <Stack spacing={2} data-testid="shipping-mailer-recipients-panel">
      <Typography variant="subtitle1" fontWeight={600} data-testid="shipping-mailer-recipients-heading">
        Shipping digest recipients
      </Typography>
      <Typography variant="body2" color="text.secondary">
        External To-list for the post-apply shipping digest. The five ASUS addresses are the floor whenever
        this list is empty. Disable a row to drop someone without falling back. Disable every row to mute the
        digest. Changes apply to the next digest — no restart.
      </Typography>
      {listQuery.isError ? (
        <Alert severity="error" data-testid="shipping-mailer-recipients-load-error">
          {safeDisplayError(listQuery.error)}
        </Alert>
      ) : null}
      {mutationError ? (
        <Alert severity="error" data-testid="shipping-mailer-recipients-save-error">
          {mutationError}
        </Alert>
      ) : null}
      {clientError ? (
        <Alert severity="warning" data-testid="shipping-mailer-recipients-validation-error">
          {clientError}
        </Alert>
      ) : null}

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} alignItems={{ sm: 'flex-start' }}>
        <TextField
          size="small"
          label="Email address"
          value={address}
          onChange={(ev) => setAddress(ev.target.value)}
          fullWidth
          inputProps={{ 'data-testid': 'shipping-mailer-recipients-add-address' }}
        />
        <TextField
          size="small"
          label="Display name (optional)"
          value={displayName}
          onChange={(ev) => setDisplayName(ev.target.value)}
          fullWidth
          inputProps={{ 'data-testid': 'shipping-mailer-recipients-add-name' }}
        />
        <Button
          variant="contained"
          onClick={onAdd}
          disabled={addMutation.isPending}
          data-testid="shipping-mailer-recipients-add"
          sx={{ whiteSpace: 'nowrap' }}
        >
          {addMutation.isPending ? 'Adding…' : 'Add'}
        </Button>
      </Stack>

      <Table size="small" data-testid="shipping-mailer-recipients-table">
        <TableHead>
          <TableRow>
            <TableCell>Address</TableCell>
            <TableCell>Name</TableCell>
            <TableCell>Enabled</TableCell>
            <TableCell>Added by</TableCell>
            <TableCell>Added</TableCell>
            <TableCell />
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((row) => (
            <TableRow key={row.id} data-testid={`shipping-mailer-recipients-row-${row.id}`}>
              <TableCell>{row.address}</TableCell>
              <TableCell>{row.display_name || '—'}</TableCell>
              <TableCell>
                <Switch
                  checked={row.enabled}
                  onChange={(_, checked) => patchMutation.mutate({ id: row.id, enabled: checked })}
                  disabled={patchMutation.isPending}
                  inputProps={{
                    'aria-label': `Enable ${row.address}`,
                    'data-testid': `shipping-mailer-recipients-enabled-${row.id}`,
                  }}
                />
              </TableCell>
              <TableCell>{row.added_by || '—'}</TableCell>
              <TableCell>{formatStamp(row.created_at)}</TableCell>
              <TableCell>
                <Button
                  size="small"
                  color="error"
                  onClick={() => setDeleteTarget(row)}
                  data-testid={`shipping-mailer-recipients-delete-${row.id}`}
                >
                  Remove
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Dialog
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        data-testid="shipping-mailer-recipients-delete-dialog"
      >
        <DialogTitle>Remove recipient</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Remove {deleteTarget?.address} from the digest list? If this is the last row, the next digest will
            re-seed the five ASUS addresses. Disable the row instead to drop them without falling back.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)} data-testid="shipping-mailer-recipients-delete-cancel">
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            disabled={deleteMutation.isPending || !deleteTarget}
            onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
            data-testid="shipping-mailer-recipients-delete-confirm"
          >
            Remove
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
