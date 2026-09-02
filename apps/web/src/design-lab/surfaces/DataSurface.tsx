'use client';

import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import {
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Checkbox,
  Chip,
  LinearProgress,
  Radio,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';

import { customers, distributors, fmtInt, products, tenant } from '../fixtures/entities';
import { importJobs, stewardQueue, type ImportJob, type StewardToken } from '../fixtures/operations';
import { LensTabs, ScopeBar, StatusChip } from '../primitives/controls';
import { DomainHeader } from '../primitives/DomainHeader';
import { EntityContextPanel, KeyValueList } from '../primitives/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '../primitives/HeadlineFigure';
import { Panel, PanelRow } from '../primitives/Panel';

type Tab = 'imports' | 'steward' | 'masters' | 'audit';

const jobTone = (s: ImportJob['status']) => (s === 'failed' ? 'danger' : s === 'stewarding' ? 'warning' : s === 'running' ? 'info' : s === 'applied' ? 'success' : 'neutral');
const jobLabel: Record<ImportJob['status'], string> = { failed: 'Failed', validated: 'Validated', applied: 'Applied', stewarding: 'Stewarding', running: 'Running' };
/** Same bands as the shared `confidenceBand` helper in the shipped steward engine (≥0.90 high / ≥0.70 medium). */
const band = (s: number) => (s >= 0.9 ? 'high' : s >= 0.7 ? 'medium' : 'low');

function ImportsTab() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const search = useSearchParams();
  const router = useRouter();
  const status = search.get('status');
  const rows = useMemo(() => importJobs.filter((j) => !status || j.status === status), [status]);
  const counts = useMemo(() => importJobs.reduce<Record<string, number>>((m, j) => ({ ...m, [j.status]: (m[j.status] ?? 0) + 1 }), {}), []);
  const setStatus = (v: string | null) => router.replace(`/design-lab/data?tab=imports${v ? `&status=${v}` : ''}`, { scroll: false });

  const columnDefs = useMemo<ColDef<ImportJob>[]>(
    () => [
      { field: 'id', headerName: 'Job', width: 90, pinned: 'left' },
      { field: 'template', headerName: 'Import type', minWidth: 190, flex: 1, valueFormatter: (p) => String(p.value).replace(/_/g, ' ') },
      { field: 'file', headerName: 'File', minWidth: 220, flex: 1.4 },
      { field: 'source', headerName: 'Source', minWidth: 170, flex: 1 },
      { field: 'rows', headerName: 'Rows', type: 'rightAligned', width: 100, valueFormatter: (p) => (p.value ? fmtInt(p.value) : '—') },
      { field: 'unresolved', headerName: 'Unresolved', type: 'rightAligned', width: 120, valueFormatter: (p) => (p.value ? fmtInt(p.value) : '—'), cellStyle: (p) => (p.value ? { color: theme.palette.warning.main, fontWeight: 600 } : null) },
      { field: 'status', headerName: 'Status', width: 150, cellRenderer: (p: { data: ImportJob }) => <StatusChip label={jobLabel[p.data.status]} tone={jobTone(p.data.status)} /> },
      { field: 'when', headerName: 'When', width: 150 },
    ],
    [theme]
  );

  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <HeadlineStrip columns={5}>
        <HeadlineFigure label="Jobs this week" value={importJobs.length} compact />
        <HeadlineFigure label="Failed" value={counts.failed ?? 0} compact severity="bad" onClick={() => setStatus('failed')} caption="Parse / validation errors" />
        <HeadlineFigure label="Stewarding" value={counts.stewarding ?? 0} compact severity="warn" onClick={() => setStatus('stewarding')} caption={`${importJobs.reduce((a, j) => a + j.unresolved, 0)} unresolved tokens`} />
        <HeadlineFigure label="Applied" value={counts.applied ?? 0} compact severity="good" caption={`${fmtInt(importJobs.filter((j) => j.status === 'applied').reduce((a, j) => a + j.rows, 0))} rows to facts`} />
        <HeadlineFigure label="Import types" value={19} compact caption="One guided pipeline for all" />
      </HeadlineStrip>
      <Panel
        title="Start an import"
        subtitle="Upload → parse → map → validate → steward → apply → derive. Same 8-step wizard for every type."
        actions={<Button variant="contained" size="small" startIcon={<CloudUploadOutlinedIcon />}>New import</Button>}
      >
        <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(6, 1fr)' } }}>
          {[
            ['Distributor sell-out & SOH', 'distributor_inventory'],
            ['Retailer sell-through', 'customer_sell_through'],
            ['Inbound shipments', 'inbound_shipments'],
            ['Lineup (unified)', 'unified_lineup'],
            ['Claim evidence', 'cpor_claim_evidence'],
            ['Product master', 'product_master'],
          ].map(([label, slug]) => (
            <Card key={slug} variant="outlined" sx={{ boxShadow: 'none' }}>
              <CardActionArea sx={{ height: '100%' }}>
                <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{label}</Typography>
                  <Typography variant="caption" color="text.secondary">{slug}</Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          ))}
        </Box>
      </Panel>
      <ScopeBar
        chips={(['failed', 'stewarding', 'validated', 'applied'] as ImportJob['status'][]).map((s) => ({ key: s, label: `${jobLabel[s]} · ${counts[s] ?? 0}`, active: status === s, onToggle: () => setStatus(status === s ? null : s), tone: s === 'failed' ? 'danger' : s === 'stewarding' ? 'warning' : s === 'applied' ? 'success' : 'default' }))}
        summary={`${rows.length} of ${importJobs.length} jobs`}
        onClear={() => setStatus(null)}
      />
      <ModuleDataSection isEmpty={rows.length === 0} empty={{ title: 'No jobs in this state', description: 'Clear the filter or start a new import.', primary: { label: 'Clear', onClick: () => setStatus(null) } }}>
        {isMobile ? (
          <Stack spacing={1}>
            {rows.map((j) => (
              <Card key={j.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{j.file}</Typography>
                      <Typography variant="caption" color="text.secondary">#{j.id} · {j.source} · {j.when}</Typography>
                    </Box>
                    <StatusChip label={jobLabel[j.status]} tone={jobTone(j.status)} />
                  </Stack>
                  {j.status === 'running' ? <LinearProgress sx={{ mt: 1 }} /> : null}
                </CardContent>
              </Card>
            ))}
          </Stack>
        ) : (
          <EnterpriseDataGrid<ImportJob> rowData={rows} columnDefs={columnDefs} height={360} gridOptions={{ getRowId: (p) => String(p.data.id) }} />
        )}
      </ModuleDataSection>
    </Stack>
  );
}

