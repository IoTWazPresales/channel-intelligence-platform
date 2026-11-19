'use client';

import { Alert, Box, Button, Chip, LinearProgress, Link, Paper, Stack, TextField, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { EntitySearchAutocomplete } from '@/features/commercial-planner/EntitySearchAutocomplete';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { apiGet } from '@/lib/api';
import { CalendarUploadPanel } from './CalendarUploadPanel';
import { barPosition, dateAxis, isoDay } from './timelineAxis';
import type { Timeline } from './types';

type Customer = { id: number; customer_name: string; customer_code: string };
const customerLabel = (c: Customer) => `${c.customer_code} - ${c.customer_name}`;
async function findCustomers(q: string, signal: AbortSignal) {
  const page = await apiGet<{ items: Customer[] }>(`/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q.trim())}`, { signal });
  return page.items;
}
const rowGrid = { display: 'grid', gridTemplateColumns: '240px minmax(460px, 1fr)', alignItems: 'center', gap: 2 };

export function TimelineRows({ timeline, from, to }: { timeline: Timeline; from?: string; to?: string }) {
  if (timeline.data_unavailable) return <Alert severity="info">{timeline.message ?? 'Customer calendar data is unavailable.'}</Alert>;
  const axis = dateAxis(
    [...timeline.promotions.map(p => p.window_start), ...timeline.calendar_events.map(e => e.start_date)],
    [...timeline.promotions.map(p => p.window_end), ...timeline.calendar_events.map(e => e.end_date)],
    from || timeline.from, to || timeline.to,
  );
  const clashCases = new Set(timeline.clashes.map(c => c.case_id));
  const clashEvents = new Set(timeline.clashes.map(c => c.event_id));
  const ticks = [...new Set([0, 0.25, 0.5, 0.75, 1].map(f => isoDay(axis.start + Math.round((axis.days - 1) * f))))];
  function row(id: string, label: React.ReactNode, start: string, end: string, clash: boolean, color: string) {
    const pos = barPosition(start, end, axis);
    return <Box key={id} sx={{ ...rowGrid, py: 1, borderBottom: '1px solid', borderColor: 'divider' }}
      data-testid={id} data-clash={String(clash)}>
      <Box>{label}<Typography variant="caption" display="block">{start} to {end}</Typography></Box>
      <Box sx={{ position: 'relative', height: 30, bgcolor: 'action.hover', borderRadius: 1 }}>
        {pos && <Box aria-label={`${start} to ${end}${clash ? ', calendar clash' : ''}`} sx={{ position: 'absolute',
          left: `${pos.left}%`, width: `${pos.width}%`, height: '100%', minWidth: 2, borderRadius: 1,
          bgcolor: clash ? 'warning.main' : color, border: clash ? '2px solid' : undefined, borderColor: 'warning.dark' }} />}
      </Box>
    </Box>;
  }
  return <Stack spacing={2}>
    {timeline.clashes.length ? <Alert severity="warning">
      <Typography fontWeight={600}>Calendar clashes ({timeline.clashes.length})</Typography>
      <Box component="ul" sx={{ my: 0.5, pl: 2.5 }}>{timeline.clashes.map(c => <li key={`${c.case_id}-${c.event_id}`}>
        {c.case_name || c.case_code} overlaps {c.event_name}: {c.overlap_start} to {c.overlap_end} ({c.overlap_days} {c.overlap_days === 1 ? 'day' : 'days'}).
      </li>)}</Box>
    </Alert> : <Alert severity="success">No calendar clashes in this range.</Alert>}
    <Typography variant="body2" color="text.secondary">Dates include both the start and end day. Warnings identify overlapping windows for review.</Typography>
    <Paper variant="outlined" sx={{ p: 2, overflowX: 'auto' }}>
      <Box sx={{ minWidth: 740 }}>
        <Box sx={rowGrid}><Typography variant="subtitle2">Shared date axis</Typography>
          <Stack direction="row" justifyContent="space-between">{ticks.map(t => <Typography key={t} variant="caption">{t}</Typography>)}</Stack>
        </Box>
        <Typography variant="h6" sx={{ mt: 2 }}>Our promotions</Typography>
        {timeline.promotions.length === 0 && <Typography variant="body2">No promotion windows in this range.</Typography>}
        {timeline.promotions.map(p => row(`promotion-${p.case_id}`,
          <><Link href={`/commercial-planner/cpor-cases/${p.case_id}`}>{p.case_name || p.case_code}</Link> <Chip size="small" label={p.status} /></>,
          p.window_start, p.window_end, clashCases.has(p.case_id), 'primary.main'))}
        <Typography variant="h6" sx={{ mt: 2 }}>Customer calendar</Typography>
        {timeline.calendar_events.length === 0 && <Typography variant="body2">No uploaded customer events in this range.</Typography>}
        {timeline.calendar_events.map(e => row(`event-${e.id}`,
          <><Typography variant="body2" component="div">{e.name} <Chip size="small" variant="outlined" label={e.kind} /></Typography>
            {e.source_file && <Typography variant="caption" color="text.secondary">Source: {e.source_file}</Typography>}</>,
          e.start_date, e.end_date, clashEvents.has(e.id), 'secondary.main'))}
      </Box>
    </Paper>
  </Stack>;
}

export function CustomerTimelineSurface() {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const user = useCurrentUser();
  const canWrite = ['admin', 'planner', 'steward'].includes(user.data?.role ?? '');
  const invalidRange = !!from && !!to && to < from;
  const query = useQuery({
    queryKey: ['customer-calendar', 'timeline', customer?.id, from, to], enabled: !!customer && !invalidRange,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({ customer_id: String(customer!.id) });
      if (from) params.set('from', from);
      if (to) params.set('to', to);
      return apiGet<Timeline>(`/api/v1/customer-calendar/timeline?${params}`, { signal });
    },
  });
  return <Stack spacing={3}>
    <Box><Typography variant="h4">Customer promotion timeline</Typography>
      <Typography color="text.secondary">Compare our promotion windows with each customer&apos;s campaigns and pillars.</Typography>
      <Link href="/promotions">Back to promotion planner</Link>
    </Box>
    <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
      <Box sx={{ minWidth: 300 }}><EntitySearchAutocomplete<Customer> label="Customer" value={customer} onChange={setCustomer}
        getOptionLabel={customerLabel} fetchOptions={findCustomers} /></Box>
      <TextField label="From" type="date" value={from} onChange={e => setFrom(e.target.value)} InputLabelProps={{ shrink: true }} />
      <TextField label="To" type="date" value={to} onChange={e => setTo(e.target.value)} InputLabelProps={{ shrink: true }} />
      <Button disabled={!customer || invalidRange || query.isFetching} onClick={() => void query.refetch()}>Refresh timeline</Button>
    </Stack>
    {!customer && <Alert severity="info">Choose a customer to view their promotion timeline.</Alert>}
    {invalidRange && <Alert severity="error">The end date must be on or after the start date.</Alert>}
    {query.isFetching && <LinearProgress />}
    {query.error && <Alert severity="error">{query.error.message}</Alert>}
    {customer && !invalidRange && query.data && <TimelineRows timeline={query.data} from={from} to={to} />}
    {customer && canWrite && <CalendarUploadPanel key={customer.id} customerId={customer.id} onApplied={() => void query.refetch()} />}
  </Stack>;
}
