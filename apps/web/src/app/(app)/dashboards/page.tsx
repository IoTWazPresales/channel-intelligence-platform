'use client';

import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiGet, apiPost, safeDisplayError } from '@/lib/api';

type SavedReport = {
  id: number;
  name: string;
  metric_key: string;
  grains: string[];
  filters: Record<string, unknown>;
  visual: string;
  visibility: string;
};

type DashboardTile = {
  id: number;
  saved_report_id: number;
  sort_order: number;
  title_override: string | null;
  report: SavedReport | null;
};

type Dashboard = {
  id: number;
  name: string;
  description: string | null;
  visibility: string;
  shared_roles: string[];
  tiles: DashboardTile[];
};

type QueryResult = {
  ok: boolean;
  value: unknown;
  message: string | null;
  status: string;
};

function formatValue(v: unknown): string {
  if (v == null) return '—';
  if (typeof v === 'number') {
    if (Math.abs(v) <= 1.5 && Number.isFinite(v)) return `${(v * 100).toFixed(1)}%`;
    return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (typeof v === 'boolean') return v ? 'Yes' : 'No';
  return String(v);
}

function DashboardTileCard({ tile }: { tile: DashboardTile }) {
  const report = tile.report;
  const q = useQuery({
    queryKey: ['dashboard-tile-query', tile.saved_report_id, report?.metric_key, report?.grains],
    enabled: Boolean(report),
    queryFn: () =>
      apiPost<QueryResult>('/api/v1/query/execute', {
        metric: report!.metric_key,
        grains: report!.grains,
        filters: report!.filters || {},
      }),
  });

  return (
    <Paper variant="outlined" sx={{ p: 2, height: '100%' }} data-testid={`dashboard-tile-${tile.id}`}>
      <Typography variant="subtitle2" fontWeight={700}>
        {tile.title_override || report?.name || `Report #${tile.saved_report_id}`}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
        {report?.metric_key} · {(report?.grains || []).join(', ')}
      </Typography>
      {q.isLoading && <Typography variant="body2">Loading…</Typography>}
      {q.isError && <Alert severity="error">{safeDisplayError(q.error)}</Alert>}
      {q.data && !q.data.ok && (
        <Alert severity="warning">{q.data.message || q.data.status}</Alert>
      )}
      {q.data?.ok && (
        <Typography variant="h4" fontWeight={700} data-testid={`dashboard-tile-value-${tile.id}`}>
          {formatValue(q.data.value)}
        </Typography>
      )}
    </Paper>
  );
}

export default function DashboardsPage() {
  const qc = useQueryClient();
  const listQ = useQuery({
    queryKey: ['dashboards'],
    queryFn: ({ signal }) => apiGet<{ items: Dashboard[] }>('/api/v1/dashboards', { signal }),
    retry: false,
  });
  const reportsQ = useQuery({
    queryKey: ['saved-reports'],
    queryFn: ({ signal }) =>
      apiGet<{ items: SavedReport[] }>('/api/v1/saved-reports', { signal }),
    retry: false,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [publish, setPublish] = useState(false);
  const [selectedReportIds, setSelectedReportIds] = useState<number[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);

  const createMut = useMutation({
    mutationFn: () =>
      apiPost<Dashboard>('/api/v1/dashboards', {
        name: name.trim(),
        visibility: publish ? 'published' : 'personal',
        shared_roles: [],
        saved_report_ids: selectedReportIds,
      }),
    onSuccess: async (d) => {
      setCreateOpen(false);
      setName('');
      setSelectedReportIds([]);
      setActiveId(d.id);
      await qc.invalidateQueries({ queryKey: ['dashboards'] });
    },
  });

  const active = (listQ.data?.items ?? []).find((d) => d.id === activeId) ?? listQ.data?.items?.[0];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Dashboards' }]} title="Dashboards" />
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 720 }}>
        Compose saved governed reports into a personal or published dashboard. Sharing is role-aware at publish time.
        Build reports on the{' '}
        <Link href="/reports">report builder</Link> first.
      </Typography>

      {listQ.isError && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Dashboards API unavailable — apply alembic <code>20260801_0006</code> on cip, then refresh.
        </Alert>
      )}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
        <Paper sx={{ p: 2, width: { md: 280 }, flexShrink: 0 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="subtitle1" fontWeight={700}>
              Yours
            </Typography>
            <Button size="small" variant="contained" onClick={() => setCreateOpen(true)} data-testid="dashboard-create">
              New
            </Button>
          </Stack>
          <Stack spacing={1}>
            {(listQ.data?.items ?? []).map((d) => (
              <Button
                key={d.id}
                variant={active?.id === d.id ? 'contained' : 'outlined'}
                size="small"
                onClick={() => setActiveId(d.id)}
                sx={{ justifyContent: 'flex-start' }}
              >
                {d.name}
                <Chip size="small" label={d.visibility} sx={{ ml: 1 }} />
              </Button>
            ))}
            {!listQ.isLoading && !listQ.isError && (listQ.data?.items?.length ?? 0) === 0 && (
              <Typography variant="body2" color="text.secondary">
                No dashboards yet.
              </Typography>
            )}
          </Stack>
        </Paper>

        <Box sx={{ flex: 1, width: '100%' }}>
          {active ? (
            <Stack spacing={2}>
              <Typography variant="h6">{active.name}</Typography>
              {active.description && (
                <Typography variant="body2" color="text.secondary">
                  {active.description}
                </Typography>
              )}
              <Box
                sx={{
                  display: 'grid',
                  gap: 2,
                  gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', lg: '1fr 1fr 1fr' },
                }}
              >
                {(active.tiles || []).map((t) => (
                  <DashboardTileCard key={t.id} tile={t} />
                ))}
              </Box>
              {(active.tiles || []).length === 0 && (
                <Alert severity="info">This dashboard has no tiles. Edit tiles after saving reports.</Alert>
              )}
            </Stack>
          ) : (
            !listQ.isError && (
              <Typography color="text.secondary">Select or create a dashboard.</Typography>
            )
          )}
        </Box>
      </Stack>

      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>New dashboard</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              fullWidth
              data-testid="dashboard-name"
            />
            <FormControlLabel
              control={<Switch checked={publish} onChange={(e) => setPublish(e.target.checked)} />}
              label="Publish to tenant (all roles)"
            />
            <Typography variant="subtitle2">Tiles (saved reports)</Typography>
            {(reportsQ.data?.items ?? []).map((r) => {
              const on = selectedReportIds.includes(r.id);
              return (
                <Button
                  key={r.id}
                  size="small"
                  variant={on ? 'contained' : 'outlined'}
                  onClick={() =>
                    setSelectedReportIds((prev) =>
                      on ? prev.filter((x) => x !== r.id) : [...prev, r.id]
                    )
                  }
                >
                  {r.name} ({r.metric_key})
                </Button>
              );
            })}
            {createMut.isError && <Alert severity="error">{safeDisplayError(createMut.error)}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!name.trim() || createMut.isPending}
            onClick={() => createMut.mutate()}
            data-testid="dashboard-create-confirm"
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
