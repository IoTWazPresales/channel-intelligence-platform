'use client';

import { Alert, Box, Button, Stack, Typography } from '@mui/material';

import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

import type { ActionItem } from './actionQueue';

/** A headline figure above the queue list (overdue approvals, evidence outstanding, conflicting windows). */
export type QueueCard = {
  key: string;
  label: string;
  /** null until the figure exists; a loading or failed figure is never shown as zero. */
  value: number | null;
  state: 'ready' | 'loading' | 'empty';
  caption?: string;
  tone?: 'warning' | 'neutral';
  onClick?: () => void;
};

/** Cases waiting on a person: awaiting approval, reapproval, ended with claim evidence pending. */
export function ActionQueuePanel({
  items,
  cards = [],
  loading = false,
  unavailable = [],
  incomplete = false,
  onRetry,
  onSelect,
}: {
  items: readonly ActionItem[];
  cards?: readonly QueueCard[];
  /** A source list is still loading: never answer "nothing waiting" yet. */
  loading?: boolean;
  /** Names of the source lists that failed to load; the queue is then incomplete, never confirmed empty. */
  unavailable?: readonly string[];
  /** A source list returned only its first page: the queue is a partial view, never confirmed empty. */
  incomplete?: boolean;
  onRetry?: () => void;
  onSelect: (caseId: number) => void;
}) {
  return (
    <Panel title="Action queue" subtitle="Cases waiting on a decision or evidence" flush>
      {cards.length > 0 ? (
        <Box
          data-testid="planner-queue-cards"
          sx={{ display: 'grid', gap: 1, px: 1, pb: 1, gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}
        >
          {cards.map((c) => (
            <Box
              key={c.key}
              component="button"
              type="button"
              data-testid={`planner-queue-card-${c.key}`}
              data-state={c.state}
              onClick={c.onClick}
              disabled={!c.onClick}
              sx={{
                textAlign: 'left',
                p: 1,
                borderRadius: 1,
                border: 1,
                borderColor: c.tone === 'warning' && c.state === 'ready' && (c.value ?? 0) > 0 ? 'warning.main' : 'divider',
                bgcolor: 'background.paper',
                color: 'text.primary',
                font: 'inherit',
                cursor: c.onClick ? 'pointer' : 'default',
              }}
            >
              <Typography variant="caption" color="text.secondary" component="span" sx={{ display: 'block' }}>
                {c.label}
              </Typography>
              <Typography variant="h6" component="span" sx={{ display: 'block', lineHeight: 1.2 }}>
                {c.state === 'loading' ? '…' : c.value == null ? '—' : c.value}
              </Typography>
              {c.caption ? (
                <Typography variant="caption" color="text.secondary" component="span" sx={{ display: 'block' }}>
                  {c.caption}
                </Typography>
              ) : null}
            </Box>
          ))}
        </Box>
      ) : null}
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
        ) : items.length === 0 && incomplete ? (
          <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }} data-testid="planner-action-queue-incomplete">
            Nothing found in the first 500 cases of each list; more cases exist, so something may still be waiting.
          </Typography>
        ) : items.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }} data-testid="planner-action-queue-empty">
            Nothing waiting on you.
          </Typography>
        ) : (
          <>
            {incomplete ? (
              <Typography variant="caption" color="text.secondary" sx={{ px: 1.5 }} data-testid="planner-action-queue-partial">
                From the first 500 cases of each list; more may be waiting.
              </Typography>
            ) : null}
            {items.map((i) => (
            <PanelRow
              key={i.key}
              severity={i.tone}
              primary={i.label}
              secondary={i.hint}
              onClick={() => onSelect(i.caseId)}
            />
            ))}
          </>
        )}
      </Stack>
    </Panel>
  );
}
