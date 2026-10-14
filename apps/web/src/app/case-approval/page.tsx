'use client';

import { useEffect, useState } from 'react';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useTheme } from '@mui/material/styles';

import { formatLocalMoney } from '@/features/cpor/fxDisplay';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

type Line = {
  product: string;
  estimate_qty: number | null;
  result_qty: number | null;
  support_per_unit: number | null;
  support_total: number | null;
};

type Summary = {
  case_code: string;
  case_name: string | null;
  customer_name: string;
  window_start: string | null;
  window_end: string | null;
  currency: string;
  export_version: number;
  lines: Line[];
  support_total: number | null;
};

function tokenFromLocation(): string {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('token') ?? '';
}

export default function CaseApprovalPage() {
  const theme = useTheme();
  const darkPage = theme.palette.mode === 'dark';
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [name, setName] = useState('');
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const token = tokenFromLocation();
    if (token.length < 20) {
      setError('This link is not valid. Ask the planner to send a new one.');
      return;
    }
    apiGet<Summary>(`/api/v1/case-approval?token=${encodeURIComponent(token)}`)
      .then(setSummary)
      .catch((err: unknown) => setError(safeDisplayError(err)));
  }, []);

  async function decide(decision: 'approved' | 'rejected', event: { preventDefault: () => void }) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiPost('/api/v1/case-approval', {
        token: tokenFromLocation(),
        decision,
        signer_name: name.trim(),
        comment: comment.trim(),
      });
      setDone(true);
    } catch (err) {
      setError(safeDisplayError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: darkPage ? 'background.default' : 'grey.100',
        p: 2,
      }}
    >
      <Box
        sx={{
          width: '100%',
          maxWidth: 720,
          p: 4,
          borderRadius: 2,
          bgcolor: 'background.paper',
          boxShadow: 6,
        }}
        data-testid="case-approval"
      >
        <Stack spacing={2}>
          <Typography variant="h4" component="h1" fontWeight={700}>
            Settlement sign-off
          </Typography>
          {error ? (
            <Alert severity="error" data-testid="case-approval-error">
              {error}
            </Alert>
          ) : null}
          {done ? (
            <Alert severity="success" data-testid="case-approval-done">
              Your decision is recorded. You can close this page.
            </Alert>
          ) : null}
          {summary && !done ? (
            <Stack component="form" spacing={2} onSubmit={(event) => decide('approved', event)}>
              <Typography variant="body1">
                {summary.case_code}
                {summary.case_name ? ` · ${summary.case_name}` : ''} · {summary.customer_name}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {summary.window_start} to {summary.window_end}. Version {summary.export_version}. Support{' '}
                {formatLocalMoney(summary.support_total, summary.currency)}.
              </Typography>
              <Box component="ul" sx={{ m: 0, pl: 2 }} data-testid="case-approval-lines">
                {summary.lines.map((line, index) => (
                  <li key={`${index}-${line.product}`}>
                    {line.product}: estimated {line.estimate_qty ?? '—'}, result {line.result_qty ?? '—'}, support{' '}
                    {formatLocalMoney(line.support_total, summary.currency)}
                  </li>
                ))}
              </Box>
              <TextField
                label="Your name"
                value={name}
                onChange={(ev) => setName(ev.target.value)}
                required
                fullWidth
                inputProps={{ 'data-testid': 'case-approval-name' }}
              />
              <TextField
                label="Comment"
                value={comment}
                onChange={(ev) => setComment(ev.target.value)}
                required
                fullWidth
                multiline
                minRows={2}
                inputProps={{ 'data-testid': 'case-approval-comment' }}
              />
              <Stack direction="row" spacing={1}>
                <Button type="submit" variant="contained" disabled={busy} data-testid="case-approval-approve">
                  Approve
                </Button>
                <Button
                  type="button"
                  variant="outlined"
                  color="warning"
                  disabled={busy}
                  data-testid="case-approval-reject"
                  onClick={(event) => {
                    if (event.currentTarget.form?.reportValidity() === false) return;
                    void decide('rejected', event);
                  }}
                >
                  Reject
                </Button>
              </Stack>
            </Stack>
          ) : null}
        </Stack>
      </Box>
    </Box>
  );
}
