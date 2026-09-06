'use client';

import { Box, TextField } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import type { CaseScope } from '@/features/promotions-funding/caseScope';
import { apiGet } from '@/lib/api';

type CustomerPick = { id: number; customer_code: string; customer_name: string };
type DistributorPick = { id: number; distributor_code: string; distributor_name: string };
type ProductPick = { id: number; sku: string; name: string };

type Props = {
  scope: CaseScope;
  onPatch: (patch: Record<string, string | null>) => void;
};

const fieldSx = { minWidth: 148, maxWidth: 200 };

export function CaseScopeFilters({ scope, onPatch }: Props) {
  const [qDraft, setQDraft] = useState(scope.q);
  const [buDraft, setBuDraft] = useState(scope.bu);
  useEffect(() => setQDraft(scope.q), [scope.q]);
  useEffect(() => setBuDraft(scope.bu), [scope.bu]);
  useEffect(() => {
    const t = setTimeout(() => {
      if (qDraft !== scope.q) onPatch({ q: qDraft || null });
    }, 300);
    return () => clearTimeout(t);
  }, [qDraft, onPatch, scope.q]);
  useEffect(() => {
    const t = setTimeout(() => {
      if (buDraft !== scope.bu) onPatch({ bu: buDraft || null });
    }, 300);
    return () => clearTimeout(t);
  }, [buDraft, onPatch, scope.bu]);
  const { data: customerHydrate } = useQuery({
    queryKey: ['customers', 'hydrate', scope.customerId],
    queryFn: ({ signal }) =>
      apiGet<{ items: CustomerPick[] }>(
        `/api/v1/customers?page=1&page_size=1&customer_id=${scope.customerId}`,
        { signal },
      ),
    enabled: scope.customerId != null,
  });
  const { data: distributorHydrate } = useQuery({
    queryKey: ['distributors', 'hydrate', scope.distributorId],
    queryFn: ({ signal }) =>
      apiGet<DistributorPick>(`/api/v1/distributors/${scope.distributorId}`, { signal }),
    enabled: scope.distributorId != null,
  });
  const { data: productHydrate } = useQuery({
    queryKey: ['products', 'hydrate', scope.productId],
    queryFn: ({ signal }) =>
      apiGet<{ items: ProductPick[] }>(
        `/api/v1/products?page=1&page_size=1&product_id=${scope.productId}`,
        { signal },
      ),
    enabled: scope.productId != null,
  });

  const customer = useMemo<CustomerPick | null>(() => {
    if (scope.customerId == null) return null;
    return (
      customerHydrate?.items?.[0] ?? {
        id: scope.customerId,
        customer_code: String(scope.customerId),
        customer_name: '',
      }
    );
  }, [scope.customerId, customerHydrate]);

  const distributor = useMemo<DistributorPick | null>(() => {
    if (scope.distributorId == null) return null;
    if (distributorHydrate?.id === scope.distributorId) return distributorHydrate;
    return {
      id: scope.distributorId,
      distributor_code: String(scope.distributorId),
      distributor_name: '',
    };
  }, [scope.distributorId, distributorHydrate]);

  const product = useMemo<ProductPick | null>(() => {
    if (scope.productId == null) return null;
    return (
      productHydrate?.items?.[0] ?? {
        id: scope.productId,
        sku: String(scope.productId),
        name: '',
      }
    );
  }, [scope.productId, productHydrate]);

  return (
    <Box
      data-testid="case-scope-filters"
      sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, flex: '1 1 640px' }}
    >
      <TextField
        size="small"
        label="Find"
        placeholder="Code or name"
        value={qDraft}
        onChange={(e) => setQDraft(e.target.value)}
        sx={fieldSx}
        inputProps={{ 'data-testid': 'case-scope-q' }}
      />
      <Box sx={fieldSx}>
        <EntitySearchAutocomplete<CustomerPick>
          label="Customer"
          value={customer}
          onChange={(next) => onPatch({ customer_id: next ? String(next.id) : null })}
          getOptionLabel={(o) =>
            o.customer_name ? `${o.customer_code} — ${o.customer_name}` : o.customer_code
          }
          fetchOptions={async (query, signal) => {
            const needle = query.trim();
            const res = await apiGet<{ items: CustomerPick[] }>(
              `/api/v1/customers?page=1&page_size=25${needle ? `&q=${encodeURIComponent(needle)}` : ''}`,
              { signal },
            );
            return res.items ?? [];
          }}
        />
      </Box>
      <Box sx={fieldSx}>
        <EntitySearchAutocomplete<DistributorPick>
          label="Distributor"
          value={distributor}
          onChange={(next) => onPatch({ distributor_id: next ? String(next.id) : null })}
          getOptionLabel={(o) =>
            o.distributor_name ? `${o.distributor_code} — ${o.distributor_name}` : o.distributor_code
          }
          fetchOptions={async (query, signal) => {
            const needle = query.trim();
            const res = await apiGet<{ items: DistributorPick[] }>(
              `/api/v1/distributors?page=1&page_size=25${needle ? `&q=${encodeURIComponent(needle)}` : ''}`,
              { signal },
            );
            return res.items ?? [];
          }}
        />
      </Box>
      <Box sx={fieldSx}>
        <EntitySearchAutocomplete<ProductPick>
          label="Product"
          value={product}
          onChange={(next) => onPatch({ product_id: next ? String(next.id) : null })}
          getOptionLabel={(o) => (o.name ? `${o.sku} — ${o.name}` : o.sku)}
          fetchOptions={async (query, signal) => {
            const needle = query.trim();
            const res = await apiGet<{ items: ProductPick[] }>(
              `/api/v1/products?page=1&page_size=25${needle ? `&q=${encodeURIComponent(needle)}` : ''}`,
              { signal },
            );
            return res.items ?? [];
          }}
        />
      </Box>
      <TextField
        size="small"
        label="BU"
        placeholder="Business unit"
        value={buDraft}
        onChange={(e) => setBuDraft(e.target.value)}
        sx={{ minWidth: 120, maxWidth: 160 }}
        inputProps={{ 'data-testid': 'case-scope-bu' }}
      />
      <TextField
        size="small"
        type="date"
        label="From"
        InputLabelProps={{ shrink: true }}
        value={scope.windowFrom}
        onChange={(e) => onPatch({ window_from: e.target.value || null })}
        sx={{ minWidth: 140 }}
        inputProps={{ 'data-testid': 'case-scope-from' }}
      />
      <TextField
        size="small"
        type="date"
        label="To"
        InputLabelProps={{ shrink: true }}
        value={scope.windowTo}
        onChange={(e) => onPatch({ window_to: e.target.value || null })}
        sx={{ minWidth: 140 }}
        inputProps={{ 'data-testid': 'case-scope-to' }}
      />
    </Box>
  );
}
