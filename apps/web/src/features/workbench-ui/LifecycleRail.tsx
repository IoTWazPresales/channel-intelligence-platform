'use client';

import { Box, Stack, Tooltip, Typography } from '@mui/material';

/**
 * One object, one lifecycle. A promotion plan and a funding case are the same `cpor_case` row at
 * different stages; the rail makes that visible wherever the case appears (planner, case book,
 * case panel) so an operator never has to reconcile two vocabularies.
 */
export function LifecycleRail<T extends string>({
  stages,
  labels,
  current,
  counts,
  onSelect,
  dense = false,
}: {
  stages: T[];
  labels: Record<T, string> | Record<string, string>;
  current?: T;
  counts?: Partial<Record<T, number>> | Record<string, number>;
  onSelect?: (s: T) => void;
  dense?: boolean;
}) {
  const idx = current ? stages.indexOf(current) : -1;
  return (
    <Box
      role="list"
      aria-label="Lifecycle"
      data-testid="lifecycle-rail"
      sx={{ display: 'flex', alignItems: 'stretch', gap: 0.5, flexWrap: 'wrap' }}
    >
      {stages.map((s, i) => {
        const done = idx >= 0 && i < idx;
        const now = i === idx;
        const clickable = !!onSelect;
        const body = (
          <Box
            role="listitem"
            aria-current={now ? 'step' : undefined}
            onClick={clickable ? () => onSelect?.(s) : undefined}
            sx={{
              flex: '1 1 0',
              minWidth: dense ? 64 : 88,
              px: dense ? 1 : 1.5,
              py: dense ? 0.5 : 0.75,
              borderRadius: 1,
              cursor: clickable ? 'pointer' : 'default',
              bgcolor: now ? 'primary.main' : done ? 'action.selected' : 'transparent',
              color: now ? 'primary.contrastText' : done ? 'text.primary' : 'text.secondary',
              border: '1px solid',
              borderColor: now ? 'primary.main' : 'divider',
              transition: 'background-color 120ms',
              '&:hover': clickable ? { bgcolor: now ? 'primary.dark' : 'action.hover' } : undefined,
            }}
          >
            <Stack direction="row" alignItems="baseline" justifyContent="space-between" spacing={1}>
              <Typography variant={dense ? 'caption' : 'body2'} sx={{ fontWeight: now ? 650 : 500, lineHeight: 1.2 }}>
                {labels[s]}
              </Typography>
              {counts && counts[s] !== undefined ? (
                <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums', opacity: 0.85 }}>
                  {counts[s]}
                </Typography>
              ) : null}
            </Stack>
          </Box>
        );
        return clickable ? (
          <Tooltip key={s} title={`Show ${labels[s].toLowerCase()} cases`} arrow>
            {body}
          </Tooltip>
        ) : (
          <Box key={s} sx={{ display: 'contents' }}>
            {body}
          </Box>
        );
      })}
    </Box>
  );
}
