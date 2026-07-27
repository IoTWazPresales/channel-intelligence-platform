'use client';

import { Alert, Box, Button, Chip, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';

import {
  confidenceBand,
  confidenceBandColor,
  confidenceBandLabel,
  type ConfidenceBand,
} from './confidenceBand';

export type StewardSuggestionCardItem = {
  targetId: number;
  label: string;
  score?: number | null;
  reason?: string | null;
  /** Precomputed band; if omitted, derived from score via shared confidenceBand. */
  band?: ConfidenceBand | null;
  onMap: (targetId: number) => void;
  mapPending?: boolean;
  mapDisabled?: boolean;
};

/**
 * Shared S7 ranked suggestion cards — neutral props only (D-017).
 * Renders 1..N cards; empty state points operators to override search (never auto-create).
 */
export function StewardSuggestionCards({
  suggestions,
  overrideSlot,
  title = 'Suggested masters',
  emptyMessage = 'No ranked suggestions for this token. Search an existing master below — never auto-created.',
  mapLabel = 'Map to this master',
  mapPendingLabel = 'Mapping…',
  testId = 'steward-suggestion-cards',
}: {
  suggestions: StewardSuggestionCardItem[];
  overrideSlot?: ReactNode;
  title?: string;
  emptyMessage?: string;
  mapLabel?: string;
  mapPendingLabel?: string;
  testId?: string;
}) {
  return (
    <Stack spacing={1.5} data-testid={testId}>
      <Box data-testid={`${testId}-list`}>
        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          {title}
        </Typography>
        {suggestions.length === 0 ? (
          <Alert severity="info" data-testid={`${testId}-empty`}>
            {emptyMessage}
          </Alert>
        ) : (
          <Stack spacing={1}>
            {suggestions.map((s) => {
              const band = s.band ?? confidenceBand(s.score);
              return (
                <Box
                  key={`${s.targetId}-${s.reason ?? ''}-${s.label}`}
                  sx={{
                    border: 1,
                    borderColor: 'divider',
                    borderRadius: 1,
                    p: 1.25,
                  }}
                  data-testid={`${testId}-item-${s.targetId}`}
                >
                  <Stack spacing={0.75}>
                    <Typography variant="body2" sx={{ fontWeight: 600, wordBreak: 'break-word' }}>
                      {s.label}
                    </Typography>
                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                      {band ? (
                        <Chip
                          size="small"
                          variant="outlined"
                          color={confidenceBandColor(band)}
                          label={confidenceBandLabel(band)}
                        />
                      ) : null}
                      {s.score != null && !Number.isNaN(Number(s.score)) ? (
                        <Chip size="small" variant="outlined" label={`score ${Number(s.score).toFixed(2)}`} />
                      ) : null}
                      {s.reason ? (
                        <Chip size="small" variant="outlined" label={s.reason} />
                      ) : null}
                    </Stack>
                    <Button
                      size="small"
                      variant="contained"
                      disabled={Boolean(s.mapDisabled || s.mapPending)}
                      onClick={() => s.onMap(s.targetId)}
                      data-testid={`${testId}-map-${s.targetId}`}
                    >
                      {s.mapPending ? mapPendingLabel : mapLabel}
                    </Button>
                  </Stack>
                </Box>
              );
            })}
          </Stack>
        )}
      </Box>
      {overrideSlot ? <Box data-testid={`${testId}-override`}>{overrideSlot}</Box> : null}
    </Stack>
  );
}
