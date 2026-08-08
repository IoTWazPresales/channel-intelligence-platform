'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import Alert from '@mui/material/Alert';

import { apiPost, apiUrl, safeDisplayError } from '@/lib/api';
import { setAuthToken } from '@/lib/authSession';
import { AUTH_ME_QUERY_KEY } from '@/features/shell/useCurrentUser';
import { useQueryClient } from '@tanstack/react-query';

type LoginResponse = {
  token: string;
  expires_at: string;
  user: { id: string; email: string; role: string; display_name?: string };
};

export default function LoginPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [email, setEmail] = useState('admin@local');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await apiPost<LoginResponse>('/api/v1/auth/login', { email, password });
      setAuthToken(res.token);
      await qc.invalidateQueries({ queryKey: AUTH_ME_QUERY_KEY });
      router.replace('/dashboard');
    } catch (err) {
      setError(safeDisplayError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box
      component="main"
      sx={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        px: 2,
        background: 'linear-gradient(160deg, #0f172a 0%, #1e293b 45%, #334155 100%)',
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
            Channel Intelligence
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Sign in with your CIP account.
          </Typography>
          {error ? (
            <Alert severity="error" data-testid="login-error">
              {error}
            </Alert>
          ) : null}
          <TextField
            label="Email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            required
            fullWidth
            inputProps={{ 'data-testid': 'login-email' }}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(ev) => setPassword(ev.target.value)}
            required
            fullWidth
            inputProps={{ 'data-testid': 'login-password' }}
          />
          <Button type="submit" variant="contained" size="large" disabled={busy} data-testid="login-submit">
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
          <Typography variant="body2" color="text.secondary" data-testid="login-forgot-password">
            Forgot password? Ask an admin to use <strong>Reset password</strong> on Admin → Users.
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Dev seed (after IAM migration): admin@local / changeme · API {apiUrl('/api/v1/auth/me')}
          </Typography>
        </Stack>
      </Box>
    </Box>
  );
}
