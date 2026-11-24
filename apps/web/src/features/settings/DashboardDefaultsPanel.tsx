'use client';

import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { JOBS } from '@/features/administration/UsersWorkspace';
import { JOB_DEFAULTS_KEY } from '@/features/overview/homeDashboard';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { Panel } from '@/features/workbench-ui/Panel';
import { apiGet, apiPut, safeDisplayError } from '@/lib/api';

type Starter = { key: string; title: string };

/** Dashboard V2: which starter each job resets to. Only what the tenant saves; no job has a default until then. */
export function DashboardDefaultsPanel() {
  const me = useCurrentUser();
  const canEdit = me.data?.role === 'admin' || me.data?.role === 'steward';
  const templatesQ = useQuery({
    queryKey: ['dashboards', 'templates'],
    queryFn: ({ signal }) => apiGet<{ items: Starter[] }>('/api/v1/dashboards/templates', { signal }),
    enabled: canEdit,
    staleTime: 5 * 60_000,
  });
  const settingsQ = useQuery({
    queryKey: ['tenant-settings'],
    queryFn: ({ signal }) => apiGet<{ settings: Record<string, unknown> }>('/api/v1/tenant-settings', { signal }),
    enabled: canEdit,
    staleTime: 60_000,
  });
  if (!canEdit) return null;
  const saved = (settingsQ.data?.settings?.[JOB_DEFAULTS_KEY] ?? {}) as Record<string, string>;
  return (
    <Box id="dashboard-defaults" data-testid="dashboard-defaults-settings">
      <Panel title="Dashboards" subtitle="The starter each job gets from Reset to my role default. Leave a job empty for none.">
        {templatesQ.isPending || settingsQ.isPending ? <Typography variant="body2">Loading dashboard settings…</Typography> : null}
        {templatesQ.isError || settingsQ.isError ? <Alert severity="error">{safeDisplayError(templatesQ.error ?? settingsQ.error)}</Alert> : null}
        {templatesQ.data && settingsQ.data ? (
          <DefaultsForm key={JSON.stringify(saved)} initial={saved} starters={templatesQ.data.items} />
        ) : null}
      </Panel>
    </Box>
  );
}

function DefaultsForm({ initial, starters }: { initial: Record<string, string>; starters: Starter[] }) {
  const qc = useQueryClient();
  const [map, setMap] = useState<Record<string, string>>(initial);
  const save = useMutation({
    mutationFn: () =>
      apiPut(`/api/v1/tenant-settings/${JOB_DEFAULTS_KEY}`, { value: Object.fromEntries(Object.entries(map).filter(([, v]) => v)) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tenant-settings'] }),
  });
  return (
    <Stack spacing={1.5}>
      {JOBS.map((job) => (
        <TextField
          key={job.value}
          select
          size="small"
          label={job.label}
          value={map[job.value] ?? ''}
          onChange={(e) => setMap((m) => ({ ...m, [job.value]: e.target.value }))}
          sx={{ maxWidth: 360 }}
          inputProps={{ 'data-testid': `job-default-${job.value}` }}
        >
          <MenuItem value="">No starter</MenuItem>
          {starters.map((s) => (
            <MenuItem key={s.key} value={s.key}>
              {s.title}
            </MenuItem>
          ))}
        </TextField>
      ))}
      <Stack direction="row" spacing={1} alignItems="center">
        <Button variant="contained" size="small" onClick={() => save.mutate()} disabled={save.isPending} data-testid="job-defaults-save">
          Save
        </Button>
        {save.isSuccess ? <Typography variant="caption">Saved.</Typography> : null}
        {save.isError ? <Typography variant="caption" color="error" role="alert">{safeDisplayError(save.error)}</Typography> : null}
      </Stack>
    </Stack>
  );
}