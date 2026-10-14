'use client';

import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';

function when(iso: string | undefined): string {
  if (!iso) return 'soon';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

type LinkView = {
  state: string;
  recipient_email?: string;
  expires_at?: string;
  decision?: string | null;
  signer_name?: string | null;
};

function describe(view: LinkView | undefined): string {
  if (!view || view.state === 'none') return 'No sign-off link has been sent.';
  if (view.state === 'open') {
    return `Waiting on ${view.recipient_email}. The link expires ${when(view.expires_at)}.`;
  }
  if (view.state === 'decided') {
    return `${view.signer_name} ${view.decision} this version.`;
  }
  if (view.state === 'revoked') return 'The last link was withdrawn.';
  if (view.state === 'expired') return 'The last link expired.';
  if (view.state === 'stale') return 'The case changed after the link was sent. Send a new one.';
  return 'No open sign-off link.';
}

export function CustomerApprovalLinkPanel({ caseId }: { caseId: number }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const key = ['cpor', 'approval-link', caseId] as const;
  const status = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => apiGet<LinkView>(`/api/v1/cpor/cases/${caseId}/approval-link`, { signal }),
  });

  const send = useMutation({
    mutationFn: () =>
      apiPost<LinkView>(`/api/v1/cpor/cases/${caseId}/approval-link`, { recipient_email: email.trim() }),
    onSuccess: (view) => {
      setError(null);
      qc.setQueryData(key, view);
    },
    onError: (err: Error) => setError(err.message),
  });

  const revoke = useMutation({
    mutationFn: () => apiPost<LinkView>(`/api/v1/cpor/cases/${caseId}/approval-link/revoke`, {}),
    onSuccess: (view) => {
      setError(null);
      qc.setQueryData(key, view);
    },
    onError: (err: Error) => setError(err.message),
  });

  return (
    <Stack spacing={1.5} data-testid="customer-approval-link" sx={{ mb: 2 }}>
      <Typography variant="h6" component="h2">
        Customer sign-off
      </Typography>
      <Typography variant="body2" color="text.secondary">
        {describe(status.data)} The customer sees this case only.
      </Typography>
      {error ? (
        <Alert severity="error" data-testid="customer-approval-link-error">
          {error}
        </Alert>
      ) : null}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
        <TextField
          label="Customer email"
          type="email"
          value={email}
          onChange={(ev) => setEmail(ev.target.value)}
          size="small"
          fullWidth
          inputProps={{ 'data-testid': 'customer-approval-email' }}
        />
        <Button
          variant="contained"
          disabled={send.isPending || !email.includes('@')}
          onClick={() => send.mutate()}
          data-testid="customer-approval-send"
        >
          {send.isPending ? 'Sending…' : 'Send link'}
        </Button>
        <Button
          variant="outlined"
          disabled={revoke.isPending || status.data?.state !== 'open'}
          onClick={() => revoke.mutate()}
          data-testid="customer-approval-revoke"
        >
          Withdraw
        </Button>
      </Stack>
    </Stack>
  );
}
