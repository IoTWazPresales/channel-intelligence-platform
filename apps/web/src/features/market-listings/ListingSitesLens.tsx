'use client';

import {
  Alert,
  Button,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from '@/lib/api';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

type Seller = {
  customer_id: number;
  customer_name: string | null;
  customer_code: string | null;
  seller_names: string[];
  seller_ids: string[];
};

type SiteRow = {
  id: number;
  site_key: string;
  display_name: string;
  adapter_key: string | null;
  product_url_pattern: string | null;
  page_id_pattern: string | null;
  search_url_pattern: string | null;
  details_url_pattern: string | null;
  first_party_seller: string | null;
  rate_limit_seconds: number | null;
  is_active: boolean;
  configured: boolean;
  missing_fields: string[];
  sellers: Seller[];
};

type SiteResponse = { items: SiteRow[]; adapter_keys: string[]; data_unavailable?: boolean };
type CustomerPick = { id: number; customer_code: string; customer_name: string };

const EMPTY = {
  display_name: '',
  adapter_key: '',
  product_url_pattern: '',
  page_id_pattern: '',
  search_url_pattern: '',
  details_url_pattern: '',
  first_party_seller: '',
  rate_limit_seconds: '',
};

export function ListingSitesLens() {
  const qc = useQueryClient();
  const me = useCurrentUser();
  const canEdit = me.data?.role === 'admin' || me.data?.role === 'steward';
  const sites = useQuery({
    queryKey: ['listing-capture', 'sites'],
    queryFn: ({ signal }) => apiGet<SiteResponse>('/api/v1/listing-capture/sites', { signal }),
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draft, setDraft] = useState(EMPTY);
  const [newKey, setNewKey] = useState('');
  const [customer, setCustomer] = useState<CustomerPick | null>(null);
  const [names, setNames] = useState('');
  const [ids, setIds] = useState('');
  const [error, setError] = useState<string | null>(null);

  const rows = sites.data?.items ?? [];
  const selected = rows.find((r) => r.id === selectedId) ?? null;

  function load(row: SiteRow) {
    setSelectedId(row.id);
    setDraft({
      display_name: row.display_name,
      adapter_key: row.adapter_key ?? '',
      product_url_pattern: row.product_url_pattern ?? '',
      page_id_pattern: row.page_id_pattern ?? '',
      search_url_pattern: row.search_url_pattern ?? '',
      details_url_pattern: row.details_url_pattern ?? '',
      first_party_seller: row.first_party_seller ?? '',
      rate_limit_seconds: row.rate_limit_seconds == null ? '' : String(row.rate_limit_seconds),
    });
    setError(null);
  }

  const save = useMutation({
    mutationFn: () =>
      apiPatch<SiteRow>(`/api/v1/listing-capture/sites/${selectedId}`, {
        ...draft,
        adapter_key: draft.adapter_key || null,
        rate_limit_seconds: draft.rate_limit_seconds === '' ? null : Number(draft.rate_limit_seconds),
      }),
    onSuccess: async () => {
      setError(null);
      await qc.invalidateQueries({ queryKey: ['listing-capture', 'sites'] });
    },
    onError: (e: Error) => setError(e.message),
  });
  const create = useMutation({
    mutationFn: () => apiPost<SiteRow>('/api/v1/listing-capture/sites', { site_key: newKey, display_name: newKey }),
    onSuccess: async (row) => {
      setNewKey('');
      await qc.invalidateQueries({ queryKey: ['listing-capture', 'sites'] });
      load(row);
    },
    onError: (e: Error) => setError(e.message),
  });
  const saveSeller = useMutation({
    mutationFn: () =>
      apiPut<SiteRow>(`/api/v1/listing-capture/sites/${selectedId}/sellers/${customer?.id}`, {
        seller_names: names.split(',').map((s) => s.trim()).filter(Boolean),
        seller_ids: ids.split(',').map((s) => s.trim()).filter(Boolean),
      }),
    onSuccess: async () => {
      setNames('');
      setIds('');
      setCustomer(null);
      await qc.invalidateQueries({ queryKey: ['listing-capture', 'sites'] });
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="listing-sites-lens">
      <Typography variant="body2" color="text.secondary">
        Sites, link patterns and each customer&apos;s own seller name on a site are saved here. A site with no page
        reader is not fetched. Nothing on this page is a fixed list in the code.
      </Typography>
      {sites.data?.data_unavailable ? <Alert severity="warning">Sites could not be loaded.</Alert> : null}
      {error ? <Alert severity="error">{error}</Alert> : null}
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
        {rows.map((row) => (
          <Button
            key={row.id}
            size="small"
            variant={row.id === selectedId ? 'contained' : 'outlined'}
            onClick={() => load(row)}
            data-testid={`listing-site-${row.site_key}`}
          >
            {row.display_name}
            {row.configured ? '' : ' · not configured'}
          </Button>
        ))}
      </Stack>
      {canEdit ? (
        <Stack direction="row" spacing={1}>
          <TextField
            size="small"
            label="New site key"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            data-testid="listing-site-new-key"
          />
          <Button variant="outlined" disabled={!newKey.trim() || create.isPending} onClick={() => create.mutate()}>
            Add site
          </Button>
        </Stack>
      ) : (
        <Typography variant="caption" color="text.secondary">
          A steward edits sites and sellers.
        </Typography>
      )}
      {selected && canEdit ? (
        <Stack spacing={1.25} data-testid="listing-site-editor">
          <Typography variant="subtitle2">{selected.site_key}</Typography>
          {(
            [
              ['display_name', 'Display name'],
              ['product_url_pattern', 'Product link pattern ({page_id})'],
              ['page_id_pattern', 'Page id pattern (one capture group)'],
              ['search_url_pattern', 'Search pattern ({query})'],
              ['details_url_pattern', 'Details pattern ({page_id})'],
              ['first_party_seller', 'Seller name for the site’s own stock'],
              ['rate_limit_seconds', 'Seconds between requests'],
            ] as const
          ).map(([key, label]) => (
            <TextField
              key={key}
              size="small"
              label={label}
              value={draft[key]}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
            />
          ))}
          <TextField
            select
            size="small"
            label="Page reader"
            value={draft.adapter_key}
            onChange={(e) => setDraft({ ...draft, adapter_key: e.target.value })}
            data-testid="listing-site-adapter"
          >
            <MenuItem value="">None</MenuItem>
            {(sites.data?.adapter_keys ?? []).map((key) => (
              <MenuItem key={key} value={key}>
                {key}
              </MenuItem>
            ))}
          </TextField>
          <Button variant="contained" disabled={save.isPending} onClick={() => save.mutate()} data-testid="listing-site-save">
            Save site
          </Button>
          <Typography variant="subtitle2">Own sellers</Typography>
          {selected.sellers.map((s) => (
            <Stack key={s.customer_id} direction="row" spacing={1} alignItems="center">
              <Typography variant="body2" sx={{ flex: 1 }}>
                {s.customer_name || s.customer_code || s.customer_id}: {s.seller_names.join(', ') || s.seller_ids.join(', ')}
              </Typography>
              <Button
                size="small"
                onClick={() =>
                  apiDelete(`/api/v1/listing-capture/sites/${selected.id}/sellers/${s.customer_id}`).then(() =>
                    qc.invalidateQueries({ queryKey: ['listing-capture', 'sites'] }),
                  )
                }
              >
                Remove
              </Button>
            </Stack>
          ))}
          <EntitySearchAutocomplete<CustomerPick>
            label="Customer"
            value={customer}
            onChange={setCustomer}
            fetchOptions={async (q, signal) => {
              const page = await apiGet<{ items?: CustomerPick[] }>(
                `/api/v1/customers?page=1&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ''}`,
                { signal },
              );
              return page.items ?? [];
            }}
            getOptionLabel={(o) => o.customer_name || o.customer_code}
          />
          <TextField size="small" label="Seller names (comma separated)" value={names} onChange={(e) => setNames(e.target.value)} />
          <TextField size="small" label="Seller ids (comma separated)" value={ids} onChange={(e) => setIds(e.target.value)} />
          <Button
            variant="outlined"
            disabled={!customer || saveSeller.isPending}
            onClick={() => saveSeller.mutate()}
            data-testid="listing-site-save-seller"
          >
            Save seller
          </Button>
        </Stack>
      ) : null}
      {!sites.isLoading && rows.length === 0 ? (
        <Typography variant="body2" data-testid="listing-sites-empty">
          No sites yet.
        </Typography>
      ) : null}
    </Stack>
  );
}
