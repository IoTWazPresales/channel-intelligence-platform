'use client';

import { Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, TextField, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { dashboardListKey } from '@/features/dashboards/dashboardList';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { apiGet, apiPost, apiPut, safeDisplayError } from '@/lib/api';

import { HOME_LAYOUT_URL, jobDefaultKey, type HomeLayoutDoc } from './homeDashboard';

type Option = { id: number; name: string };

export function homeLayoutQueryKey(me: { id?: string; tenant_id?: string | null } | null | undefined) {
  return ['me', 'ui-layout', me?.tenant_id ?? null, me?.id ?? null, 'dashboard.home'] as const;
}

/** The person's chosen home dashboard id, or null when they have not chosen one. */
export function useHomeDashboardId(): number | null {
  const { data: me } = useCurrentUser();
  const q = useQuery({
    queryKey: homeLayoutQueryKey(me),
    queryFn: ({ signal }) => apiGet<HomeLayoutDoc>(HOME_LAYOUT_URL, { signal }),
    enabled: Boolean(me?.id),
    retry: false,
    staleTime: 60_000,
  });
  const id = q.data?.value?.dashboard_id;
  return typeof id === 'number' ? id : null;
}

/** Header controls on Overview: choose my home dashboard; reset to my job's starter (with confirmation). */
export function HomeDashboardControls({ dashboards, activeId }: { dashboards: Option[]; activeId: number | undefined }) {
  const qc = useQueryClient();
  const { data: me } = useCurrentUser();
  const [confirm, setConfirm] = useState(false);
  const settingsQ = useQuery({
    queryKey: ['tenant-settings'],
    queryFn: ({ signal }) => apiGet<{ settings: Record<string, unknown> }>('/api/v1/tenant-settings', { signal }),
    staleTime: 60_000,
    retry: false,
  });
  const starter = jobDefaultKey(settingsQ.data?.settings, me?.job);

  const setHome = async (id: number) => {
    await apiPut(HOME_LAYOUT_URL, { value: { dashboard_id: id } });
    await qc.invalidateQueries({ queryKey: homeLayoutQueryKey(me) });
  };
  const choose = useMutation({ mutationFn: setHome });
  const reset = useMutation({
    mutationFn: async () => {
      if (!starter) throw new Error('No starter is set for your job.');
      // A new copy of the starter; the current dashboard stays in the list (nothing is deleted).
      const created = await apiPost<{ id: number }>('/api/v1/dashboards/from-template', { key: starter });
      await qc.invalidateQueries({ queryKey: dashboardListKey(me) });
      await setHome(created.id);
    },
    onSuccess: () => setConfirm(false),
  });

  return (
    <>
      {dashboards.length > 1 ? (
        <TextField
          select
          size="small"
          label="Home"
          value={activeId ?? ''}
          onChange={(e) => choose.mutate(Number(e.target.value))}
          sx={{ minWidth: 160 }}
          inputProps={{ 'data-testid': 'overview-home-select' }}
        >
          {dashboards.map((d) => (
            <MenuItem key={d.id} value={d.id}>
              {d.name}
            </MenuItem>
          ))}
        </TextField>
      ) : null}
      <Button
        size="small"
        variant="text"
        onClick={() => setConfirm(true)}
        disabled={!starter}
        title={starter ? undefined : 'An admin sets a starter for your job in Settings -> Dashboards.'}
        data-testid="overview-reset-home"
      >
        Reset to my role default
      </Button>
      {choose.isError ? (
        <Typography variant="caption" color="error" role="alert">
          {safeDisplayError(choose.error)}
        </Typography>
      ) : null}
      <Dialog open={confirm} onClose={() => setConfirm(false)} aria-labelledby="reset-home-title">
        <DialogTitle id="reset-home-title">Reset to my role default?</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            This adds a fresh copy of your job&apos;s starter dashboard and makes it your home. Your current dashboards stay in the list.
          </Typography>
          {reset.isError ? (
            <Typography variant="body2" color="error" role="alert" sx={{ mt: 1 }}>
              {safeDisplayError(reset.error)}
            </Typography>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirm(false)}>Cancel</Button>
          <Button variant="contained" onClick={() => reset.mutate()} disabled={reset.isPending} data-testid="overview-reset-home-confirm">
            Reset
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}