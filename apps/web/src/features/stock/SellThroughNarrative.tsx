'use client';

import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import { Alert, Box, Button, CircularProgress, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet, safeDisplayError } from '@/lib/api';

import type { SellThroughOverview } from './sellThroughTypes';

type Narrative = {
  source: 'ai' | 'rules';
  text: string;
  reason?: string;
  model?: string;
  cached?: boolean;
};

/**
 * Summary at the top of the Sell-through tab (Warren 2026-10-19). The sentences built from the
 * computed numbers always show. "Write AI summary" asks the server for one short AI-worded summary
 * of the same view; it is cached per view, and falls back to the rules when AI is not set up.
 */
export function SellThroughNarrative({ overview, query }: { overview: SellThroughOverview; query: string }) {
  const [asked, setAsked] = useState<string | null>(null);
  const ai = useQuery({
    queryKey: ['sell-through', 'narrative', asked],
    queryFn: ({ signal }) => apiGet<Narrative>(`/api/v1/sell-through/narrative?${asked}`, { signal }),
    enabled: asked != null,
    staleTime: 30 * 60_000,
  });
  const showingAi = asked === query && ai.data?.source === 'ai';

  return (
    <Box
      data-testid="sellthrough-summary"
      sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 1.5, p: 1.5, bgcolor: 'background.paper' }}
    >
      <Stack direction="row" spacing={1} alignItems="flex-start">
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {showingAi ? (
            <>
              <Typography variant="body2">{ai.data?.text}</Typography>
              <Typography variant="caption" color="text.secondary">
                AI summary of the numbers on this page{ai.data?.cached ? ' (saved earlier)' : ''}. Check figures below.
              </Typography>
            </>
          ) : overview.summary.length ? (
            <Box component="ul" sx={{ m: 0, pl: 2.25 }}>
              {overview.summary.map((s) => (
                <li key={s}>
                  <Typography variant="body2">{s}</Typography>
                </li>
              ))}
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No sell-through in this window for these filters.
            </Typography>
          )}
          {asked === query && ai.data?.source === 'rules' && ai.data.reason ? (
            <Typography variant="caption" color="text.secondary" display="block">
              AI summary not available: {ai.data.reason}.
            </Typography>
          ) : null}
          {ai.isError ? <Alert severity="warning" sx={{ mt: 1 }}>{safeDisplayError(ai.error)}</Alert> : null}
        </Box>
        <Button
          size="small"
          variant="outlined"
          startIcon={ai.isFetching ? <CircularProgress size={14} /> : <AutoAwesomeOutlinedIcon fontSize="small" />}
          disabled={ai.isFetching || !overview.summary.length}
          onClick={() => setAsked(query)}
          data-testid="sellthrough-ai-summary"
          sx={{ flexShrink: 0 }}
        >
          {showingAi ? 'AI summary' : 'Write AI summary'}
        </Button>
      </Stack>
    </Box>
  );
}
