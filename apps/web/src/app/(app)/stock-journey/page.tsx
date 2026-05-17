'use client';

import {
  Alert,
  Box,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

import { KpiCard } from '@/components/KpiCard';
import { PageHeader } from '@/components/PageHeader';
import { apiGet } from '@/lib/api';

type JourneyData = {
  in_transit: number;
  at_distributor: number;
  at_retailer: number;
  sold: number;
  total_pipeline: number;
  data_unavailable?: boolean;
};

type GapItem = {
  product_sku: string;
  product_name: string;
  gap_type: string;
  severity: string;
  detail: string;
};

type ReconciliationGaps = {
  items: GapItem[];
  data_unavailable?: boolean;
};

const STAGE_COLORS = {
  in_transit: '#42a5f5',
  at_distributor: '#ffa726',
  at_retailer: '#66bb6a',
  sold: '#ab47bc',
} as const;

function severityChipColor(severity: string): 'error' | 'warning' | 'info' | 'default' {
  switch (severity.toLowerCase()) {
    case 'high':
    case 'critical':
      return 'error';
    case 'medium':
      return 'warning';
    case 'low':
      return 'info';
    default:
      return 'default';
  }
}

export default function StockJourneyPage() {
  const { data: journey } = useQuery({
    queryKey: ['stock-journey'],
    queryFn: ({ signal }) => apiGet<JourneyData>('/api/v1/soh/journey', { signal }),
  });

  const { data: gaps } = useQuery({
    queryKey: ['stock-reconciliation-gaps'],
    queryFn: ({ signal }) => apiGet<ReconciliationGaps>('/api/v1/soh/reconciliation/gaps', { signal }),
  });

  const journeyUnavailable = journey?.data_unavailable === true;
  const gapsUnavailable = gaps?.data_unavailable === true;

  const chartData = journey
    ? [
        { stage: 'In transit', units: journey.in_transit, fill: STAGE_COLORS.in_transit },
        { stage: 'At distributor', units: journey.at_distributor, fill: STAGE_COLORS.at_distributor },
        { stage: 'At retailer', units: journey.at_retailer, fill: STAGE_COLORS.at_retailer },
        { stage: 'Sold', units: journey.sold, fill: STAGE_COLORS.sold },
      ]
    : [];

  return (
    <>
      <PageHeader crumbs={[{ label: 'Commercial' }, { label: 'Stock journey' }]} title="Stock journey" />

      {journeyUnavailable ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          Stock journey data is not yet available. The underlying tables need to be migrated before this dashboard
          populates.
        </Alert>
      ) : (
        <Alert severity="info" sx={{ mb: 2 }}>
          End-to-end pipeline view from factory shipment through to retail sell-through. Data sourced from{' '}
          <strong>fact_stock_on_hand</strong> and <strong>fact_sales_sellout</strong>.
        </Alert>
      )}

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 3 }} flexWrap="wrap" useFlexGap>
        <Box sx={{ flex: '1 1 180px' }}>
          <KpiCard
            label="In transit"
            value={journey != null ? journey.in_transit.toLocaleString() : '—'}
            hint="Units currently in transit"
          />
        </Box>
        <Box sx={{ flex: '1 1 180px' }}>
          <KpiCard
            label="At distributor"
            value={journey != null ? journey.at_distributor.toLocaleString() : '—'}
            hint="Units held by distributors"
          />
        </Box>
        <Box sx={{ flex: '1 1 180px' }}>
          <KpiCard
            label="At retailer"
            value={journey != null ? journey.at_retailer.toLocaleString() : '—'}
            hint="Units on retail shelves"
          />
        </Box>
        <Box sx={{ flex: '1 1 180px' }}>
          <KpiCard
            label="Sold"
            value={journey != null ? journey.sold.toLocaleString() : '—'}
            hint="Units sold to consumers"
          />
        </Box>
        <Box sx={{ flex: '1 1 180px' }}>
          <KpiCard
            label="Total pipeline"
            value={journey != null ? journey.total_pipeline.toLocaleString() : '—'}
            hint="All units across stages"
          />
        </Box>
      </Stack>

      {!journeyUnavailable && chartData.length > 0 ? (
        <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
          <Typography variant="subtitle2" gutterBottom>
            Units by journey stage
          </Typography>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={chartData} margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
              <XAxis dataKey="stage" />
              <YAxis />
              <Tooltip formatter={(value: number) => value.toLocaleString()} />
              <Bar dataKey="units" radius={[4, 4, 0, 0]}>
                {chartData.map((entry) => (
                  <rect key={entry.stage} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Paper>
      ) : null}

      <Typography variant="h6" sx={{ mb: 1 }}>
        Reconciliation gaps
      </Typography>

      {gapsUnavailable ? (
        <Alert severity="info" sx={{ mb: 2 }}>
          Reconciliation gap analysis is not yet available. The required tables need to be migrated first.
        </Alert>
      ) : (
        <Paper variant="outlined">
          <Box sx={{ p: 2, overflowX: 'auto' }}>
            {(gaps?.items ?? []).length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                No reconciliation gaps detected.
              </Typography>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Product SKU</TableCell>
                    <TableCell>Product name</TableCell>
                    <TableCell>Gap type</TableCell>
                    <TableCell>Severity</TableCell>
                    <TableCell>Detail</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(gaps?.items ?? []).map((g, idx) => (
                    <TableRow key={`${g.product_sku}-${g.gap_type}-${idx}`}>
                      <TableCell>{g.product_sku}</TableCell>
                      <TableCell>{g.product_name}</TableCell>
                      <TableCell>{g.gap_type}</TableCell>
                      <TableCell>
                        <Chip size="small" label={g.severity} color={severityChipColor(g.severity)} />
                      </TableCell>
                      <TableCell>{g.detail}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Box>
        </Paper>
      )}
    </>
  );
}
