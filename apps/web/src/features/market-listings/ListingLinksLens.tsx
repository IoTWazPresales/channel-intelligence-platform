'use client';

import { Alert, Box, Button, Stack, TextField, Typography } from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { apiGet, apiPost } from '@/lib/api';

import {
  discoveryError, fetchProducts, type PageFacts, type ProductPick, productLabel,
} from './discoveryApi';
import { DiscoveryPageLink } from './DiscoveryPreview';

type Candidate = {
  url?: string;
  title?: string | null;
  page_id?: string;
  product_id?: number;
  label?: string;
};
type QueueItem = {
  id: number;
  site_id: number;
  product_id: number | null;
  product_label?: string | null;
  customer_name?: string | null;
  listing_id: number | null;
  listing_url?: string | null;
  reason: string;
  candidates: Candidate[];
  evidence?: { facts?: PageFacts; title?: string; http_status?: number };
  status: string;
};
type Decision = { id: number; action: string; url?: string; product_id?: number };

const REASON: Record<string, string> = {
  ambiguous: 'More than one page matched',
  no_match: 'No page matched',
  not_corroborated: 'The page was a different product',
  stale: 'The saved link now shows a different product',
  ambiguous_identity: 'More than one product matched',
  no_identity_on_page: 'No barcode or model was found on the page',
  page_unreadable: 'The page could not be read',
  identity_mismatch: 'The page matched a different product',
};

function ProductActions({ item, pending, decide }: {
  item: QueueItem;
  pending: boolean;
  decide: (body: Decision) => void;
}) {
  const [product, setProduct] = useState<ProductPick | null>(null);
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        {item.candidates.filter((candidate) => candidate.product_id != null).map((candidate) => (
          <Button key={candidate.product_id} variant="outlined" size="small" disabled={pending}
            onClick={() => decide({ id: item.id, action: 'link_product', product_id: candidate.product_id })}>
            Link to {candidate.label || 'suggested product'}
          </Button>
        ))}
      </Stack>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'flex-start' }}>
        <Box sx={{ minWidth: 240, flex: 1 }}>
          <EntitySearchAutocomplete<ProductPick> label="Find a product" size="small"
            value={product} onChange={setProduct} fetchOptions={fetchProducts}
            getOptionLabel={productLabel} disabled={pending} />
        </Box>
        <Button size="small" variant="contained" disabled={pending || !product}
          onClick={() => product && decide({ id: item.id, action: 'link_product', product_id: product.id })}>
          Link selected product
        </Button>
        <Button size="small" disabled={pending} onClick={() => decide({ id: item.id, action: 'not_on_site' })}>
          Not on this site
        </Button>
      </Stack>
    </Stack>
  );
}

export function ListingLinksLens() {
  const qc = useQueryClient();
  const me = useCurrentUser();
  const canEdit = me.data?.role === 'admin' || me.data?.role === 'steward';
  const queue = useQuery({
    queryKey: ['listing-capture', 'link-queue'],
    queryFn: ({ signal }) => apiGet<{ items: QueueItem[]; data_unavailable?: boolean }>('/api/v1/listing-capture/link-queue', { signal }),
  });
  const [urls, setUrls] = useState<Record<number, string>>({});
  const decide = useMutation({
    mutationFn: ({ id, action, url, product_id }: Decision) =>
      apiPost(`/api/v1/listing-capture/link-queue/${id}`, {
        action,
        ...(product_id != null ? { product_id } : { url: url || null }),
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['listing-capture'] });
    },
  });
  const items = queue.data?.items ?? [];

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="listing-links-lens">
      <Typography variant="body2" color="text.secondary">
        Links use the page’s barcode or model. A report stock code is never a product match.
        Review the evidence, then confirm a page or choose the product it belongs to.
      </Typography>
      {decide.isError ? <Alert severity="error">{discoveryError(decide.error)}</Alert> : null}
      {queue.isLoading ? <Typography variant="body2">Loading link queue…</Typography> : null}
      {queue.isError || queue.data?.data_unavailable ? (
        <Alert severity="warning" action={<Button color="inherit" onClick={() => void queue.refetch()}>Retry</Button>}>
          The link queue could not be loaded.
        </Alert>
      ) : null}
      {queue.isSuccess && !queue.data.data_unavailable && items.length === 0 ? (
        <Typography variant="body2" data-testid="listing-links-empty">Nothing waiting.</Typography>
      ) : null}
      {items.map((item) => {
        const selectedUrl = urls[item.id] ?? item.candidates.find((candidate) => candidate.url)?.url ?? '';
        return (
          <Stack key={item.id} spacing={1} data-testid={`listing-link-${item.id}`}
            sx={{ border: 1, borderColor: 'divider', p: 1.5 }}>
            {item.customer_name ? <Typography variant="subtitle2">{item.customer_name}</Typography> : null}
            {item.product_id == null ? (
              <>
                <Typography variant="subtitle2">Listing has no product — {REASON[item.reason] ?? item.reason}</Typography>
                <DiscoveryPageLink url={item.listing_url} />
              </>
            ) : <Typography variant="subtitle2">{item.product_label || `Product ${item.product_id}`} — {REASON[item.reason] ?? item.reason}</Typography>}
            {item.evidence?.title ? <Typography variant="body2">{item.evidence.title}</Typography> : null}
            {item.evidence?.http_status != null ? <Typography variant="caption">Page response: {item.evidence.http_status}</Typography> : null}
            {item.evidence?.facts?.barcodes?.length ? <Typography variant="caption">Barcodes: {item.evidence.facts.barcodes.join(', ')}</Typography> : null}
            {item.evidence?.facts?.models?.length ? <Typography variant="caption">Models: {item.evidence.facts.models.join(', ')}</Typography> : null}
            {item.candidates.map((candidate, index) => (
              <Stack key={`${candidate.product_id ?? candidate.url}-${index}`} spacing={0.5}>
                {candidate.label || candidate.title ? <Typography variant="body2">{candidate.label || candidate.title}</Typography> : null}
                {candidate.url ? <DiscoveryPageLink url={candidate.url} /> : null}
              </Stack>
            ))}
            {canEdit ? item.product_id == null ? (
              <ProductActions item={item} pending={decide.isPending} decide={(body) => decide.mutate(body)} />
            ) : (
              <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                <TextField size="small" label="Product page link" value={selectedUrl}
                  onChange={(event) => setUrls({ ...urls, [item.id]: event.target.value })}
                  sx={{ minWidth: 280, flex: 1 }} />
                <Button size="small" variant="contained" disabled={decide.isPending || !selectedUrl.trim()}
                  onClick={() => decide.mutate({ id: item.id, action: 'confirm', url: selectedUrl })}>Confirm</Button>
                <Button size="small" variant="outlined" disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: item.id, action: 'reject', url: selectedUrl })}>Reject</Button>
                <Button size="small" disabled={decide.isPending}
                  onClick={() => decide.mutate({ id: item.id, action: 'not_on_site' })}>Not on this site</Button>
              </Stack>
            ) : null}
          </Stack>
        );
      })}
    </Stack>
  );
}
