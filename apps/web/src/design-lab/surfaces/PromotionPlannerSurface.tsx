'use client';

import AutoAwesomeOutlinedIcon from '@mui/icons-material/AutoAwesomeOutlined';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined';
import type { CellClickedEvent, CellValueChangedEvent, ColDef, RowClickedEvent } from 'ag-grid-community';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import NextLink from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';

import {
  activationLabel,
  budgetCheck,
  commercialCapabilities,
  comparableCases,
  costEvidenceForLine,
  costSourceLabel,
  dealerPrice,
  lifecycleStages,
  lineSupport,
  planLines as seedLines,
  planTemplates,
  promotionPlans as seedPlans,
  stageLabel,
  supportUnit,
  type PlanLine,
  type PlanStage,
  type PromotionPlan,
} from '../fixtures/commercial';
import { customers, fmtCurrency, fmtInt } from '../fixtures/entities';
import { CapabilityLedger } from '../primitives/CapabilityLedger';
import { CapabilityStatus } from '../primitives/CapabilityStatus';
import { ScopeBar, StatusChip } from '../primitives/controls';
import { EntityContextPanel, KeyValueList } from '../primitives/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '../primitives/HeadlineFigure';
import { LifecycleRail } from '../primitives/LifecycleRail';
import { Panel, PanelRow } from '../primitives/Panel';

const stageTone = (s: PlanStage) => (s === 'active' ? 'success' : s === 'approved' ? 'info' : s === 'proposed' ? 'warning' : s === 'cancelled' ? 'danger' : 'neutral');
const originLabel: Record<PromotionPlan['origin'], string> = { proposed_by_cip: 'Proposed by CIP', manual: 'Manual', historical_import: 'Historical import' };

/**
 * Promotion planner — the planning half of the single promotion-case lifecycle (draft → proposed →
 * approved → live → ended → settled). Same `cpor_case` the Case book settles later.
 *
 * Two views on one URL: the plan list (`?lens=planner`) and the plan workspace (`&plan=CPR-…`).
 * Everything shown here is either computed by the shipped waterfall (dealer price, support/unit,
 * totals, budget check) or is a stored fact (cost tiers, comparables, cover, listing state,
 * competitor mappings). Uplift, elasticity and competitor impact are not shown as numbers anywhere.
 */
