'use client';

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiPost, getApiBase } from '@/lib/api';
import { loadWipeAvailability } from '@/lib/wipeAvailability';
import { useUiStore } from '@/stores/uiStore';

const WIPE_CONFIRM_PHRASE = 'DELETE ALL APPLICATION DATA';

export default function SettingsPage() {
  const apiDisplay =
    getApiBase() ||
    'Same-origin /api/… (rewritten to FastAPI in next dev when NEXT_PUBLIC_API_URL is unset)';
  const density = useUiStore((s) => s.density);
  const qc = useQueryClient();
  const [wipeOpen, setWipeOpen] = useState(false);
  const [wipePhrase, setWipePhrase] = useState('');

  const { data: wipeStatus, isPending: wipeStatusPending } = useQuery({
    queryKey: ['dev-database-wipe-status'],
    queryFn: ({ signal }) => loadWipeAvailability(signal),
    staleTime: 30_000,
  });

  const wipeMutation = useMutation({
    mutationFn: () => apiPost<{ ok: boolean; rows_deleted: number }>('/api/v1/dev/database-wipe', { confirm: true }),
    onSuccess: async (data) => {
      setWipeOpen(false);
      setWipePhrase('');
      await qc.invalidateQueries();
      window.alert(`Database wiped. ${data.rows_deleted} row(s) deleted. Reload the page if grids look stale.`);
    },
  });

  const phraseOk = useMemo(() => wipePhrase.trim() === WIPE_CONFIRM_PHRASE, [wipePhrase]);

  return (
    <>
      <PageHeader crumbs={[{ label: 'Settings' }]} title="Settings" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Authentication and per-user preferences are not fully wired yet. Density is saved in the browser; API
        location is build-time for the web bundle.
      </Alert>
      <Paper sx={{ p: 3 }}>
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          API base URL
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          <code style={{ wordBreak: 'break-all' }}>{apiDisplay}</code>
        </Typography>
        <Typography variant="caption" color="text.disabled">
          Set <code>NEXT_PUBLIC_API_URL</code> before <code>pnpm build</code> or in Docker build args to pin the API
          host. Leave it unset in <code>next dev</code> to use same-origin <code>/api/v1/…</code> (proxied by{' '}
          <code>src/app/api/v1/[[...path]]/route.ts</code> to FastAPI on <code>127.0.0.1:8000</code> by default).
        </Typography>
        <Divider sx={{ my: 3 }} />
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Table density
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography variant="body2" color="text.secondary">
            Current: <strong>{density}</strong> — toggle from the toolbar (compact rows icon).
          </Typography>
        </Stack>

        <Divider sx={{ my: 3 }} />
        <Typography variant="subtitle1" fontWeight={600} gutterBottom>
          Developer: wipe database
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Removes <strong>every row</strong> in all application tables (same as{' '}
          <code>python scripts/wipe_database.py</code> in the API repo). Schema stays; upload files on disk are
          unchanged. Restart the Celery worker after a wipe if you use background jobs.
        </Typography>
        {wipeStatusPending ? (
          <Typography variant="body2" color="text.secondary">
            Checking whether database wipe is available on this API…
          </Typography>
        ) : wipeStatus?.fetch_error ? (
          <Stack spacing={2}>
            <Alert severity="error">
              Could not read wipe status from <code>{apiDisplay}</code>: {wipeStatus.fetch_error}
              {wipeStatus.fetch_error.startsWith('404 ') ? (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  A <strong>404</strong> here usually means the process on <code>127.0.0.1:8000</code> (or your proxy
                  target) is <strong>not the API from this repository</strong>, or it is an <strong>older uvicorn</strong>{' '}
                  still holding the port. Run <code>pnpm dev:api</code> from a clean port (it refuses to start if the
                  port serves the wrong OpenAPI), or stop Docker/other Python on that port, then reload Settings.
                </Typography>
              ) : (
                <Typography variant="body2" sx={{ mt: 1 }}>
                  If other pages load data, compare <code>NEXT_PUBLIC_API_URL</code> (build-time) to the API you are
                  actually running, and ensure this API version includes <code>GET /api/v1/dev/database-wipe</code>{' '}
                  (CORS must allow your web origin and <code>X-User-Id</code> / <code>X-User-Role</code> headers).
                </Typography>
              )}
            </Alert>
            <Alert severity="warning">
              Wipe via the UI stays <strong>off</strong> until the status call succeeds. You can still wipe from a
              shell: <code>pnpm docker:db:wipe</code> / <code>pnpm docker:db:wipe:run</code>, or run{' '}
              <code>python scripts/wipe_database.py</code> from <code>apps/api</code> against your Postgres URL.
            </Alert>
          </Stack>
        ) : wipeStatus?.wipe_enabled ? (
          <>
            <Alert severity="error" sx={{ mb: 2 }}>
              Wipe is <strong>enabled</strong> on this API (<code>ALLOW_DB_WIPE=true</code>). Do not use on shared or
              production databases.
            </Alert>
            <Button variant="outlined" color="error" onClick={() => setWipeOpen(true)}>
              Open wipe confirmation…
            </Button>
          </>
        ) : (
          <Alert severity="warning">
            Wipe via the UI is <strong>disabled</strong> (<code>ALLOW_DB_WIPE</code> is not set on the API). On the API
            host, set <code>ALLOW_DB_WIPE=true</code>, restart the API, then reload this page. For Docker, uncomment{' '}
            <code>ALLOW_DB_WIPE</code> under the <code>api</code> service in <code>infra/docker/docker-compose.yml</code>{' '}
            or use <code>pnpm docker:db:wipe</code> / <code>pnpm docker:db:wipe:run</code> from the repo root instead.
          </Alert>
        )}
      </Paper>

      <Dialog open={wipeOpen} onClose={() => !wipeMutation.isPending && setWipeOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Wipe all application data?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            This cannot be undone. Type the following phrase exactly (case-sensitive) to enable the button:
          </Typography>
          <Paper variant="outlined" sx={{ p: 1.5, mb: 2, bgcolor: 'action.hover' }}>
            <Typography variant="body2" fontFamily="monospace">
              {WIPE_CONFIRM_PHRASE}
            </Typography>
          </Paper>
          <TextField
            fullWidth
            label="Confirmation phrase"
            value={wipePhrase}
            onChange={(e) => setWipePhrase(e.target.value)}
            disabled={wipeMutation.isPending}
            autoComplete="off"
          />
          {wipeMutation.isError ? (
            <Alert severity="error" sx={{ mt: 2 }}>
              {wipeMutation.error instanceof Error ? wipeMutation.error.message : String(wipeMutation.error)}
            </Alert>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWipeOpen(false)} disabled={wipeMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={!phraseOk || wipeMutation.isPending}
            onClick={() => wipeMutation.mutate()}
          >
            {wipeMutation.isPending ? 'Wiping…' : 'Wipe database'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
