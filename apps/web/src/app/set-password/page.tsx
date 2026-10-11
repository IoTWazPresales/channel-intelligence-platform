'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import { useTheme } from '@mui/material/styles';

import { apiPost, safeDisplayError } from '@/lib/api';

function tokenFromLocation(): string {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('token') ?? '';
}

export default function SetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const theme = useTheme();
  const darkPage = theme.palette.mode === 'dark';

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const token = tokenFromLocation();
    if (token.length < 20) {
      setError('This link is not valid. Ask an admin to send a new one.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirm) {
      setError('The two passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      await apiPost('/api/v1/auth/invites/accept', { token, new_password: password });
      router.replace('/login');
    } catch (err) {
      setError(safeDisplayError(err));
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
        component="form"
        onSubmit={onSubmit}
        sx={{
          width: '100%',
          maxWidth: 420,
          p: 4,
          borderRadius: 2,
          bgcolor: 'background.paper',
          boxShadow: 6,
        }}
      >
        <Stack spacing={2.5}>
          <Typography variant="h4" component="h1" fontWeight={700}>
            Choose a password
          </Typography>
          <Typography variant="body2" color="text.secondary">
            This link works once and expires 72 hours after it was sent.
          </Typography>
          {error ? (
            <Alert severity="error" data-testid="set-password-error">
              {error}
            </Alert>
          ) : null}
          <TextField
            label="New password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(ev) => setPassword(ev.target.value)}
            required
            fullWidth
            inputProps={{ 'data-testid': 'set-password-new', minLength: 8 }}
          />
          <TextField
            label="Confirm password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(ev) => setConfirm(ev.target.value)}
            required
            fullWidth
            inputProps={{ 'data-testid': 'set-password-confirm', minLength: 8 }}
          />
          <Button type="submit" variant="contained" size="large" disabled={busy} data-testid="set-password-submit">
            {busy ? 'Saving…' : 'Save password'}
          </Button>
        </Stack>
      </Box>
    </Box>
  );
}
