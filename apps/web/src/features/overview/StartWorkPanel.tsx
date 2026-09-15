'use client';

import { Box, Typography } from '@mui/material';

import { startVerbsForRole } from '@/features/overview/startWork';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

export function StartWorkPanel() {
  const { data: me } = useCurrentUser();
  const role = me?.role ? String(me.role) : null;
  const verbs = startVerbsForRole(role);

  return (
    <Box data-testid="start-work">
      <Panel
        title="Start work"
        subtitle={
          verbs.length
            ? 'Begin a job from here. Needs attention stays exceptions-only.'
            : 'No start actions for this role. Find a workflow from the directory or Ctrl+K.'
        }
        flush
      >
        {verbs.length ? (
          <Box sx={{ px: 1, pb: 1 }}>
            {verbs.map((v) => (
              <PanelRow
                key={v.id}
                severity="neutral"
                primary={<span data-testid={`start-work-${v.id}`}>{v.label}</span>}
                secondary={v.what}
                href={v.href}
              />
            ))}
          </Box>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ px: 2, pb: 2 }}>
            Nothing this role can start from Overview. The capability directory lists every workflow.
          </Typography>
        )}
      </Panel>
    </Box>
  );
}