export function PromotionPlannerSurface() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const router = useRouter();
  const search = useSearchParams();
  const planId = search.get('plan');
  const stageFilter = search.get('stage') as PlanStage | null;
  const setParam = useCallback(
    (k: string, v: string | null) => {
      const next = new URLSearchParams(search.toString());
      if (v === null) next.delete(k);
      else next.set(k, v);
      router.replace(`/design-lab/funding?${next.toString()}`, { scroll: false });
    },
    [router, search]
  );

  const [plans, setPlans] = useState<PromotionPlan[]>(seedPlans);
  const [toast, setToast] = useState<string | null>(null);
  const plan = plans.find((p) => p.id === planId) ?? null;

  if (plan) {
    return <PlanWorkspace plan={plan} onBack={() => setParam('plan', null)} onStage={(s) => { setPlans((ps) => ps.map((p) => (p.id === plan.id ? { ...p, stage: s } : p))); setToast(s === 'proposed' ? `${plan.id} submitted for approval — the case now appears under Proposed in the Case book` : `${plan.id} → ${stageLabel[s]}`); }} toast={toast} setToast={setToast} />;
  }

  const counts = lifecycleStages.reduce<Partial<Record<PlanStage, number>>>((m, s) => ({ ...m, [s]: plans.filter((p) => p.stage === s).length }), {});
  const rows = plans.filter((p) => !stageFilter || p.stage === stageFilter);
  const planning = plans.filter((p) => ['draft', 'proposed', 'approved'].includes(p.stage));
  const live = plans.filter((p) => p.stage === 'active');

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="promotion-planner">
      <Alert severity="info" variant="outlined" icon={false} sx={{ '& .MuiAlert-message': { width: '100%' } }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }} justifyContent="space-between">
          <Typography variant="body2">
            <b>One case, one lifecycle.</b> A promotion plan you author here is the same case the Case book approves, watches live, claims and settles. Nothing is copied between “plan” and “funding”.
          </Typography>
          <Box sx={{ minWidth: { md: 520 } }}>
            <LifecycleRail stages={lifecycleStages} labels={stageLabel} counts={counts} dense onSelect={(s) => setParam('stage', stageFilter === s ? null : s)} />
          </Box>
        </Stack>
      </Alert>

      <HeadlineStrip columns={5}>
        <HeadlineFigure label="In planning" value={planning.length} unit="plans" compact caption={`${fmtCurrency(planning.reduce((a, p) => a + p.supportTotal, 0), { compact: true })} support proposed`} onClick={() => setParam('stage', 'proposed')} />
        <HeadlineFigure label="Live now" value={live.length} unit="plans" compact severity={live.some((p) => p.activation === 'not_activated') ? 'warn' : 'good'} caption={live.some((p) => p.activation === 'not_activated') ? '1 listing not at promo price' : 'All listings at promo price'} onClick={() => setParam('stage', 'active')} />
        <HeadlineFigure label="Awaiting your review" value={counts.proposed ?? 0} unit="proposed" compact severity="warn" caption="CIP proposals need a planner decision" onClick={() => setParam('stage', 'proposed')} />
        <HeadlineFigure label="Budget reservation used" value={`${Math.round((budgetCheck.drawnUsd / budgetCheck.reservationUsd) * 100)}%`} compact caption={`$${fmtInt(budgetCheck.drawnUsd)} of $${fmtInt(budgetCheck.reservationUsd)} · lineup-derived`} severity={budgetCheck.drawnUsd / budgetCheck.reservationUsd > 0.85 ? 'warn' : 'neutral'} />
        <HeadlineFigure label="Uplift / effectiveness" value="—" compact caption="Not derived until ≥5 settled cases with claim evidence — never estimated" />
      </HeadlineStrip>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: 'minmax(0, 3fr) minmax(300px, 2fr)' }, alignItems: 'start' }}>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <ScopeBar
            chips={lifecycleStages.map((s) => ({ key: s, label: `${stageLabel[s]} · ${counts[s] ?? 0}`, active: stageFilter === s, onToggle: () => setParam('stage', stageFilter === s ? null : s), tone: s === 'active' ? 'success' : s === 'proposed' ? 'warning' : 'default' }))}
            summary={`${rows.length} of ${plans.length} plans`}
            onClear={() => setParam('stage', null)}
            trailing={
              <Stack direction="row" spacing={1}>
                <Tooltip title="Partly built: today a draft needs a seed case id. The proposal from customer + window alone is the N-0010 delta." arrow>
                  <span>
                    <Button size="small" variant="outlined" startIcon={<AutoAwesomeOutlinedIcon />} onClick={() => setToast('Proposal seeds a draft from the customer’s last approved case, 13-week forecast, cover and MAC — review it before it goes anywhere.')} data-testid="planner-propose">
                      Propose a plan
                    </Button>
                  </span>
                </Tooltip>
                <Button size="small" variant="contained" onClick={() => setToast('New empty case: pick customer, promotion type and window, then add lines.')} data-testid="planner-new">
                  New plan
                </Button>
              </Stack>
            }
          />
          <ModuleDataSection isEmpty={rows.length === 0} empty={{ title: 'No plans in this stage', description: 'Clear the stage filter, propose a plan from evidence, or start one manually.', primary: { label: 'Clear', onClick: () => setParam('stage', null) } }}>
            {isMobile ? (
              <Stack spacing={1} data-testid="planner-record-cards">
                {rows.map((p) => (
                  <Card key={p.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                    <CardActionArea onClick={() => setParam('plan', p.id)}>
                      <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>{p.name}</Typography>
                            <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>{p.id} · {p.customer} · {p.period}</Typography>
                          </Box>
                          <StatusChip label={stageLabel[p.stage]} tone={stageTone(p.stage)} />
                        </Stack>
                        <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
                          <Typography variant="caption">Lines <b>{p.lines}</b></Typography>
                          <Typography variant="caption">Units <b>{fmtInt(p.estimateUnits)}</b></Typography>
                          <Typography variant="caption">Support <b>{fmtCurrency(p.supportTotal, { compact: true })}</b></Typography>
                        </Stack>
                        {p.flags.length ? <Typography variant="caption" color="warning.main" sx={{ display: 'block', mt: 0.5 }}>{p.flags.join(' · ')}</Typography> : null}
                      </CardContent>
                    </CardActionArea>
                  </Card>
                ))}
              </Stack>
            ) : (
              <PlanGrid rows={rows} onOpen={(id) => setParam('plan', id)} />
            )}
          </ModuleDataSection>
        </Stack>

        <Stack spacing={2}>
          <Panel title="Needs a decision" subtitle="Proposals, flags and live checks on your plans" flush>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
              {plans.filter((p) => p.stage === 'proposed').map((p) => (
                <PanelRow key={p.id} severity="warning" primary={`${p.id} · review CIP proposal`} secondary={`${p.customer} · ${p.lines} lines · ${fmtCurrency(p.supportTotal, { compact: true })}`} onClick={() => setParam('plan', p.id)} />
              ))}
              {plans.filter((p) => p.stage === 'active' && p.activation === 'not_activated').map((p) => (
                <PanelRow key={`${p.id}-act`} severity="danger" primary={`${p.id} · live but not at promo price`} secondary="Metro NBP14-I7 observed R18 999 vs case R16 999 (listing 44, today 06:10)" figure="Market › Activation" onClick={() => router.push('/design-lab/market?lens=activation')} />
              ))}
              {plans.filter((p) => p.stage === 'draft' && p.flags.some((f) => f.includes('template'))).map((p) => (
                <PanelRow key={`${p.id}-tpl`} severity="info" primary={`${p.id} · export template needs mapping`} secondary="OfficeWorld request form: 18 of 39 canonical fields mapped" figure="Templates" onClick={() => setParam('lens', 'templates')} />
              ))}
              {plans.filter((p) => p.stage === 'ended').map((p) => (
                <PanelRow key={`${p.id}-claim`} severity="info" primary={`${p.id} · ended, claim evidence pending`} secondary="Case moves to settlement once Metro’s claim file is applied" figure="Case book" onClick={() => setParam('lens', null)} />
              ))}
            </Stack>
          </Panel>
          <CapabilityLedger items={commercialCapabilities.planner} />
        </Stack>
      </Box>
      <Snackbar open={!!toast} autoHideDuration={4500} onClose={() => setToast(null)} message={toast} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Stack>
  );
}

