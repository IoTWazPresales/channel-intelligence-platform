'use client';

import { Autocomplete, Button, Chip, Stack, TextField, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { apiGet } from '@/lib/api';

import {
  customersListUrl,
  type ListingCustomerPick,
  searchCustomers,
  useListingCustomerScope,
} from './listingCustomerScope';

type Props = {
  testIdPrefix?: string;
};

export function ListingCustomerScopePicker({ testIdPrefix = 'listing-customer-scope' }: Props) {
  const scope = useListingCustomerScope();
  const [options, setOptions] = useState<ListingCustomerPick[]>([]);
  const [input, setInput] = useState('');
  const hydrateQ = useQuery({
    queryKey: ['customers', 'listing-scope-hydrate', scope.selectedIds.join(',')],
    queryFn: async ({ signal }) => {
      const missing = scope.selectedIds.filter((id) => !scope.labels.has(id));
      if (!missing.length) return [];
      const rows: ListingCustomerPick[] = [];
      for (const id of missing.slice(0, 20)) {
        const page = await apiGet<{ items?: ListingCustomerPick[] }>(
          customersListUrl(false, { customer_id: id }),
          { signal },
        );
        if (page.items?.[0]) rows.push(page.items[0]);
      }
      return rows;
    },
    enabled: scope.hydrated && scope.selectedIds.some((id) => !scope.labels.has(id)),
    staleTime: 60_000,
  });

  const nameById = useMemo(() => {
    const m = new Map(scope.labels);
    for (const c of hydrateQ.data ?? []) {
      m.set(c.id, (c.customer_name || c.customer_code || '').trim());
    }
    return m;
  }, [scope.labels, hydrateQ.data]);

  return (
    <Stack spacing={1} data-testid={testIdPrefix}>
      <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
        <Typography variant="body2" color="text.secondary">
          Customers in view
        </Typography>
        <Button size="small" variant="outlined" onClick={scope.resetToReporting} disabled={scope.reportingLoading}>
          Reporting default
        </Button>
      </Stack>
      <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap">
        {scope.selectedIds.map((id) => (
          <Chip
            key={id}
            size="small"
            label={nameById.get(id) ?? `Customer ${id}`}
            onDelete={() => scope.toggleCustomer(id, false)}
            data-testid={`${testIdPrefix}-chip-${id}`}
          />
        ))}
        {!scope.selectedIds.length ? (
          <Typography variant="body2" color="text.secondary">
            No customers selected.
          </Typography>
        ) : null}
      </Stack>
      <Autocomplete
        size="small"
        options={options.filter((o) => !scope.selectedIds.includes(o.id))}
        inputValue={input}
        onInputChange={(_, v, reason) => {
          setInput(v);
          if (reason === 'input' && v.trim().length >= 2) {
            void searchCustomers(v.trim(), new AbortController().signal).then(setOptions).catch(() => setOptions([]));
          }
        }}
        getOptionLabel={(o) => (o.customer_name || o.customer_code || '').trim()}
        onChange={(_, v) => {
          if (v) {
            scope.toggleCustomer(v.id, true);
            setInput('');
          }
        }}
        renderInput={(params) => (
          <TextField {...params} label="Add customer" placeholder="Search directory" data-testid={`${testIdPrefix}-add`} />
        )}
        sx={{ maxWidth: 360 }}
      />
    </Stack>
  );
}