function StewardTab() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [entity, setEntity] = useState<'all' | StewardToken['entity']>('all');
  const [queue, setQueue] = useState(stewardQueue);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [open, setOpen] = useState<StewardToken | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const rows = useMemo(() => queue.filter((t) => entity === 'all' || t.entity === entity), [queue, entity]);
  const counts = useMemo(() => ({ customer: queue.filter((t) => t.entity === 'customer').length, product: queue.filter((t) => t.entity === 'product').length, distributor: queue.filter((t) => t.entity === 'distributor').length }), [queue]);

  const resolve = (ids: number[], how: 'accept' | 'reject') => {
    setQueue((q) => q.filter((t) => !ids.includes(t.id)));
    setSelectedIds([]);
    setOpen(null);
    setToast(how === 'accept' ? `${ids.length} token${ids.length > 1 ? 's' : ''} mapped — ${queue.filter((t) => ids.includes(t.id)).reduce((a, t) => a + t.rows, 0)} rows re-resolved across ${queue.filter((t) => ids.includes(t.id)).reduce((a, t) => a + t.jobs, 0)} jobs` : `${ids.length} candidate${ids.length > 1 ? 's' : ''} rejected — tokens stay in queue for manual search`);
  };

  const columnDefs = useMemo<ColDef<StewardToken>[]>(
    () => [
      { field: 'token', headerName: 'Token from file', minWidth: 200, flex: 1.2, pinned: 'left', checkboxSelection: true, headerCheckboxSelection: true },
      { field: 'entity', headerName: 'Entity', width: 120, valueFormatter: (p) => String(p.value)[0].toUpperCase() + String(p.value).slice(1) },
      { field: 'bestCandidate', headerName: 'Best candidate', minWidth: 240, flex: 1.5 },
      { field: 'candidateScore', headerName: 'Confidence', width: 150, cellRenderer: (p: { data: StewardToken }) => <StatusChip label={`${band(p.data.candidateScore)} · ${p.data.candidateScore.toFixed(2)}`} tone={band(p.data.candidateScore) === 'high' ? 'success' : band(p.data.candidateScore) === 'medium' ? 'warning' : 'neutral'} /> },
      { field: 'corroborated', headerName: 'Corroborated', width: 130, cellDataType: 'text', valueFormatter: (p) => (p.value ? 'Shipments ✓' : '—'), cellStyle: (p) => (p.value ? { color: theme.palette.success.main } : null) },
      { field: 'jobs', headerName: 'Jobs', type: 'rightAligned', width: 80 },
      { field: 'rows', headerName: 'Rows affected', type: 'rightAligned', width: 130, valueFormatter: (p) => fmtInt(p.value) },
    ],
    [theme]
  );

  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <HeadlineStrip columns={4}>
        <HeadlineFigure label="Tokens awaiting resolution" value={queue.length} compact severity={queue.length ? 'warn' : 'good'} caption={`${fmtInt(queue.reduce((a, t) => a + t.rows, 0))} fact rows held back`} />
        <HeadlineFigure label="Customers" value={counts.customer} compact onClick={() => setEntity('customer')} />
        <HeadlineFigure label="Products" value={counts.product} compact onClick={() => setEntity('product')} />
        <HeadlineFigure label="Distributors" value={counts.distributor} compact onClick={() => setEntity('distributor')} />
      </HeadlineStrip>
      <Typography variant="body2" color="text.secondary">
        Cross-job queue: every unresolved name from any import, deduplicated. Resolving here re-resolves all held rows. Per-job stewarding remains inside each import job — this is the same governance boundary seen across jobs. Candidates are deterministic-first; AI suggestions appear only on a miss and never auto-apply below 0.90.
      </Typography>
      <LensTabs value={entity} onChange={setEntity} ariaLabel="Entity" lenses={[{ value: 'all', label: 'All', count: queue.length }, { value: 'customer', label: 'Customers', count: counts.customer }, { value: 'product', label: 'Products', count: counts.product }, { value: 'distributor', label: 'Distributors', count: counts.distributor }]} />
      {selectedIds.length ? (
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap data-testid="steward-bulk-bar" sx={{ p: 1, borderRadius: 1.5, bgcolor: 'action.selected' }}>
          <Chip size="small" color="primary" label={`${selectedIds.length} selected`} />
          <Typography variant="caption" color="text.secondary">
            {fmtInt(rows.filter((r) => selectedIds.includes(r.id)).reduce((a, r) => a + r.rows, 0))} rows will re-resolve
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Button size="small" variant="outlined" color="error" onClick={() => resolve(selectedIds, 'reject')}>
            Reject candidates
          </Button>
          <Button size="small" variant="contained" onClick={() => resolve(selectedIds, 'accept')} disabled={rows.filter((r) => selectedIds.includes(r.id)).some((r) => r.candidateScore < 0.7)}>
            Accept best candidates
          </Button>
          <Button size="small" onClick={() => setSelectedIds([])}>Clear</Button>
        </Stack>
      ) : null}
      <ModuleDataSection isEmpty={rows.length === 0} empty={{ title: 'Queue clear', description: 'Every token from every job is mapped. New imports will add to this queue.', primary: { label: 'Import Center', href: '/design-lab/data?tab=imports' } }}>
        {isMobile ? (
          <Stack spacing={1} data-testid="steward-record-cards">
            {rows.map((t) => (
              <Card key={t.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                  <Stack direction="row" alignItems="flex-start" spacing={1}>
                    <Checkbox size="small" checked={selectedIds.includes(t.id)} onChange={(e) => setSelectedIds((s) => (e.target.checked ? [...s, t.id] : s.filter((x) => x !== t.id)))} sx={{ p: 0.25 }} inputProps={{ 'aria-label': `Select ${t.token}` }} />
                    <Box sx={{ flex: 1, minWidth: 0 }} onClick={() => setOpen(t)}>
                      <Typography variant="caption" color="text.secondary">{t.entity} · {t.jobs} jobs · {fmtInt(t.rows)} rows</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>“{t.token}”</Typography>
                      <Typography variant="body2">→ {t.bestCandidate}</Typography>
                      <Stack direction="row" spacing={1} sx={{ mt: 0.75 }} alignItems="center">
                        <StatusChip label={`${band(t.candidateScore)} ${t.candidateScore.toFixed(2)}`} tone={band(t.candidateScore) === 'high' ? 'success' : band(t.candidateScore) === 'medium' ? 'warning' : 'neutral'} />
                        {t.corroborated ? <Chip size="small" variant="outlined" label="Shipments corroborate" sx={{ height: 22 }} /> : null}
                      </Stack>
                    </Box>
                  </Stack>
                  <Stack direction="row" spacing={1} sx={{ mt: 1 }} justifyContent="flex-end">
                    <Button size="small" variant="outlined" color="error" onClick={() => resolve([t.id], 'reject')}>Reject</Button>
                    <Button size="small" variant="contained" onClick={() => resolve([t.id], 'accept')} disabled={t.candidateScore < 0.7}>Accept</Button>
                  </Stack>
                </CardContent>
              </Card>
            ))}
          </Stack>
        ) : (
          <EnterpriseDataGrid<StewardToken>
            rowData={rows}
            columnDefs={columnDefs}
            height={380}
            gridOptions={{
              rowSelection: 'multiple',
              suppressRowClickSelection: true,
              getRowId: (p) => String(p.data.id),
              onSelectionChanged: (e) => setSelectedIds(e.api.getSelectedRows().map((r) => r.id)),
              onRowClicked: (e: RowClickedEvent<StewardToken>) => e.data && setOpen(e.data),
            }}
          />
        )}
      </ModuleDataSection>
      <EntityContextPanel
        open={!!open}
        onClose={() => setOpen(null)}
        kicker={open ? `${open.entity} token` : undefined}
        width={520}
        title={open ? `“${open.token}”` : ''}
        subtitle={open ? `Seen in ${open.jobs} jobs · ${fmtInt(open.rows)} rows held` : undefined}
        footer={
          open ? (
            <>
              <Button variant="outlined" color="error" size="small" onClick={() => resolve([open.id], 'reject')}>Reject candidate</Button>
              <Button variant="contained" size="small" onClick={() => resolve([open.id], 'accept')} disabled={open.candidateScore < 0.7}>Map to candidate</Button>
            </>
          ) : null
        }
      >
        {open ? <StewardDrawerBody token={open} /> : null}
      </EntityContextPanel>
      <Snackbar open={!!toast} autoHideDuration={4000} onClose={() => setToast(null)} message={toast} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Stack>
  );
}