function PlanGrid({ rows, onOpen }: { rows: PromotionPlan[]; onOpen: (id: string) => void }) {
  const columnDefs = useMemo<ColDef<PromotionPlan>[]>(
    () => [
      { field: 'id', headerName: 'Case', width: 120, pinned: 'left' },
      { field: 'name', headerName: 'Plan', minWidth: 220, flex: 1.6, cellRenderer: (p: { data: PromotionPlan }) => (
          <Box sx={{ lineHeight: 1.2 }}>
            <Typography variant="body2" noWrap>{p.data.name}</Typography>
            <Typography variant="caption" color="text.secondary">{p.data.customer} · {p.data.promotionType}</Typography>
          </Box>
        ) },
      { field: 'period', headerName: 'Window', minWidth: 150, flex: 1 },
      { field: 'stage', headerName: 'Stage', width: 120, cellRenderer: (p: { data: PromotionPlan }) => <StatusChip label={stageLabel[p.data.stage]} tone={stageTone(p.data.stage)} /> },
      { field: 'origin', headerName: 'Origin', width: 150, valueFormatter: (p) => originLabel[p.value as PromotionPlan['origin']] },
      { field: 'lines', headerName: 'Lines', type: 'rightAligned', width: 80 },
      { field: 'estimateUnits', headerName: 'Est. units', type: 'rightAligned', width: 110, valueFormatter: (p) => fmtInt(p.value) },
      { field: 'supportTotal', headerName: 'Support', type: 'rightAligned', width: 120, valueFormatter: (p) => fmtCurrency(p.value, { compact: true }) },
      { field: 'activation', headerName: 'On shelf', width: 190, valueFormatter: (p) => activationLabel[p.value as PromotionPlan['activation']] },
      { field: 'templateCode', headerName: 'Export template', minWidth: 200, flex: 1, valueFormatter: (p) => planTemplates.find((t) => t.code === p.value)?.name ?? p.value },
      { field: 'flags', headerName: 'Flags', minWidth: 220, flex: 1.4, valueFormatter: (p) => (p.value as string[]).join(' · ') },
    ],
    []
  );
  return <EnterpriseDataGrid<PromotionPlan> rowData={rows} columnDefs={columnDefs} height={400} gridOptions={{ onRowClicked: (e: RowClickedEvent<PromotionPlan>) => e.data && onOpen(e.data.id), getRowId: (p) => p.data.id }} />;
}

// ---------------------------------------------------------------------------------------------
// Plan workspace
// ---------------------------------------------------------------------------------------------

