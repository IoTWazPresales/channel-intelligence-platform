'use client';

import ViewColumnIcon from '@mui/icons-material/ViewColumn';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Chip,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';

import {
  INBOUND_SHIPMENTS_OPTIONAL_FIELDS,
  InboundShipmentsColumnsDialog,
} from './InboundShipmentsColumnsDialog';

const LS_GRID = 'cip.commercial.inbound-shipments.grid.optional.v1';

type CountBucket = { key: string; count: number };

type ShippingSummary = {
  total_lines: number;
  by_line_state: CountBucket[];
  by_status: CountBucket[];
  by_distributor: CountBucket[];
};

type ShippingLine = {
  id: number;
  import_job_id: number | null;
  source_key: string;
  line_state: string;
  status: string;
  report_type?: string | null;
  sales_model_name?: string | null;
  product_resolution_status?: string | null;
  distributor_resolution_status?: string | null;
  customer_resolution_status?: string | null;
  product_sku?: string | null;
  product_name?: string | null;
  distributor_code?: string | null;
  distributor_name?: string | null;
  distributor_display?: string | null;
  item_code?: string | null;
  eta_date?: string | null;
  promise_date?: string | null;
  pod_date?: string | null;
  product_resolution_token?: string | null;
  distributor_resolution_token?: string | null;
  customer_dealer_token?: string | null;
  order_no?: string | null;
  delivery_no?: string | null;
  quantity?: number | null;
};

type LinesResponse = { total: number; skip: number; limit: number; items: ShippingLine[] };

type DistHit = { id: number; distributor_code: string; distributor_name: string };

function fmtShortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function CountTile({ title, buckets }: { title: string; buckets: CountBucket[] }) {
  if (!buckets.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        No rows in this bucket.
      </Typography>
    );
  }
  return (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      {buckets.map((b) => (
        <Tooltip key={`${title}-${b.key}`} title={b.key.length > 96 ? b.key : ''} disableHoverListener={b.key.length <= 96}>
          <Chip label={`${b.key.length > 40 ? `${b.key.slice(0, 40)}…` : b.key}: ${b.count}`} size="small" variant="outlined" />
        </Tooltip>
      ))}
    </Stack>
  );
}

function fmtOpt(v: string | number | null | undefined): string {
  if (v == null || v === '') return '—';
  return String(v);
}

