'use client';

import {
  Box,
  Chip,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { gridDeleteColumn } from '@/components/gridDeleteColumn';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';
import { PageHeader } from '@/components/PageHeader';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import { toQueryError } from '@/lib/queryError';
import { useUiStore } from '@/stores/uiStore';
import type { ColDef } from 'ag-grid-community';

type ExceptionInboxItem = {
  id: number;
  exception_type: string;
  severity: string;
  title: string;
  explanation_summary: string | null;
  status: string;
};

type UnresolvedProductsData = {
  shipment_unresolved: { item_code: string; sample_sales_model: string | null; occurrences: number }[];
  dsi_unresolved: { raw_product_token: string; occurrences: number }[];
};

type DistributorGapsData = {
  distributors: { code: string; name: string }[];
};

type DataQualityData = {
  checks: unknown[];
};

function TabPanel({ value, index, children }: { value: number; index: number; children: ReactNode }) {
  if (value !== index) return null;
  return <Box sx={{ pt: 2 }}>{children}</Box>;
}

export default function ExceptionsPage() {
  const qc = useQueryClient();
  const openDrawer = useUiStore((s) => s.openDrawer);
  const [tab, setTab] = useState(0);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['exceptions'],
    queryFn: ({ signal }) => apiGet<ExceptionInboxItem[]>('/api/v1/exceptions', { signal }),
  });

  const delRow = useMutation({
    mutationFn: (id: number) => apiDelete(`/api/v1/exceptions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exceptions'] }),
  });
  const clearAll = useMutation({
    mutationFn: () => apiPost<{ deleted: number }>('/api/v1/exceptions/clear-all', { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exceptions'] }),
  });

  const colDefs: ColDef<ExceptionInboxItem>[] = useMemo(() => {
    const busyDel = delRow.isPending || clearAll.isPending;
    return [
      { field: 'exception_type', headerName: 'Type', minWidth: 160 },
      { field: 'severity', headerName: 'Severity', minWidth: 110 },
      { field: 'title', headerName: 'Title', flex: 1, minWidth: 220 },
      { field: 'status', headerName: 'Status', minWidth: 100 },
      {
        headerName: '',
        width: 90,
        cellRenderer: (p: { data: ExceptionInboxItem }) => (
          <Chip
            size="small"
            label="Why"
            onClick={() => openDrawer(p.data.title, p.data.explanation_summary || 'No explanation captured.')}
          />
        ),
      },
      gridDeleteColumn<ExceptionInboxItem>((id) => void delRow.mutate(id), { busy: busyDel }),
    ];
  }, [delRow, delRow.isPending, clearAll.isPending, openDrawer]);

  const rows = data ?? [];

  const { data: unresolvedProducts, isLoading: unresolvedLoading } = useQuery({
    queryKey: ['exceptions-unresolved-products'],
    queryFn: ({ signal }) =>
      apiGet<UnresolvedProductsData>('/api/v1/exceptions/analysis/unresolved-products', { signal }),
    enabled: tab === 1,
  });

  const { data: distributorGaps, isLoading: gapsLoading } = useQuery({
    queryKey: ['exceptions-distributor-gaps'],
    queryFn: ({ signal }) =>
      apiGet<DistributorGapsData>('/api/v1/exceptions/analysis/distributor-gaps', { signal }),
    enabled: tab === 2,
  });

  const { data: dataQuality, isLoading: qualityLoading } = useQuery({
    queryKey: ['exceptions-data-quality'],
    queryFn: ({ signal }) =>
      apiGet<DataQualityData>('/api/v1/exceptions/analysis/data-quality', { signal }),
    enabled: tab === 3,
  });

  const shipmentUnresolved = unresolvedProducts?.shipment_unresolved ?? [];
  const dsiUnresolved = unresolvedProducts?.dsi_unresolved ?? [];
  const totalUnresolved = shipmentUnresolved.length + dsiUnresolved.length;
  const gapDistributors = distributorGaps?.distributors ?? [];

  // suppress unused-variable lint for dataQuality (fetched for future use)
  void dataQuality;
  void qualityLoading;

  return (
    <>
      <PageHeader crumbs={[{ label: 'Exceptions' }]} title="Exceptions" />
      <Paper sx={{ px: 2, pt: 1, mb: 0 }}>
        <Tabs value={tab} onChange={(_, v) => setTab(v)}>
          <Tab label="Exception inbox" />
          <Tab label="Unresolved products" />
          <Tab label="Distributor gaps" />
          <Tab label="Data quality" />
        </Tabs>
      </Paper>

      <TabPanel value={tab} index={0}>
        <Paper sx={{ p: 2 }}>
          <ModuleDataSection
            intro={
              <>
                Each row is an actionable exception with explainable context. Use <strong>Why</strong> to open the detail
                drawer. Items are created by planning and validation services when upstream facts trigger them.
              </>
            }
            introWhen="always"
            isLoading={isLoading}
            isError={isError}
            error={toQueryError(error)}
            onRetry={() => void refetch()}
            isEmpty={rows.length === 0}
            empty={{
              title: 'No open exceptions',
              description:
                'Nothing is flagged yet, or the database has no derived exception rows. Load upstream facts (inventory, inbound, mappings) and refresh.',
              primary: { label: 'Data imports', href: '/admin/imports' },
              secondary: { label: 'Overview', href: '/dashboard' },
            }}
            toolbar={
              <ModuleGridToolbar
                onRefresh={() => qc.invalidateQueries({ queryKey: ['exceptions'] })}
                onClearAll={() => {
                  if (!window.confirm('Delete every exception inbox row? This cannot be undone.')) return;
                  void clearAll.mutate();
                }}
                importsHref="/admin/imports"
                busy={delRow.isPending || clearAll.isPending}
              />
            }
          >
            <EnterpriseDataGrid rowData={rows} columnDefs={colDefs} height={520} />
          </ModuleDataSection>
        </Paper>
      </TabPanel>

      <TabPanel value={tab} index={1}>
        <Paper sx={{ p: 2 }}>
          {unresolvedLoading ? (
            <Typography color="text.secondary">Loading unresolved products…</Typography>
          ) : (
            <>
              <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
                <Typography variant="body1" fontWeight={600}>
                  {totalUnresolved} unresolved product references across shipment evidence and DSI staging
                </Typography>
              </Paper>

              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Shipment evidence — unresolved products
              </Typography>
              <TableContainer component={Paper} variant="outlined" sx={{ mb: 3 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Item code</TableCell>
                      <TableCell>Sample sales model</TableCell>
                      <TableCell align="right">Occurrences</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {shipmentUnresolved.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={3}>
                          <Typography variant="body2" color="text.secondary">No unresolved shipment products.</Typography>
                        </TableCell>
                      </TableRow>
                    ) : null}
                    {shipmentUnresolved.map((row, i) => (
                      <TableRow key={i}>
                        <TableCell>{row.item_code}</TableCell>
                        <TableCell>{row.sample_sales_model ?? '—'}</TableCell>
                        <TableCell align="right">{row.occurrences}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                DSI staging — unresolved products
              </Typography>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Raw product token</TableCell>
                      <TableCell align="right">Occurrences</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {dsiUnresolved.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={2}>
                          <Typography variant="body2" color="text.secondary">No unresolved DSI products.</Typography>
                        </TableCell>
                      </TableRow>
                    ) : null}
                    {dsiUnresolved.map((row, i) => (
                      <TableRow key={i}>
                        <TableCell>{row.raw_product_token}</TableCell>
                        <TableCell align="right">{row.occurrences}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </Paper>
      </TabPanel>

      <TabPanel value={tab} index={2}>
        <Paper sx={{ p: 2 }}>
          {gapsLoading ? (
            <Typography color="text.secondary">Loading distributor gaps…</Typography>
          ) : (
            <>
              <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
                <Typography variant="body1" fontWeight={600}>
                  {gapDistributors.length} distributors have no linked shipment or sell-out data
                </Typography>
              </Paper>

              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Code</TableCell>
                      <TableCell>Name</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {gapDistributors.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={2}>
                          <Typography variant="body2" color="text.secondary">All distributors have linked data.</Typography>
                        </TableCell>
                      </TableRow>
                    ) : null}
                    {gapDistributors.map((d, i) => (
                      <TableRow key={i}>
                        <TableCell>{d.code}</TableCell>
                        <TableCell>{d.name}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </>
          )}
        </Paper>
      </TabPanel>

      <TabPanel value={tab} index={3}>
        <Paper
          variant="outlined"
          sx={{
            p: 3,
            textAlign: 'center',
            border: '2px dashed',
            borderColor: 'divider',
          }}
        >
          <Typography variant="body1" color="text.secondary">
            More exception types coming soon — data quality checks will surface duplicate entities, stale data, and
            schema drift as the platform matures.
          </Typography>
        </Paper>
      </TabPanel>
    </>
  );
}
