'use client';

import { Stack, Typography } from '@mui/material';

import { startVerbsForRole } from '@/features/overview/startWork';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

export function StartWorkPanel() {
  const { data: me } = useCurrentUser();
  const role = me?.role ? String(me.role) : null;
  const verbs = startVerbsForRole(role);

  return (
    <Panel
      title="Start work"
      subtitle={
        verbs.length
          ? 'Jobs you can begin from here. Needs attention stays exceptions-only.'
          : 'No start actions for this role. Find a workflow from the directory or Ctrl+K.'
      }
      flush
    >
      <Stack spacing={0.25} sx={{ px: 1, pb: 1 }} data-testid="start-work">
        {verbs.length ? (
          verbs.map((v) => (
            <PanelRow
              key={v.id}
              severity="neutral"
              primary={<span data-testid={`start-work-${v.id}`}>{v.label}</span>}
              secondary={v.what}
              href={v.href}
            />
          ))
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
            Nothing this role can start from Overview. The capability directory lists every workflow.
          </Typography>
        )}
      </Stack>
    </Panel>
  );
}
