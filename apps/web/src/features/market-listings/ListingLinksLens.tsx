'use client';

import { Alert, Button, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

type Candidate = { url?: string; title?: string | null; page_id?: string };
type QueueItem = {
  id: number;
  site_id: number;
  product_id: number;
  listing_id: number | null;
  reason: string;
  candidates: Candidate[];
  status: string;
};

const REASON: Record<string, string> = {
  ambiguous: 'More than one page matched',
  no_match: 'No page matched',
  not_corroborated: 'The page was a different product',
  stale: 'The saved link now shows a different product',
};

export function ListingLinksLens() {
  const qc = useQueryClient();
  const me = useCurrentUser();
  const canEdit = me.data?.role === 'admin' || me.data?.role === 'steward';
  const queue = useQuery({
    queryKey: ['listing-capture', 'link-queue'],
    queryFn: ({ signal }) => apiGet<{ items: QueueItem[]; data_unavailable?: boolean }>('/api/v1/listing-capture/link-queue', { signal }),
  });
  const [urls, setUrls] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const decide = useMutation({
    mutationFn: (body: { id: number; action: string; url?: string }) =>
      apiPost(`/api/v1/listing-capture/link-queue/${body.id}`, { action: body.action, url: body.url || null }),
    onSuccess: async () => {
      setError(null);
      await qc.invalidateQueries({ queryKey: ['listing-capture', 'link-queue'] });
    },
    onError: (e: Error) => setError(e.message),
  });
  const items = queue.data?.items ?? [];

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="listing-links-lens">
      <Typography variant="body2" color="text.secondary">
        A link is learned from the page (barcode, then model) and remembered. A report stock code is never the link.
        Confirm once, or reject it, or say the product is not on this site. A reject is remembered too.
      </Typography>
      {error ? <Alert severity="error">{error}</Alert> : null}
      {queue.data?.data_unavailable ? <Alert severity="warning">The link queue could not be loaded.</Alert> : null}
      {!queue.isLoading && items.length === 0 ? (
        <Typography variant="body2" data-testid="listing-links-empty">
          Nothing waiting.
        </Typography>
      ) : null}
      {items.map((item) => (
        <Stack key={item.id} spacing={1} data-testid={`listing-link-${item.id}`} sx={{ border: 1, borderColor: 'divider', p: 1.5 }}>
          <Typography variant="subtitle2">
            Product {item.product_id} · {REASON[item.reason] ?? item.reason}
          </Typography>
          {(item.candidates || []).map((c) => (
            <Typography key={c.url} variant="body2" sx={{ wordBreak: 'break-all' }}>
              {c.title ? `${c.title} — ` : ''}
              {c.url}
            </Typography>
          ))}
          {canEdit ? (
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
              <TextField
                size="small"
                label="Product page link"
                value={urls[item.id] ?? item.candidates?.[0]?.url ?? ''}
                onChange={(e) => setUrls({ ...urls, [item.id]: e.target.value })}
                sx={{ minWidth: 280, flex: 1 }}
              />
              <Button
                size="small"
                variant="contained"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: item.id, action: 'confirm', url: urls[item.id] ?? item.candidates?.[0]?.url })}
              >
                Confirm
              </Button>
              <Button
                size="small"
                variant="outlined"
                disabled={decide.isPending}
                onClick={() => decide.mutate({ id: item.id, action: 'reject', url: urls[item.id] ?? item.candidates?.[0]?.url })}
              >
                Reject
              </Button>
              <Button size="small" disabled={decide.isPending} onClick={() => decide.mutate({ id: item.id, action: 'not_on_site' })}>
                Not on this site
              </Button>
            </Stack>
          ) : null}
        </Stack>
      ))}
    </Stack>
  );
}
