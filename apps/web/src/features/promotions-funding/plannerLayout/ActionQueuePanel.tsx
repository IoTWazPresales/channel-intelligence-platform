'use client';

import { Stack, Typography } from '@mui/material';

import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

import type { ActionItem } from './actionQueue';

/** Cases waiting on a person: awaiting approval, reapproval, ended with claim evidence pending. */
export function ActionQueuePanel({
  items,
  onSelect,
}: {
  items: readonly ActionItem[];
  onSelect: (caseId: number) => void;
}) {
  return (
    <Panel title="Action queue" subtitle="Cases waiting on a decision or evidence" flush>
      <Stack spacing={0.25} sx={{ px: 1, pb: 1 }} data-testid="planner-action-queue">
        {items.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }} data-testid="planner-action-queue-empty">
            Nothing waiting on you.
          </Typography>
        ) : (
          items.map((i) => (
            <PanelRow
              key={i.key}
              severity={i.tone}
              primary={i.label}
              secondary={i.hint}
              onClick={() => onSelect(i.caseId)}
            />
          ))
        )}
      </Stack>
    </Panel>
  );
}