export default function InboundShipmentsPage() {
  const [lineState, setLineState] = useState<string>('');
  const [cargoStatus, setCargoStatus] = useState<string>('');
  const [distributorPick, setDistributorPick] = useState<DistHit | null>(null);
  const [distQ, setDistQ] = useState('');
  const [etaFrom, setEtaFrom] = useState('');
  const [etaTo, setEtaTo] = useState('');
  const [colDialogOpen, setColDialogOpen] = useState(false);
  const [optionalFields, setOptionalFields] = useState<string[]>([]);
  const [persistReady, setPersistReady] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_GRID);
      if (raw) {
        const p = JSON.parse(raw) as { optionalFields?: string[] };
        const allowed = new Set(INBOUND_SHIPMENTS_OPTIONAL_FIELDS.map((c) => c.field));
        if (Array.isArray(p.optionalFields)) {
          setOptionalFields(p.optionalFields.filter((f) => allowed.has(f)));
        }
      }
    } catch {
      /* ignore */
    }
    setPersistReady(true);
  }, []);

  useEffect(() => {
    if (!persistReady) return;
    try {
      localStorage.setItem(LS_GRID, JSON.stringify({ optionalFields }));
    } catch {
      /* ignore */
    }
  }, [optionalFields, persistReady]);

  const optionalSet = useMemo(() => new Set(optionalFields), [optionalFields]);

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['shipping-summary'],
    queryFn: ({ signal }) => apiGet<ShippingSummary>('/api/v1/shipping/summary', { signal }),
  });

  const queryKey = useMemo(
    () => ['shipping-lines', lineState, cargoStatus, distributorPick?.id ?? null, etaFrom, etaTo] as const,
    [lineState, cargoStatus, distributorPick?.id, etaFrom, etaTo]
  );

  const { data: lines, isLoading: linesLoading } = useQuery({
    queryKey,
    queryFn: ({ signal }) => {
      const params = new URLSearchParams();
      params.set('limit', '50');
      if (lineState) params.set('line_state', lineState);
      if (cargoStatus) params.set('status', cargoStatus);
      if (distributorPick != null) params.set('distributor_id', String(distributorPick.id));
      if (etaFrom.trim()) params.set('eta_from', etaFrom.trim());
      if (etaTo.trim()) params.set('eta_to', etaTo.trim());
      return apiGet<LinesResponse>(`/api/v1/shipping/lines?${params.toString()}`, { signal });
    },
  });

  const { data: distHits = [] } = useQuery({
    queryKey: ['distributors-search-inbound-ship', distQ],
    queryFn: ({ signal }) =>
      apiGet<{ items: DistHit[] }>(`/api/v1/distributors?q=${encodeURIComponent(distQ)}&page_size=30`, { signal }),
    enabled: distQ.trim().length >= 1,
    select: (r) => r.items ?? [],
  });

  return (
    <>
      <PageHeader crumbs={[{ label: 'Inbound shipments' }]} title="Inbound shipments" />
      <Alert severity="info" sx={{ mb: 2 }}>
        Truth layer from <strong>fact_inbound_shipment</strong> (populated when an inbound import job is applied).
        Steward raw imports under <strong>Admin → Shipment evidence</strong>.
      </Alert>
      {summaryLoading ? (
        <Typography color="text.secondary">Loading summary…</Typography>
      ) : (
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }}>
          <Paper sx={{ p: 2, flex: 1 }}>
            <Typography variant="subtitle2" color="text.secondary">
              Total fact rows
            </Typography>
            <Typography variant="h5">{summary?.total_lines ?? '—'}</Typography>
          </Paper>
          <Paper sx={{ p: 2, flex: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              By line state
            </Typography>
            <CountTile title="line_state" buckets={summary?.by_line_state ?? []} />
          </Paper>
          <Paper sx={{ p: 2, flex: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              By cargo status
            </Typography>
            <CountTile title="status" buckets={summary?.by_status ?? []} />
          </Paper>
          <Paper sx={{ p: 2, flex: 2 }}>
            <Typography variant="subtitle2" color="text.secondary" gutterBottom>
              By distributor (canonical or source text)
            </Typography>
            <CountTile title="distributor" buckets={summary?.by_distributor ?? []} />
          </Paper>
        </Stack>
      )}

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap alignItems="flex-start">
        <Autocomplete
          sx={{ minWidth: 280, flex: 1 }}
          size="small"
          options={distHits}
          value={distributorPick}
          onChange={(_e, v) => {
            setDistributorPick(v);
            if (!v) setDistQ('');
          }}
          inputValue={distQ}
          onInputChange={(_e, v) => setDistQ(v)}
          getOptionLabel={(o) => `${o.distributor_name} (${o.distributor_code})`}
          isOptionEqualToValue={(a, b) => a.id === b.id}
          renderInput={(params) => <TextField {...params} label="Distributor (canonical)" placeholder="Search…" />}
        />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="flt-line-state">Line state</InputLabel>
          <Select
            labelId="flt-line-state"
            label="Line state"
            value={lineState}
            onChange={(e) => setLineState(String(e.target.value))}
          >
            <MenuItem value="">(any)</MenuItem>
            {(summary?.by_line_state ?? []).map((b) => (
              <MenuItem key={b.key} value={b.key}>
                {b.key}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="flt-cargo">Cargo status</InputLabel>
          <Select
            labelId="flt-cargo"
            label="Cargo status"
            value={cargoStatus}
            onChange={(e) => setCargoStatus(String(e.target.value))}
          >
            <MenuItem value="">(any)</MenuItem>
            {(summary?.by_status ?? []).map((b) => (
              <MenuItem key={b.key} value={b.key}>
                {b.key}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <TextField
          size="small"
          label="ETA from"
          type="date"
          InputLabelProps={{ shrink: true }}
          value={etaFrom}
          onChange={(e) => setEtaFrom(e.target.value)}
          sx={{ width: 160 }}
        />
        <TextField
          size="small"
          label="ETA to"
          type="date"
          InputLabelProps={{ shrink: true }}
          value={etaTo}
          onChange={(e) => setEtaTo(e.target.value)}
          sx={{ width: 160 }}
        />
        <Button
          size="small"
          variant="outlined"
          startIcon={<ViewColumnIcon />}
          onClick={() => setColDialogOpen(true)}
          sx={{ flexShrink: 0, alignSelf: 'center' }}
        >
          Additional columns
        </Button>
      </Stack>

      <Box sx={{ overflowX: 'auto' }}>
        {linesLoading ? (
          <Typography color="text.secondary">Loading rows…</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Distributor</TableCell>
                <TableCell>Product (sales model)</TableCell>
                <TableCell>Line state</TableCell>
                <TableCell>Cargo status</TableCell>
                <TableCell>ETA</TableCell>
                <TableCell>Promise</TableCell>
                <TableCell>POD</TableCell>
                {INBOUND_SHIPMENTS_OPTIONAL_FIELDS.filter((c) => optionalSet.has(c.field)).map((c) => (
                  <TableCell key={c.field}>{c.label}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {(lines?.items ?? []).map((row) => (
                <TableRow key={row.id}>
                  <TableCell>
                    <Typography variant="body2">{row.distributor_display ?? row.distributor_name ?? '—'}</Typography>
                    {row.distributor_code && row.distributor_name ? (
                      <Typography variant="caption" color="text.secondary" display="block">
                        {row.distributor_code}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">{row.sales_model_name ?? row.product_name ?? row.item_code ?? '—'}</Typography>
                    {row.product_sku ? (
                      <Typography variant="caption" color="text.secondary" display="block">
                        SKU {row.product_sku}
                      </Typography>
                    ) : null}
                  </TableCell>
                  <TableCell>{row.line_state}</TableCell>
                  <TableCell>{row.status}</TableCell>
                  <TableCell>{fmtShortDate(row.eta_date)}</TableCell>
                  <TableCell>{fmtShortDate(row.promise_date)}</TableCell>
                  <TableCell>{fmtShortDate(row.pod_date)}</TableCell>
                  {optionalSet.has('import_job_id') ? <TableCell>{fmtOpt(row.import_job_id)}</TableCell> : null}
                  {optionalSet.has('source_key') ? <TableCell sx={{ maxWidth: 220 }}>{fmtOpt(row.source_key)}</TableCell> : null}
                  {optionalSet.has('report_type') ? <TableCell>{fmtOpt(row.report_type)}</TableCell> : null}
                  {optionalSet.has('product_resolution_status') ? (
                    <TableCell>{fmtOpt(row.product_resolution_status)}</TableCell>
                  ) : null}
                  {optionalSet.has('product_resolution_token') ? (
                    <TableCell sx={{ maxWidth: 200 }}>{fmtOpt(row.product_resolution_token)}</TableCell>
                  ) : null}
                  {optionalSet.has('distributor_resolution_status') ? (
                    <TableCell>{fmtOpt(row.distributor_resolution_status)}</TableCell>
                  ) : null}
                  {optionalSet.has('distributor_resolution_token') ? (
                    <TableCell sx={{ maxWidth: 200 }}>{fmtOpt(row.distributor_resolution_token)}</TableCell>
                  ) : null}
                  {optionalSet.has('customer_resolution_status') ? (
                    <TableCell>{fmtOpt(row.customer_resolution_status)}</TableCell>
                  ) : null}
                  {optionalSet.has('customer_dealer_token') ? (
                    <TableCell sx={{ maxWidth: 200 }}>{fmtOpt(row.customer_dealer_token)}</TableCell>
                  ) : null}
                  {optionalSet.has('order_no') ? <TableCell>{fmtOpt(row.order_no)}</TableCell> : null}
                  {optionalSet.has('delivery_no') ? <TableCell>{fmtOpt(row.delivery_no)}</TableCell> : null}
                  {optionalSet.has('quantity') ? <TableCell>{row.quantity != null ? String(row.quantity) : '—'}</TableCell> : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {lines && !linesLoading ? (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
            Showing {lines.items.length} of {lines.total} (skip {lines.skip}, limit {lines.limit})
          </Typography>
        ) : null}
      </Box>

      <InboundShipmentsColumnsDialog
        open={colDialogOpen}
        onClose={() => setColDialogOpen(false)}
        optionalFields={optionalFields}
        onOptionalFieldsChange={setOptionalFields}
      />
    </>
  );
}
