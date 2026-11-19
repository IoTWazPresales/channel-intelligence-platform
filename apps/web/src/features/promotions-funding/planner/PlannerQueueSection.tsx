'use client';

import { Alert, Box, Button, Stack, Typography } from '@mui/material';

import type { ActionItem } from '@/features/promotions-funding/plannerLayout/actionQueue';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

import { NOT_AVAILABLE_YET } from './PlannerKpiCard';

export type PlannerQueueCard = {
  key: string;
  label: string;
  /** Real figure; null while it does not exist. Ignored unless `state` is `ready`. */
  value: number | null;
  /** ready / loading / empty (the request failed) / unavailable (no source exists yet). */
  state: 'ready' | 'loading' | 'empty' | 'unavailable';
  /** The one-line caption (ready) or reason (unavailable). */
  caption: string;
  tone?: 'warning' | 'neutral';
  onClick?: () => void;
};

/**
 * The action queue under the timeline: five cards (Overdue approvals, Low stock risk, Funding gaps,
 * Evidence outstanding, Conflicting windows), then the list of cases that wait on a person.
 */
export function PlannerQueueSection({
  cards,
  items,
  loading = false,
  unavailable = [],
  incomplete = false,
  onRetry,
  onSelect,
}: {
  cards: readonly PlannerQueueCard[];
  items: readonly ActionItem[];
  loading?: boolean;
  /** Names of the source lists that failed to load; the queue is then incomplete, never confirmed empty. */
  unavailable?: readonly string[];
  /** A source list returned only its first page: a partial view, never confirmed empty. */
  incomplete?: boolean;
  onRetry?: () => void;
  onSelect: (caseId: number) => void;
}) {
  return (
    <Box data-testid="planner-queue-section" id="planner-action-queue">
      <Panel title="Action queue" subtitle="What needs a person: approvals, stock, funding, evidence and clashes" flush>
        <Box
          data-testid="planner-queue-cards"
          sx={{
            display: 'grid',
            gap: 1,
            px: 1,
            pb: 1,
            gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(3, minmax(0, 1fr))', lg: 'repeat(5, minmax(0, 1fr))' },
          }}
        >
          {cards.map((c) => {
            const interactive = Boolean(c.onClick) && c.state !== 'unavailable';
            const warn = c.tone === 'warning' && c.state === 'ready' && (c.value ?? 0) > 0;
            return (
              <Box
                key={c.key}
                component="button"
                type="button"
                data-testid={`planner-queue-card-${c.key}`}
                data-state={c.state}
                onClick={interactive ? c.onClick : undefined}
                disabled={!interactive}
                sx={{
                  textAlign: 'left',
                  p: 1,
                  borderRadius: 1,
                  border: 1,
                  borderColor: warn ? 'warning.main' : 'divider',
                  bgcolor: 'background.paper',
                  color: 'text.primary',
                  font: 'inherit',
                  minWidth: 0,
                  cursor: interactive ? 'pointer' : 'default',
                }}
              >
                <Typography variant="caption" color="text.secondary" component="span" data-testid="queue-label" sx={{ display: 'block' }}>
                  {c.label}
                </Typography>
                <Typography
                  variant={c.state === 'unavailable' ? 'body2' : 'h6'}
                  component="span"
                  data-testid="queue-value"
                  sx={{ display: 'block', lineHeight: 1.3, fontWeight: 600, color: c.state === 'ready' ? 'text.primary' : 'text.secondary' }}
                >
                  {c.state === 'unavailable'
                    ? NOT_AVAILABLE_YET
                    : c.state === 'loading'
                      ? '…'
                      : c.state === 'empty' || c.value == null
                        ? '—'
                        : c.value}
                </Typography>
                <Typography variant="caption" color="text.secondary" component="span" data-testid="queue-note" sx={{ display: 'block' }}>
                  {c.caption}
                </Typography>
              </Box>
            );
          })}
        </Box>
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
                <PanelRow key={i.key} severity={i.tone} primary={i.label} secondary={i.hint} onClick={() => onSelect(i.caseId)} />
              ))}
            </>
          )}
        </Stack>
      </Panel>
    </Box>
  );
}
