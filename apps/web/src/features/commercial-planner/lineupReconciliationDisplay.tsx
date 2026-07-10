'use client';

import { Chip, Stack } from '@mui/material';

export type ReconSummary = {
  matched?: number;
  short?: number;
  over?: number;
  unshipped?: number;
  unplanned?: number;
  amended?: number;
  po_no_match?: number;
};

export type ReconCustomerSlice = {
  customer_id: number | null;
  label: string;
  awaiting_po?: boolean;
  summary: ReconSummary;
};

const FLAG_ORDER: (keyof ReconSummary)[] = [
  'matched',
  'short',
  'over',
  'unshipped',
  'unplanned',
  'amended',
  'po_no_match',
];

const FLAG_COLORS: Record<string, 'success' | 'warning' | 'error' | 'info' | 'default'> = {
  matched: 'success',
  short: 'warning',
  over: 'warning',
  unshipped: 'error',
  unplanned: 'info',
  amended: 'info',
  po_no_match: 'error',
};

const FLAG_LABELS: Record<string, string> = {
  matched: 'matched',
  short: 'short',
  over: 'over',
  unshipped: 'unshipped',
  unplanned: 'unplanned',
  amended: 'amended',
  po_no_match: 'po no match',
};

export function formatCustomerReconChipLabel(slice: ReconCustomerSlice): string {
  if (slice.awaiting_po) {
    return `${slice.label}: awaiting PO`;
  }
  const active = FLAG_ORDER.filter((f) => (slice.summary[f] ?? 0) > 0);
  if (!active.length) {
    return `${slice.label}: no shipments`;
  }
  return `${slice.label}: ${active.map((f) => `${slice.summary[f]} ${FLAG_LABELS[f] ?? f}`).join(' · ')}`;
}

export function ReconSummaryChips({ summary }: { summary: ReconSummary }) {
  const items = FLAG_ORDER.map((key) => ({
    key,
    label: FLAG_LABELS[key] ?? key,
    color: FLAG_COLORS[key] ?? 'default',
  }));
  const active = items.filter((it) => (summary[it.key] ?? 0) > 0);
  if (!active.length) {
    return <Chip size="small" variant="outlined" label="No reconciled lines yet" />;
  }
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
      {active.map((it) => (
        <Chip key={it.key} size="small" color={it.color as 'success'} label={`${summary[it.key]} ${it.label}`} />
      ))}
    </Stack>
  );
}

export function CustomerReconChips({
  customers,
  testIdPrefix,
}: {
  customers: ReconCustomerSlice[];
  testIdPrefix?: string;
}) {
  if (!customers.length) return null;
  return (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap data-testid={testIdPrefix}>
      {customers.map((c) => (
        <Chip
          key={c.customer_id ?? 'unattributed'}
          size="small"
          variant={c.awaiting_po ? 'outlined' : 'filled'}
          color={c.awaiting_po ? 'warning' : 'default'}
          label={formatCustomerReconChipLabel(c)}
          data-testid={testIdPrefix ? `${testIdPrefix}-${c.customer_id ?? 'unattributed'}` : undefined}
        />
      ))}
    </Stack>
  );
}
