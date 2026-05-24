'use client';

import {
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';

export type DsiCustomerSearchHit = {
  id: number;
  customer_code: string;
  customer_name: string;
};

export function DsiCustomerSearchFields({
  searchQuery,
  onSearchQueryChange,
  customerId,
  onCustomerIdChange,
  searchLabel = 'Search customers',
  selectLabel = 'Customer',
  selectTestId,
  searchTestId,
  helperText = 'Type at least 2 characters',
  size = 'small',
}: {
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  customerId: number | '';
  onCustomerIdChange: (id: number | '') => void;
  searchLabel?: string;
  selectLabel?: string;
  selectTestId?: string;
  searchTestId?: string;
  helperText?: string;
  size?: 'small' | 'medium';
}) {
  const { data: hits = [] } = useQuery({
    queryKey: ['customers-search', searchQuery],
    queryFn: ({ signal }) =>
      apiGet<{ items: DsiCustomerSearchHit[] }>(
        `/api/v1/customers?q=${encodeURIComponent(searchQuery)}&page_size=20`,
        { signal }
      ),
    enabled: searchQuery.trim().length >= 2,
    select: (r) => r.items ?? [],
  });

  return (
    <Stack spacing={1}>
      <TextField
        label={searchLabel}
        value={searchQuery}
        onChange={(e) => onSearchQueryChange(e.target.value)}
        helperText={helperText}
        fullWidth
        size={size}
        inputProps={searchTestId ? { 'data-testid': searchTestId } : undefined}
      />
      <FormControl fullWidth size={size}>
        <InputLabel id="dsi-cust-search-select">{selectLabel}</InputLabel>
        <Select
          labelId="dsi-cust-search-select"
          label={selectLabel}
          value={customerId === '' ? '' : String(customerId)}
          onChange={(e) => onCustomerIdChange(e.target.value === '' ? '' : Number(e.target.value))}
          data-testid={selectTestId}
        >
          {customerId !== '' &&
          !hits.some((c) => c.id === customerId) ? (
            <MenuItem value={String(customerId)}>
              Customer id {customerId} (selected)
            </MenuItem>
          ) : null}
          {hits.map((c) => (
            <MenuItem key={c.id} value={String(c.id)}>
              {c.customer_code} — {c.customer_name}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
      {customerId !== '' && hits.length === 0 && searchQuery.trim().length < 2 ? (
        <Typography variant="caption" color="text.secondary">
          Selected customer id {String(customerId)}. Search to change selection.
        </Typography>
      ) : null}
    </Stack>
  );
}