function PlanWorkspace({ plan, onBack, onStage, toast, setToast }: { plan: PromotionPlan; onBack: () => void; onStage: (s: PlanStage) => void; toast: string | null; setToast: (t: string | null) => void }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const router = useRouter();
  const [lines, setLines] = useState<PlanLine[]>(seedLines);
  const [selectedLine, setSelectedLine] = useState<number | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [templateCode, setTemplateCode] = useState(plan.templateCode);
  const editable = plan.stage === 'draft' || plan.stage === 'proposed';
  const line = lines.find((l) => l.id === selectedLine) ?? null;

  const totals = useMemo(() => {
    const units = lines.reduce((a, l) => a + l.estimateQty, 0);
    const support = lines.reduce((a, l) => a + lineSupport(l), 0);
    return { units, support, flags: lines.reduce((a, l) => a + l.flags.length, 0) };
  }, [lines]);
  const supportUsd = totals.support / plan.roe;
  const overBudget = budgetCheck.drawnUsd + supportUsd > budgetCheck.reservationUsd;
  const template = planTemplates.find((t) => t.code === templateCode)!;

  const onCell = (e: CellValueChangedEvent<PlanLine>) => {
    if (!e.data) return;
    const next = { ...e.data, [e.colDef.field as string]: Number(e.newValue) } as PlanLine;
    setLines((ls) => ls.map((l) => (l.id === next.id ? next : l)));
    setToast(`${next.sku}: support/unit ${fmtCurrency(supportUnit(next))} · line ${fmtCurrency(lineSupport(next), { compact: true })} — recomputed by the waterfall, flags re-evaluated`);
  };
  const acceptSuggested = () => {
    setLines((ls) => ls.map((l) => ({ ...l, estimateQty: l.suggestedQty })));
    setToast('All lines reset to CIP’s suggested quantity (history × forecast share, cover-capped).');
  };

  const columnDefs = useMemo<ColDef<PlanLine>[]>(
    () => [
      { field: 'sku', headerName: 'Product', minWidth: 210, flex: 1.4, pinned: 'left', cellRenderer: (p: { data: PlanLine }) => (
          <Box sx={{ lineHeight: 1.2 }}>
            <Typography variant="body2" noWrap>{p.data.product}</Typography>
            <Typography variant="caption" color="text.secondary">{p.data.sku} · {p.data.distributor} · {p.data.layer}</Typography>
          </Box>
        ) },
      { field: 'srp', headerName: 'Promo SRP', type: 'rightAligned', width: 115, editable, valueFormatter: (p) => fmtCurrency(p.value), cellClass: editable ? 'lab-editable' : undefined },
      { field: 'dealerMarginPct', headerName: 'Dealer %', type: 'rightAligned', width: 95, editable, valueFormatter: (p) => `${Math.round(p.value * 100)}%`, valueParser: (p) => Number(String(p.newValue).replace('%', '')) / (Number(p.newValue) > 1 ? 100 : 1) },
      { headerName: 'Dealer price', type: 'rightAligned', width: 115, valueGetter: (p) => (p.data ? dealerPrice(p.data) : 0), valueFormatter: (p) => fmtCurrency(p.value) },
      { field: 'costBasis', headerName: 'Cost basis', type: 'rightAligned', width: 115, valueFormatter: (p) => fmtCurrency(p.value), cellRenderer: (p: { data: PlanLine }) => (
          <Tooltip title={`${costSourceLabel[p.data.costSource]} · as of ${p.data.costAsOf}`} arrow>
            <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums', textDecoration: 'underline dotted', textDecorationColor: theme.palette.text.disabled, width: '100%', textAlign: 'right' }}>
              {fmtCurrency(p.data.costBasis)}
            </Typography>
          </Tooltip>
        ) },
      { headerName: 'Support / unit', type: 'rightAligned', width: 120, valueGetter: (p) => (p.data ? supportUnit(p.data) : 0), valueFormatter: (p) => fmtCurrency(p.value), cellStyle: (p) => (p.data && supportUnit(p.data) > p.data.normSupportUnit * 1.15 ? { color: theme.palette.warning.main } : null) },
      { field: 'estimateQty', headerName: 'Est. units', type: 'rightAligned', width: 105, editable, valueFormatter: (p) => fmtInt(p.value), cellClass: editable ? 'lab-editable' : undefined },
      { field: 'suggestedQty', headerName: 'CIP suggests', type: 'rightAligned', width: 115, valueFormatter: (p) => fmtInt(p.value), cellStyle: (p) => (p.data && p.data.estimateQty !== p.data.suggestedQty ? { color: theme.palette.text.secondary, fontStyle: 'italic' } : null) },
      { headerName: 'Line support', type: 'rightAligned', width: 125, valueGetter: (p) => (p.data ? lineSupport(p.data) : 0), valueFormatter: (p) => fmtCurrency(p.value, { compact: true }) },
      { field: 'coverWeeks', headerName: 'Cover', type: 'rightAligned', width: 90, valueFormatter: (p) => `${p.value} wk`, cellStyle: (p) => (Number(p.value) < 4 ? { color: theme.palette.warning.main } : null) },
      { headerName: 'On shelf', width: 170, valueGetter: (p) => (p.data?.listing ? `${p.data.listing.marketplace} · ${fmtCurrency(p.data.listing.lastPrice)}` : 'No monitored listing') },
      { headerName: 'Competitors', width: 120, valueGetter: (p) => (p.data ? `${p.data.competitors.mapped} mapped · ${p.data.competitors.priced} priced` : '') },
      { field: 'flags', headerName: 'Flags', minWidth: 240, flex: 1.6, valueFormatter: (p) => (p.value as string[]).join(' · '), cellStyle: (p) => ((p.value as string[]).length ? { color: theme.palette.warning.main } : null) },
    ],
    [editable, theme]
  );

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="plan-workspace">
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'flex-end' }} spacing={1}>
        <Box sx={{ minWidth: 0 }}>
          <Button size="small" onClick={onBack} sx={{ ml: -1, mb: 0.25 }}>‹ All plans</Button>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography variant="h6" sx={{ fontWeight: 650, lineHeight: 1.2 }}>{plan.name}</Typography>
            <StatusChip label={stageLabel[plan.stage]} tone={stageTone(plan.stage)} />
            <Typography variant="caption" color="text.secondary">{plan.id} · {originLabel[plan.origin]} · {plan.owner} · updated {plan.updated}</Typography>
          </Stack>
        </Box>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button size="small" variant="outlined" startIcon={<FileDownloadOutlinedIcon />} onClick={() => setExportOpen(true)} data-testid="plan-export">Export</Button>
          {plan.stage === 'draft' ? <Button size="small" variant="contained" onClick={() => onStage('proposed')} disabled={totals.flags > 0 && lines.some((l) => l.flags.some((f) => f.startsWith('no_cost_evidence')))} data-testid="plan-submit">Submit for approval</Button> : null}
          {plan.stage === 'proposed' ? (
            <>
              <Button size="small" variant="outlined" onClick={() => onStage('draft')}>Return to draft</Button>
              <Button size="small" variant="contained" onClick={() => onStage('approved')} data-testid="plan-approve">Approve</Button>
            </>
          ) : null}
          {plan.stage === 'approved' ? <Button size="small" variant="contained" onClick={() => onStage('active')}>Mark live</Button> : null}
        </Stack>
      </Stack>

      <LifecycleRail stages={lifecycleStages} labels={stageLabel} current={plan.stage === 'cancelled' ? undefined : plan.stage} />

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', xl: 'minmax(0, 3fr) minmax(300px, 1fr)' }, alignItems: 'start' }}>
        <Stack spacing={2} sx={{ minWidth: 0 }}>
          <Panel title="Plan parameters" subtitle="Customer, mechanic and window define the case; terms come from the customer’s defaults and can be overridden per line">
            <Box sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(auto-fit, minmax(150px, 1fr))' } }}>
              <TextField select size="small" label="Customer" value={plan.customerId} disabled={!editable} data-testid="plan-customer">
                {customers.filter((c) => c.id !== 107).map((c) => (
                  <MenuItem key={c.id} value={c.id}>{c.name}</MenuItem>
                ))}
              </TextField>
              <TextField select size="small" label="Promotion type" value={plan.promotionType} disabled={!editable}>
                {['Sell-Through PP', 'Sell out PP', 'Stock PP (In-Direct)'].map((t) => (
                  <MenuItem key={t} value={t}>{t}</MenuItem>
                ))}
              </TextField>
              <TextField size="small" label="Window start" type="date" value={plan.windowStart} disabled={!editable} InputLabelProps={{ shrink: true }} />
              <TextField size="small" label="Window end" type="date" value={plan.windowEnd} disabled={!editable} InputLabelProps={{ shrink: true }} />
              <TextField select size="small" label="Export template" value={templateCode} onChange={(e) => setTemplateCode(e.target.value)} data-testid="plan-template">
                {planTemplates.map((t) => (
                  <MenuItem key={t.code} value={t.code}>{t.name}{t.status !== 'mapped' ? ' — needs mapping' : ''}</MenuItem>
                ))}
              </TextField>
            </Box>
          </Panel>

          <HeadlineStrip columns={5}>
            <HeadlineFigure label="Lines" value={lines.length} compact caption={`${totals.flags} flag${totals.flags === 1 ? '' : 's'} · none block`} severity={totals.flags ? 'warn' : 'neutral'} />
            <HeadlineFigure label="Estimated units" value={fmtInt(totals.units)} compact caption={`CIP suggests ${fmtInt(lines.reduce((a, l) => a + l.suggestedQty, 0))}`} />
            <HeadlineFigure label="Total support" value={fmtCurrency(totals.support, { compact: true })} compact caption={`≈ $${fmtInt(supportUsd)} at ROE ${plan.roe}`} />
            <HeadlineFigure label="Budget after this plan" value={`${Math.round(((budgetCheck.drawnUsd + supportUsd) / budgetCheck.reservationUsd) * 100)}%`} compact severity={overBudget ? 'bad' : 'good'} caption={overBudget ? 'Over lineup reservation — flagged, not blocked' : 'Within lineup reservation'} />
            <HeadlineFigure label="On shelf today" value={lines.filter((l) => l.listing).length} unit={`of ${lines.length}`} compact caption="Lines with a monitored listing — activation checked once live" />
          </HeadlineStrip>

          <Panel
            title="Lines"
            subtitle={`${editable ? 'Edit SRP, dealer % and units in the grid; dealer price, support and totals recompute on the server-side waterfall. Click a row for the evidence behind it.' : 'Read-only at this stage. Click a row for the evidence behind it.'}${plan.id === 'CPR-26-1204' ? '' : ' Design fixture: lines and comparables shown are the CPR-26-1204 seed, not this case’s.'}`}
            actions={
              editable ? (
                <Stack direction="row" spacing={1}>
                  <Button size="small" onClick={acceptSuggested} data-testid="plan-accept-suggested">Use CIP quantities</Button>
                  <Button size="small" variant="outlined" onClick={() => setToast('Add line: pick product (token-resolved), distributor and POD-quarter layer; cost basis is suggested from the tier ladder.')}>Add line</Button>
                </Stack>
              ) : undefined
            }
            flush
          >
            {isMobile ? (
              <Stack spacing={1} sx={{ px: 2, pb: 2 }}>
                {lines.map((l) => (
                  <Card key={l.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                    <CardActionArea onClick={() => setSelectedLine(l.id)}>
                      <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>{l.product}</Typography>
                        <Typography variant="caption" color="text.secondary">{l.sku} · SRP {fmtCurrency(l.srp)} · cost {fmtCurrency(l.costBasis)}</Typography>
                        <Stack direction="row" spacing={2} sx={{ mt: 0.75 }}>
                          <Typography variant="caption">Support/unit <b>{fmtCurrency(supportUnit(l))}</b></Typography>
                          <Typography variant="caption">Units <b>{fmtInt(l.estimateQty)}</b></Typography>
                          <Typography variant="caption">Line <b>{fmtCurrency(lineSupport(l), { compact: true })}</b></Typography>
                        </Stack>
                        {l.flags.length ? <Typography variant="caption" color="warning.main" sx={{ display: 'block', mt: 0.5 }}>{l.flags.join(' · ')}</Typography> : null}
                      </CardContent>
                    </CardActionArea>
                  </Card>
                ))}
              </Stack>
            ) : (
              <Box sx={{ '& .lab-editable': { bgcolor: theme.palette.mode === 'dark' ? 'rgba(144,202,249,0.08)' : 'rgba(25,118,210,0.05)' } }}>
                <EnterpriseDataGrid<PlanLine>
                  rowData={lines}
                  columnDefs={columnDefs}
                  height={260}
                  gridOptions={{
                    // Editable cells edit on click; every other cell opens the evidence panel for that line.
                    onCellClicked: (e: CellClickedEvent<PlanLine>) => e.data && !e.colDef.editable && setSelectedLine(e.data.id),
                    onCellValueChanged: onCell,
                    getRowId: (p) => String(p.data.id),
                    singleClickEdit: true,
                    stopEditingWhenCellsLoseFocus: true,
                  }}
                />
              </Box>
            )}
          </Panel>

          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: 'minmax(0, 1fr)', xl: 'repeat(2, minmax(0, 1fr))' } }}>
            <Panel title="Comparable cases — same customer & family" subtitle="What was approved before and what it delivered (result ÷ estimate). Delivery is a stored fact, not a forecast." flush>
              <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" sx={{ '& td, & th': { py: 0.6, whiteSpace: 'nowrap' } }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Case</TableCell>
                    <TableCell>Window</TableCell>
                    <TableCell align="right">Support/unit</TableCell>
                    <TableCell align="right">Est → result</TableCell>
                    <TableCell align="right">Delivery</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {comparableCases.map((c) => (
                    <TableRow key={c.id} hover>
                      <TableCell>
                        <Typography variant="body2">{c.id}</Typography>
                        <Typography variant="caption" color="text.secondary">{c.customer}</Typography>
                      </TableCell>
                      <TableCell>{c.window}</TableCell>
                      <TableCell align="right">{fmtCurrency(c.supportUnit)}</TableCell>
                      <TableCell align="right">{fmtInt(c.estimate)} → {fmtInt(c.result)}</TableCell>
                      <TableCell align="right" sx={{ color: c.delivery < 0.9 ? 'warning.main' : 'success.main', fontWeight: 600 }}>{Math.round(c.delivery * 100)}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              </Box>
            </Panel>
            <Panel title="Where this plan draws from" subtitle="Cross-domain evidence, each a link to its owning workflow" flush>
              <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                <PanelRow severity="neutral" primary="Stock cover per line" secondary="UX2410F at 3.2 wk is below the 4.0 target — replenish before the window" figure="Stock & Sell-through" onClick={() => router.push('/design-lab/stock?lens=cover&product=63')} />
                <PanelRow severity="neutral" primary="Lineup forecast & budget reservation" secondary={`TechMart FY26 P09 lineup · 13-week forecast feeds suggested units · ${budgetCheck.source}`} figure="Planning" onClick={() => router.push('/design-lab/planning?customer=101')} />
                <PanelRow severity="neutral" primary="Listings for these SKUs" secondary="3 of 4 lines have a monitored TechMart listing; activation is checked daily once live" figure="Market & Listings" onClick={() => router.push('/design-lab/market?customer=101')} />
                <PanelRow severity="neutral" primary="Competitor products" secondary="4 approved mappings across these SKUs; no competitor prices observed yet — nothing inferred" figure="Market › Competition" onClick={() => router.push('/design-lab/market?lens=competition')} />
                <PanelRow severity="neutral" primary="Customer terms" secondary="TechMart dealer margin 15% · VAT 15% · export template techmart_promo_grid_v2" figure="Data & Stewardship" onClick={() => router.push('/design-lab/data?tab=masters&m=customers&id=101')} />
              </Stack>
            </Panel>
          </Box>
        </Stack>

        <Box sx={{ display: 'grid', gap: 2, minWidth: 0, gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(3, minmax(0, 1fr))', xl: 'minmax(0, 1fr)' }, alignItems: 'start' }}>
          <Panel title="Validation" subtitle="Flags explain; they never block a save. Submit needs cost evidence or a recorded manual override on every line." flush>
            <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
              {lines.flatMap((l) => l.flags.map((f) => ({ l, f }))).map(({ l, f }) => (
                <PanelRow key={`${l.id}-${f}`} severity={f.startsWith('no_cost') ? 'danger' : 'warning'} primary={l.sku} secondary={f} onClick={() => setSelectedLine(l.id)} />
              ))}
              {overBudget ? <PanelRow severity="warning" primary="Budget" secondary={`Plan takes reservation to ${Math.round(((budgetCheck.drawnUsd + supportUsd) / budgetCheck.reservationUsd) * 100)}% — soft check (hard enforcement off)`} /> : null}
              {!lines.some((l) => l.flags.length) && !overBudget ? (
                <Stack direction="row" spacing={1} alignItems="center" sx={{ px: 1.5, py: 1 }}>
                  <CheckCircleOutlineIcon fontSize="small" color="success" />
                  <Typography variant="body2">No flags on this plan.</Typography>
                </Stack>
              ) : null}
            </Stack>
          </Panel>
          <Panel title="Export target" subtitle="The plan leaves CIP in the customer’s own workbook layout">
            <Stack spacing={1}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{template.name}</Typography>
                <CapabilityStatus status={template.status === 'mapped' ? 'live' : 'partial'} size="inline" />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                {template.direction} · {template.mappedFields}/{template.canonicalFields} canonical fields mapped · learned from {template.learnedFrom}
              </Typography>
              {template.status !== 'mapped' ? (
                <Alert severity="warning" variant="outlined" sx={{ py: 0 }}>
                  {template.canonicalFields - template.mappedFields} canonical fields have no column in this template. Required: promotion_type. <NextLink href="/design-lab/funding?lens=templates&template=officeworld_promo_v1">Finish mapping</NextLink>
                </Alert>
              ) : null}
            </Stack>
          </Panel>
          <CapabilityLedger items={commercialCapabilities.planner.slice(0, 5)} title="What works on this screen" />
        </Box>
      </Box>

      <LineEvidencePanel line={line} onClose={() => setSelectedLine(null)} plan={plan} />

      <Dialog open={exportOpen} onClose={() => setExportOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Export {plan.id}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 0.5 }}>
            <FormControl size="small" fullWidth>
              <InputLabel id="export-template">Template</InputLabel>
              <Select labelId="export-template" label="Template" value={templateCode} onChange={(e) => setTemplateCode(e.target.value)}>
                {planTemplates.map((t) => (
                  <MenuItem key={t.code} value={t.code} disabled={t.direction === 'import only'}>
                    {t.name} · {t.owner}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <Typography variant="body2" color="text.secondary">
              Rendered as versioned XLSX (v{plan.stage === 'settled' ? 3 : 1}) in the <b>{template.name}</b> layout: {template.sheets.join(', ')} · header row {template.headerRow}. The file is recorded against the case so approvals refer to an exact version.
            </Typography>
            {template.status !== 'mapped' ? (
              <Alert severity="error" variant="outlined" icon={<ErrorOutlineIcon />}>
                This template cannot render yet — required canonical field <b>promotion_type</b> has no target column. Map it in Plan templates first.
              </Alert>
            ) : (
              <Alert severity="success" variant="outlined">All required canonical fields have a target column. Computed fields (support/unit, total support) are filled on export.</Alert>
            )}
            <Divider />
            <Typography variant="caption" color="text.secondary">
              Today the export is one frozen 32-column layout in code. Template-driven export is the N-0010 delta; the import side of the same profile already exists in the database.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setExportOpen(false)}>Cancel</Button>
          <Button variant="contained" disabled={template.status !== 'mapped'} onClick={() => { setExportOpen(false); setToast(`${plan.id} exported as ${template.name} v1 — recorded on the case.`); }} data-testid="plan-export-confirm">
            Export XLSX
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar open={!!toast} autoHideDuration={4500} onClose={() => setToast(null)} message={toast} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Stack>
  );
}

function LineEvidencePanel({ line, plan, onClose }: { line: PlanLine | null; plan: PromotionPlan; onClose: () => void }) {
  return (
    <EntityContextPanel
      open={!!line}
      onClose={onClose}
      kicker={line ? `${plan.id} · line ${line.id}` : undefined}
      title={line ? line.product : ''}
      subtitle={line ? `${line.sku} · ${line.distributor} · layer ${line.layer}` : undefined}
      width={500}
      figures={
        line ? (
          <HeadlineStrip columns={3}>
            <HeadlineFigure label="Support / unit" value={fmtCurrency(supportUnit(line))} dense caption={`cost ${fmtCurrency(line.costBasis)} − dealer ${fmtCurrency(dealerPrice(line))}`} severity={supportUnit(line) > line.normSupportUnit * 1.15 ? 'warn' : 'neutral'} />
            <HeadlineFigure label="Norm (comparables)" value={fmtCurrency(line.normSupportUnit)} dense caption={`${line.comparables} comparable case${line.comparables === 1 ? '' : 's'}`} />
            <HeadlineFigure label="Line support" value={fmtCurrency(lineSupport(line), { compact: true })} dense caption={`${fmtInt(line.estimateQty)} units`} />
          </HeadlineStrip>
        ) : null
      }
      related={
        line
          ? [
              { label: 'Stock cover & sell-through', href: `/design-lab/stock?lens=cover&product=${line.productId}`, hint: `Stock & Sell-through · ${line.coverWeeks} wk cover` },
              { label: 'Monitored listings for this SKU', href: `/design-lab/market?product=${line.productId}`, hint: line.listing ? `Market & Listings · last ${fmtCurrency(line.listing.lastPrice)} on ${line.listing.marketplace}` : 'Market & Listings · none yet' },
              { label: 'Competitor mappings', href: `/design-lab/market?lens=competition&product=${line.productId}`, hint: `Market › Competition · ${line.competitors.mapped} mapped, ${line.competitors.priced} priced` },
              { label: 'Product master', href: `/design-lab/data?tab=masters&m=products&id=${line.productId}`, hint: 'Data & Stewardship' },
            ]
          : []
      }
      footer={line ? <Button variant="outlined" size="small" onClick={onClose}>Close</Button> : null}
    >
      {line ? (
        <Stack spacing={2.5}>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>Waterfall</Typography>
            <KeyValueList
              items={[
                { k: 'Promo SRP (incl VAT)', v: fmtCurrency(line.srp) },
                { k: 'Ex VAT', v: fmtCurrency(line.srp / (1 + line.vatRate)) },
                { k: `Dealer price (−${Math.round(line.dealerMarginPct * 100)}%)`, v: fmtCurrency(dealerPrice(line)) },
                { k: 'Cost basis', v: `${fmtCurrency(line.costBasis)} · ${costSourceLabel[line.costSource]}` },
                { k: 'Support / unit', v: <b>{fmtCurrency(supportUnit(line))}</b> },
              ]}
            />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>Cost evidence — tier ladder</Typography>
            <Stack spacing={0.5} sx={{ mt: 1 }}>
              {costEvidenceForLine(line).map((t) => (
                <Stack key={t.tier} direction="row" spacing={1} alignItems="flex-start" sx={{ opacity: t.value === null ? 0.5 : 1 }}>
                  {t.chosen ? <CheckCircleOutlineIcon fontSize="small" color="primary" sx={{ mt: 0.2 }} /> : <Box sx={{ width: 20, flexShrink: 0 }} />}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" sx={{ fontWeight: t.chosen ? 600 : 400 }}>{t.tier}</Typography>
                    <Typography variant="caption" color="text.secondary">{t.note}{t.asOf ? ` · as of ${t.asOf}` : ''}</Typography>
                  </Box>
                  <Typography variant="body2" sx={{ fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>{t.value === null ? 'no data' : fmtCurrency(t.value)}</Typography>
                </Stack>
              ))}
            </Stack>
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>Quantity evidence</Typography>
            <KeyValueList
              items={[
                { k: 'Last comparable window', v: `${fmtInt(line.historyUnits)} units` },
                { k: '13-week forecast', v: `${fmtInt(line.forecast13w)} units` },
                { k: 'Stock cover', v: `${line.coverWeeks} weeks${line.coverWeeks < 4 ? ' — below target' : ''}` },
                { k: 'CIP suggested', v: `${fmtInt(line.suggestedQty)} units` },
                { k: 'Planner estimate', v: `${fmtInt(line.estimateQty)} units` },
              ]}
            />
          </Box>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>Market evidence</Typography>
            <KeyValueList
              items={[
                { k: 'Monitored listing', v: line.listing ? `${line.listing.marketplace} · ${fmtCurrency(line.listing.lastPrice)} · ${activationLabel[line.listing.activation]}` : 'None — add one in Market & Listings' },
                { k: 'Competitor SKUs mapped', v: `${line.competitors.mapped}` },
                { k: 'Competitor prices observed', v: line.competitors.priced ? `${line.competitors.priced}` : 'None — no impact inferred' },
              ]}
            />
          </Box>
          {line.flags.length ? (
            <Alert severity="warning" variant="outlined">
              {line.flags.map((f) => (
                <Typography key={f} variant="body2">{f}</Typography>
              ))}
            </Alert>
          ) : null}
        </Stack>
      ) : null}
    </EntityContextPanel>
  );
}