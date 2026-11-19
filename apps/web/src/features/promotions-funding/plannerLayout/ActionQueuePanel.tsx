'use client';

import { Alert, Button, Stack, Typography } from '@mui/material';

import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

import type { ActionItem } from './actionQueue';

/** Cases waiting on a person: awaiting approval, reapproval, ended with claim evidence pending. */
export function ActionQueuePanel({
  items,
  loading = false,
  unavailable = [],
  onRetry,
  onSelect,
}: {
  items: readonly ActionItem[];
  /** A source list is still loading: never answer "nothing waiting" yet. */
  loading?: boolean;
  /** Names of the source lists that failed to load; the queue is then incomplete, never confirmed empty. */
  unavailable?: readonly string[];
  onRetry?: () => void;
  onSelect: (caseId: number) => void;
}) {
  return (
    <Panel title="Action queue" subtitle="Cases waiting on a decision or evidence" flush>
      <Stack spacing={0.25} sx={{ px: 1, pb: 1 }} data-testid="planner-action-queue">
        {unavailable.length > 0 ? (
          <Alert
            severity="error"
            variant="outlined"
            data-testid="planner-action-queue-error"
            action={
              onRetry ? (
                <Button color="inherit" size="small" onClick={onRetry}>
                  Retry
                </Button>
              ) : undefined
            }
          >
            Could not load: {unavailable.join(', ')}.{' '}
            {items.length > 0 ? 'The queue below may be incomplete.' : 'This is not an empty queue.'}
          </Alert>
        ) : null}
        {items.length === 0 && unavailable.length > 0 ? null : items.length === 0 && loading ? (
          <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }} data-testid="planner-action-queue-loading">
            Loading…
          </Typography>
        ) : items.length === 0 ? (
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