/**
 * Drawer body for one token. Mirrors the depth of the shipped steward panels
 * (ShipmentEntityStewardPanel / DSI resolution section): ranked candidates with the
 * tier that produced them, the source rows carrying the token, a master search,
 * and the provisional-record path — all behind steward confirmation.
 */
function StewardDrawerBody({ token }: { token: StewardToken }) {
  const [choice, setChoice] = useState(0);
  const [query, setQuery] = useState('');
  const pool =
    token.entity === 'customer'
      ? customers.map((c) => ({ name: c.name, meta: c.group }))
      : token.entity === 'product'
        ? products.map((p) => ({ name: p.name, meta: `${p.sku} · ${p.family}` }))
        : distributors.map((d) => ({ name: d.name, meta: d.region }));
  const best = { name: token.bestCandidate, meta: pool.find((p) => p.name === token.bestCandidate)?.meta ?? '', score: token.candidateScore, tier: token.entity === 'product' ? 'sales model name' : 'alias', corroborated: token.corroborated };
  const others = pool
    .filter((p) => p.name !== token.bestCandidate)
    .slice(0, 3)
    .map((p, i) => ({ ...p, score: Math.max(0.31, token.candidateScore - 0.22 - i * 0.11), tier: i === 0 ? 'alias' : 'name similarity', corroborated: false }));
  const candidates = [best, ...others];
  const searchHits = query.trim() ? pool.filter((p) => p.name.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 4) : [];
  const sampleRows = [
    { job: 'Job 1276', file: 'MER_sellout_W36.xlsx', row: 'row 214', qty: '12', date: '2026-08-31' },
    { job: 'Job 1271', file: 'OfficeWorld_P10_lineup.xlsx', row: 'row 58', qty: '40', date: '2026-08-26' },
    { job: 'Job 1268', file: 'MER_sellout_W35.xlsx', row: 'row 197', qty: '9', date: '2026-08-24' },
  ];
  return (
    <Stack spacing={2}>
      <Panel title="Candidates" subtitle="Deterministic tiers: item code → EAN → model name → alias; shipment corroboration runs after eligibility" flush>
        <Stack spacing={0} sx={{ px: 1, pb: 1 }}>
          {candidates.map((c, i) => (
            <Box
              key={c.name}
              onClick={() => setChoice(i)}
              sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1, py: 0.75, borderRadius: 1, cursor: 'pointer', bgcolor: choice === i ? 'action.selected' : 'transparent', '&:hover': { bgcolor: 'action.hover' } }}
            >
              <Radio size="small" checked={choice === i} sx={{ p: 0.25 }} inputProps={{ 'aria-label': `Choose ${c.name}` }} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: i === 0 ? 600 : 500 }} noWrap>{c.name}</Typography>
                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>{c.meta} · via {c.tier}</Typography>
              </Box>
              <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0 }}>
                {c.corroborated ? <StatusChip label="shipments ✓" tone="success" /> : null}
                <StatusChip label={`${band(c.score)} · ${c.score.toFixed(2)}`} tone={band(c.score) === 'high' ? 'success' : band(c.score) === 'medium' ? 'warning' : 'neutral'} />
              </Stack>
            </Box>
          ))}
        </Stack>
      </Panel>

      <Panel title="Not listed? Search the master" subtitle={`Any ${token.entity} record can be chosen; the mapping is recorded as a steward decision`}>
        <TextField size="small" fullWidth placeholder={`Search ${token.entity}s by name, code or alias`} value={query} onChange={(e) => setQuery(e.target.value)} inputProps={{ 'aria-label': 'Search master records' }} />
        {searchHits.length ? (
          <Stack spacing={0.25} sx={{ mt: 1 }}>
            {searchHits.map((h) => (
              <PanelRow key={h.name} severity="neutral" primary={h.name} secondary={h.meta} figure="Choose" onClick={() => { setQuery(''); }} />
            ))}
          </Stack>
        ) : query.trim() ? (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>No master record matches — create a provisional record below (steward-initiated, enriched later).</Typography>
        ) : null}
        <Button size="small" variant="text" sx={{ mt: 1 }}>Create provisional {token.entity} from this token</Button>
      </Panel>

      <Panel title={`Source rows carrying this token`} subtitle={`${fmtInt(token.rows)} rows across ${token.jobs} jobs are held until it resolves — showing 3`} flush>
        <Table size="small" sx={{ '& td, & th': { py: 0.5, px: 1.5, whiteSpace: 'nowrap' } }}>
          <TableHead>
            <TableRow>
              <TableCell>Job</TableCell>
              <TableCell>File</TableCell>
              <TableCell>Row</TableCell>
              <TableCell align="right">Qty</TableCell>
              <TableCell>Date</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {sampleRows.map((r) => (
              <TableRow key={r.row + r.file} hover>
                <TableCell>{r.job}</TableCell>
                <TableCell sx={{ maxWidth: 170, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.file}</TableCell>
                <TableCell>{r.row}</TableCell>
                <TableCell align="right">{r.qty}</TableCell>
                <TableCell>{r.date}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Panel>

      <KeyValueList
        items={[
          { k: 'First seen', v: 'Job 1268 · 24 Aug 2026' },
          { k: 'Applies to', v: `${token.jobs} jobs · re-resolves ${fmtInt(token.rows)} held rows on confirm` },
          { k: 'Governance', v: 'Steward confirmation required; no auto-create of master records; AI suggestions never auto-apply below 0.90' },
        ]}
      />
    </Stack>
  );
}

function MastersTab() {
  const masters = [
    { key: 'products', label: 'Products', count: 18_204, provisional: 96, duplicates: 12, what: 'SKU, EAN, model, family, lifecycle; specs JSON' },
    { key: 'customers', label: 'Customers / dealers', count: 1_412, provisional: 31, duplicates: 7, what: 'Groups, strategic flag, commercial terms, channel mapping' },
    { key: 'distributors', label: 'Distributors', count: 4, provisional: 0, duplicates: 0, what: 'Commercial terms, regions, DSI file conventions' },
    { key: 'stores', label: 'Stores', count: 388, provisional: 14, duplicates: 3, what: 'Retail locations under customers' },
  ];
  return (
    <Stack spacing={2} sx={{ mt: 2 }}>
      <Typography variant="body2" color="text.secondary">Master data is the identity anchor for every fact. Import evidence never creates a master record silently — provisional records are steward-initiated and enriched here.</Typography>
      <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', md: 'repeat(2, 1fr)' } }}>
        {masters.map((m) => (
          <Panel key={m.key} title={m.label} subtitle={m.what} actions={<Button size="small" component={NextLink} href={`/design-lab/data?tab=masters&m=${m.key}`}>Open grid</Button>}>
            <HeadlineStrip columns={3}>
              <HeadlineFigure label="Records" value={fmtInt(m.count)} dense />
              <HeadlineFigure label="Provisional" value={m.provisional} dense severity={m.provisional ? 'warn' : 'neutral'} />
              <HeadlineFigure label="Possible duplicates" value={m.duplicates} dense severity={m.duplicates ? 'warn' : 'neutral'} />
            </HeadlineStrip>
          </Panel>
        ))}
      </Box>
    </Stack>
  );
}

export function DataSurface() {
  const search = useSearchParams();
  const router = useRouter();
  const tab = (search.get('tab') as Tab) || 'imports';
  return (
    <Box data-testid="data-surface">
      <DomainHeader
        crumbs={[{ label: 'Data & Stewardship' }]}
        title="Data & Stewardship"
        description="Bring files in, resolve unknown names to master records, and keep master data trustworthy. Every fact in CIP arrives through this door."
        meta={`${tenant.period} · ${importJobs.length} jobs this week · ${stewardQueue.length} tokens in the cross-job queue`}
        actions={<Button variant="contained" size="small" startIcon={<CloudUploadOutlinedIcon />}>New import</Button>}
      />
      <LensTabs
        value={tab}
        onChange={(t) => router.replace(`/design-lab/data?tab=${t}`, { scroll: false })}
        ariaLabel="Data & Stewardship"
        lenses={[
          { value: 'imports', label: 'Import Center', count: importJobs.filter((j) => j.status === 'failed' || j.status === 'stewarding').length },
          { value: 'steward', label: 'Steward queue', count: stewardQueue.length },
          { value: 'masters', label: 'Master data' },
          { value: 'audit', label: 'Steward audit' },
        ]}
      />
      {tab === 'imports' ? <ImportsTab /> : null}
      {tab === 'steward' ? <StewardTab /> : null}
      {tab === 'masters' ? <MastersTab /> : null}
      {tab === 'audit' ? (
        <Stack spacing={1} sx={{ mt: 2 }}>
          <Panel title="Recent steward actions" subtitle="Who mapped what, when, with which evidence" flush>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
              <PanelRow severity="neutral" primary="“KZN CHANNEL” → Kwazulu Channel Partners" secondary="W. Eliason · today 09:31 · corroborated by 3 shipments · 3 120 rows re-resolved" />
              <PanelRow severity="neutral" primary="“UX2780-Q BLK” → 27&quot; QHD IPS Monitor UX2780Q" secondary="T. Naidoo · yesterday 16:12 · tier: model name · 96 rows" />
              <PanelRow severity="neutral" primary="Provisional customer created: Game Zone — Menlyn" secondary="T. Naidoo · Mon 11:04 · pending enrichment (group, terms)" />
            </Stack>
          </Panel>
        </Stack>
      ) : null}
    </Box>
  );
}
