'use client';

import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import { Alert, Box, Button, Card, CardActionArea, CardContent, Snackbar, Stack, Typography, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';

import { lifecycleStages, promotionPlans, stageLabel, type PlanStage } from '../fixtures/commercial';
import { fmtCurrency, fmtInt, tenant } from '../fixtures/entities';
import { ageingBuckets, fundingBook, fundingCases, statusLabel, type CaseStatus, type FundingCase } from '../fixtures/funding';
import { CapabilityStatus } from '../primitives/CapabilityStatus';
import { CategoryBars } from '../primitives/charts';
import { LensTabs, ScopeBar, StatusChip } from '../primitives/controls';
import { DomainHeader } from '../primitives/DomainHeader';
import { EntityContextPanel, KeyValueList } from '../primitives/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '../primitives/HeadlineFigure';
import { LifecycleRail } from '../primitives/LifecycleRail';
import { Panel, PanelRow } from '../primitives/Panel';
import { labDomains } from '../shell/labNav';
import { PlanTemplatesSurface } from './PlanTemplatesSurface';
import { PromotionPlannerSurface } from './PromotionPlannerSurface';

const tone = (s: CaseStatus) => (s === 'blocked' ? 'danger' : s === 'evidence_pending' ? 'warning' : s === 'open' ? 'info' : s === 'settled' ? 'success' : 'neutral');

type Lens = 'planner' | 'book' | 'claims' | 'payments' | 'templates' | 'pricing' | 'budgets';

/** Settlement-side statuses sit in the ended → settled half of the one promotion lifecycle. */
const stageForCase = (s: CaseStatus): PlanStage => (s === 'settled' ? 'settled' : 'ended');

export function FundingSurface() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const router = useRouter();
  const search = useSearchParams();
  const lens = (search.get('lens') as Lens) || 'book';
  const status = search.get('status') as CaseStatus | null;
  const sku = search.get('sku');
  const setParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(search.toString());
      Object.entries(patch).forEach(([k, v]) => (v === null ? next.delete(k) : next.set(k, v)));
      router.replace(`/design-lab/funding?${next.toString()}`, { scroll: false });
    },
    [router, search]
  );
  const setParam = useCallback((k: string, v: string | null) => setParams({ [k]: v }), [setParams]);

  const [cases, setCases] = useState<FundingCase[]>(fundingCases);
  const [selectedId, setSelectedId] = useState<string | null>(search.get('case'));
  const [toast, setToast] = useState<string | null>(null);
  const selected = cases.find((c) => c.id === selectedId) ?? null;

  const rows = useMemo(() => cases.filter((c) => (!status || c.status === status) && (!sku || c.sku === sku)), [cases, status, sku]);
  const counts = useMemo(() => {
    const m: Partial<Record<CaseStatus, number>> = {};
    cases.forEach((c) => (m[c.status] = (m[c.status] ?? 0) + 1));
    return m;
  }, [cases]);

  const decide = (id: string, decision: 'approved' | 'blocked') => {
    setCases((cs) => cs.map((c) => (c.id === id ? { ...c, status: decision, blockedReason: decision === 'blocked' ? 'Returned by approver — evidence insufficient' : undefined, settled: decision === 'approved' ? Math.round(c.claimed * 0.5) : c.settled, outstanding: decision === 'approved' ? c.claimed - Math.round(c.claimed * 0.5) : c.outstanding } : c)));
    setToast(decision === 'approved' ? `${id} approved — first 50% released to settlement` : `${id} returned to customer with reason`);
    setSelectedId(null);
  };

  const columnDefs = useMemo<ColDef<FundingCase>[]>(
    () => [
      { field: 'id', headerName: 'Case', width: 120, pinned: 'left' },
      { field: 'customer', headerName: 'Customer', minWidth: 160, flex: 1 },
      { field: 'programme', headerName: 'Programme', minWidth: 190, flex: 1.2 },
      { field: 'product', headerName: 'Product', minWidth: 200, flex: 1.3, valueGetter: (p) => p.data?.sku, cellRenderer: (p: { data: FundingCase }) => (
          <Box sx={{ lineHeight: 1.2 }}>
            <Typography variant="body2" noWrap>{p.data.product}</Typography>
            <Typography variant="caption" color="text.secondary">{p.data.sku}</Typography>
          </Box>
        ) },
      { field: 'units', headerName: 'Units', type: 'rightAligned', width: 90, valueFormatter: (p) => fmtInt(p.value) },
      { field: 'claimed', headerName: 'Claimed', type: 'rightAligned', width: 120, valueFormatter: (p) => fmtCurrency(p.value) },
      { field: 'outstanding', headerName: 'Outstanding', type: 'rightAligned', width: 130, valueFormatter: (p) => fmtCurrency(p.value), sort: 'desc' },
      { field: 'ageDays', headerName: 'Age', type: 'rightAligned', width: 80, valueFormatter: (p) => `${p.value}d`, cellStyle: (p) => (Number(p.value) > 60 ? { color: theme.palette.error.main } : Number(p.value) > 30 ? { color: theme.palette.warning.main } : null) },
      { field: 'status', headerName: 'Status', width: 160, cellRenderer: (p: { data: FundingCase }) => <StatusChip label={statusLabel[p.data.status]} tone={tone(p.data.status)} /> },
      { field: 'blockedReason', headerName: 'Blocked reason', minWidth: 240, flex: 1.5, valueFormatter: (p) => p.value ?? '' },
    ],
    [theme]
  );

  const chips = (['open', 'evidence_pending', 'blocked', 'approved', 'settled'] as CaseStatus[]).map((s) => ({
    key: s,
    label: `${statusLabel[s]} · ${counts[s] ?? 0}`,
    active: status === s,
    onToggle: () => setParam('status', status === s ? null : s),
    tone: s === 'blocked' ? ('danger' as const) : s === 'evidence_pending' ? ('warning' as const) : s === 'settled' ? ('success' as const) : ('default' as const),
  }));

  const evidenceRow = (label: string, ok: boolean) => (
    <Stack direction="row" spacing={1} alignItems="center" key={label}>
      {ok ? <CheckCircleOutlineIcon fontSize="small" color="success" /> : <RadioButtonUncheckedIcon fontSize="small" color="disabled" />}
      <Typography variant="body2" color={ok ? 'text.primary' : 'text.secondary'}>
        {label} {ok ? '' : '— missing'}
      </Typography>
    </Stack>
  );

  const domain = labDomains.find((d) => d.id === 'funding')!;
  const planningCounts = lifecycleStages.reduce<Partial<Record<PlanStage, number>>>((m, s) => ({ ...m, [s]: promotionPlans.filter((p) => p.stage === s).length }), {});

  return (
    <Box data-testid="funding-surface">
      <DomainHeader
        crumbs={[{ label: domain.label }]}
        title={domain.label}
        description={domain.what}
        meta={`${tenant.period} · ${promotionPlans.filter((p) => ['draft', 'proposed', 'approved'].includes(p.stage)).length} plans in planning · ${promotionPlans.filter((p) => p.stage === 'active').length} live · ${fundingBook.cases} in settlement · book ${fmtCurrency(fundingBook.book)} · delivery rate ${(fundingBook.deliveryRate * 100).toFixed(0)}%`}
        actions={
          <>
            <Button variant="outlined" size="small" href="/design-lab/reports">Open in Reports</Button>
            <Button variant="outlined" size="small" href="/design-lab/data?tab=imports">Import claims / payments</Button>
            <Button variant="contained" size="small" onClick={() => { setParam('lens', 'planner'); }}>New promotion plan</Button>
          </>
        }
      />
      <LensTabs
        value={lens}
        onChange={(l) => setParams({ plan: null, stage: null, template: null, lens: l === 'book' ? null : l })}
        ariaLabel="Promotions & Funding lenses"
        lenses={[
          { value: 'planner', label: 'Promotion planner', count: (planningCounts.draft ?? 0) + (planningCounts.proposed ?? 0) + (planningCounts.approved ?? 0) },
          { value: 'book', label: 'Case book', count: fundingBook.cases },
          { value: 'claims', label: 'Claims evidence' },
          { value: 'payments', label: 'Payments' },
          { value: 'templates', label: 'Plan templates' },
          { value: 'pricing', label: 'Terms & assumptions' },
          { value: 'budgets', label: 'Budget ledger' },
        ]}
      />

      {lens === 'planner' ? <PromotionPlannerSurface /> : null}
      {lens === 'templates' ? <PlanTemplatesSurface /> : null}

      {lens === 'book' ? (
        <Stack spacing={2} sx={{ mt: 2 }}>
          <Alert severity="info" variant="outlined" icon={false} sx={{ '& .MuiAlert-message': { width: '100%' } }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }} justifyContent="space-between">
              <Typography variant="body2">
                <b>The Case book is the settlement half of the same lifecycle.</b> Cases here were authored or approved in the Promotion planner; claimed, settled and blocked describe what happened after the window ended.
              </Typography>
              <Box sx={{ minWidth: { md: 520 } }}>
                <LifecycleRail stages={lifecycleStages} labels={stageLabel} counts={{ ...planningCounts, ended: cases.filter((c) => c.status !== 'settled').length, settled: cases.filter((c) => c.status === 'settled').length }} dense onSelect={(s) => (s === 'ended' || s === 'settled' ? setParam('status', s === 'settled' ? 'settled' : null) : router.push(`/design-lab/funding?lens=planner&stage=${s}`))} />
              </Box>
            </Stack>
          </Alert>
          <HeadlineStrip columns={5}>
            <HeadlineFigure label="Book total" value={fmtCurrency(fundingBook.book, { compact: true })} compact caption={`${fundingBook.cases} cases`} />
            <HeadlineFigure label="Settled" value={fmtCurrency(fundingBook.settled, { compact: true })} compact severity="good" caption={`Delivery rate ${(fundingBook.deliveryRate * 100).toFixed(0)}%`} />
            <HeadlineFigure label="Outstanding" value={fmtCurrency(fundingBook.outstanding, { compact: true })} compact caption="Claimed − settled" />
            <HeadlineFigure label="Blocked" value={fundingBook.blocked} unit="cases" compact severity="bad" caption={fmtCurrency(fundingBook.blockedValue, { compact: true })} onClick={() => setParam('status', 'blocked')} />
            <HeadlineFigure label="Awaiting approval" value={counts.open ?? 0} unit="cases" compact severity="warn" onClick={() => setParam('status', 'open')} caption="Your decision needed" />
          </HeadlineStrip>

          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '2fr 3fr' } }}>
            <Panel title="Outstanding by age" subtitle="Unsettled value by days since claim">
              <CategoryBars data={ageingBuckets} x="bucket" y="value" height={170} format={(v) => fmtCurrency(v, { compact: true })} colorBy={(r) => (String(r.bucket) === '60d+' ? theme.palette.error.main : String(r.bucket) === '31–60d' ? theme.palette.warning.main : theme.palette.primary.main)} />
            </Panel>
            <Panel title="Blocked cases — reasons" subtitle="Each reason links to the evidence or resolution step that clears it" flush>
              <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
                {cases
                  .filter((c) => c.status === 'blocked')
                  .slice(0, 5)
                  .map((c) => (
                    <PanelRow key={c.id} severity="danger" primary={`${c.id} · ${c.customer}`} secondary={c.blockedReason} figure={fmtCurrency(c.outstanding, { compact: true })} onClick={() => setSelectedId(c.id)} />
                  ))}
              </Stack>
            </Panel>
          </Box>

          <ScopeBar chips={chips} summary={`${rows.length} of ${cases.length} cases${sku ? ` · SKU ${sku}` : ''}`} onClear={() => setParams({ status: null, sku: null })} />

          <ModuleDataSection isEmpty={rows.length === 0} empty={{ title: 'No cases in this scope', description: 'Clear the status chips or import claim evidence to create cases.', primary: { label: 'Clear scope', onClick: () => setParam('status', null) } }}>
            {isMobile ? (
              <Stack spacing={1} data-testid="funding-record-cards">
                {rows.map((c) => (
                  <Card key={c.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                    <CardActionArea onClick={() => setSelectedId(c.id)}>
                      <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                          <Box sx={{ minWidth: 0 }}>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>{c.customer} · {c.id}</Typography>
                            <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>{c.programme} · {c.sku}</Typography>
                          </Box>
                          <StatusChip label={statusLabel[c.status]} tone={tone(c.status)} />
                        </Stack>
                        <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
                          <Typography variant="caption">Claimed <b>{fmtCurrency(c.claimed, { compact: true })}</b></Typography>
                          <Typography variant="caption">Outstanding <b>{fmtCurrency(c.outstanding, { compact: true })}</b></Typography>
                          <Typography variant="caption">Age <b>{c.ageDays}d</b></Typography>
                        </Stack>
                        {c.blockedReason ? <Typography variant="caption" color="error.main" sx={{ display: 'block', mt: 0.5 }}>{c.blockedReason}</Typography> : null}
                      </CardContent>
                    </CardActionArea>
                  </Card>
                ))}
              </Stack>
            ) : (
              <EnterpriseDataGrid<FundingCase> rowData={rows} columnDefs={columnDefs} height={420} gridOptions={{ onRowClicked: (e: RowClickedEvent<FundingCase>) => e.data && setSelectedId(e.data.id), getRowId: (p) => p.data.id }} />
            )}
          </ModuleDataSection>
        </Stack>
      ) : null}

      {lens === 'claims' || lens === 'payments' || lens === 'pricing' ? (
        <Box sx={{ mt: 2 }}>
          <ModuleDataSection
            isEmpty
            empty={{
              title: lens === 'claims' ? 'Claim evidence is matched per case' : lens === 'payments' ? 'Payment evidence and delivery rate' : 'Terms & assumptions',
              description: lens === 'claims' ? '64 claim rows from Metro_claims_P08.xlsx are validated and awaiting apply (4 unresolved tokens). Open the import job to finish stewarding.' : lens === 'payments' ? 'Payment evidence links settled value to cases. Delivery rate = result ÷ estimate per case.' : 'Customer margin and rebate defaults plus per-SKU assumptions feed the waterfall in the planner (dealer price → support per unit). Edited here, applied on the next recompute.',
              primary: { label: lens === 'pricing' ? 'Open customer masters' : 'Open Import Center', href: lens === 'pricing' ? '/design-lab/data?tab=masters&m=customers' : '/design-lab/data?tab=imports' },
            }}
          >
            <span />
          </ModuleDataSection>
        </Box>
      ) : null}

      {lens === 'budgets' ? (
        <Box sx={{ mt: 2 }} data-testid="lens-substrate">
          <Panel
            title={
              <Stack direction="row" spacing={1} alignItems="center">
                <span>Budget ledger — data only</span>
                <CapabilityStatus status="substrate" />
              </Stack>
            }
          >
            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 760 }}>
              Allocation → commitment → actual tables (fact_budget_*) exist with no writer and no rows. The planner’s budget check therefore uses the lineup-derived profit reservation instead, and says so on the figure. When a budget import or ledger writer lands, this lens shows allocation vs drawn per programme and period; until then nothing is shown rather than a placeholder.
            </Typography>
          </Panel>
        </Box>
      ) : null}

      <EntityContextPanel
        open={!!selected}
        onClose={() => setSelectedId(null)}
        kicker={selected ? statusLabel[selected.status] : undefined}
        title={selected ? `${selected.id} · ${selected.customer}` : ''}
        subtitle={selected ? `${selected.programme} · ${selected.period}` : undefined}
        width={480}
        figures={
          selected ? (
            <HeadlineStrip columns={3}>
              <HeadlineFigure label="Claimed" value={fmtCurrency(selected.claimed, { compact: true })} dense caption={`${fmtInt(selected.units)} units × ${fmtCurrency(selected.supportPerUnit)}`} />
              <HeadlineFigure label="Outstanding" value={fmtCurrency(selected.outstanding, { compact: true })} dense severity={selected.outstanding ? 'warn' : 'good'} />
              <HeadlineFigure label="Age" value={selected.ageDays} unit="days" dense severity={selected.ageDays > 60 ? 'bad' : 'neutral'} />
            </HeadlineStrip>
          ) : null
        }
        related={
          selected
            ? [
                { label: 'Open in Promotion planner', href: `/design-lab/funding?lens=planner&stage=ended`, hint: 'Promotions & Funding › same case, planning view' },
                { label: 'Was the promotion live at the planned price?', href: `/design-lab/market?lens=activation&product=${products_idFor(selected.sku)}`, hint: 'Market & Listings › Activation' },
                { label: 'Stock cover for this SKU', href: `/design-lab/stock?lens=cover&product=${products_idFor(selected.sku)}`, hint: 'Stock & Sell-through › Cover' },
                { label: `Lineup plan — ${selected.customer}`, href: `/design-lab/planning?customer=${selected.customerId}`, hint: 'Planning › Lineup cases' },
                { label: 'Customer master & terms', href: `/design-lab/data?tab=masters&m=customers&id=${selected.customerId}`, hint: 'Data & Stewardship › Customers' },
              ]
            : []
        }
        footer={
          selected && (selected.status === 'open' || selected.status === 'blocked' || selected.status === 'evidence_pending') ? (
            <>
              <Button variant="outlined" color="error" size="small" onClick={() => decide(selected.id, 'blocked')} data-testid="case-return">
                Return with reason
              </Button>
              <Button variant="contained" size="small" onClick={() => decide(selected.id, 'approved')} disabled={!selected.evidence.claim || !selected.evidence.sellThrough} data-testid="case-approve">
                Approve
              </Button>
            </>
          ) : selected ? (
            <Button variant="outlined" size="small" onClick={() => setSelectedId(null)}>Close</Button>
          ) : null
        }
      >
        {selected ? (
          <Stack spacing={2}>
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>Lifecycle</Typography>
              <Box sx={{ mt: 1 }}>
                <LifecycleRail stages={lifecycleStages} labels={stageLabel} current={stageForCase(selected.status)} dense />
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
                Planned and approved in the Promotion planner; the window has ended and the case is now in settlement.
              </Typography>
            </Box>
            {selected.blockedReason ? <Alert severity="error" variant="outlined">{selected.blockedReason}</Alert> : null}
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>Evidence</Typography>
              <Stack spacing={0.75} sx={{ mt: 1 }}>
                {evidenceRow('Claim file matched', selected.evidence.claim)}
                {evidenceRow('Sell-through corroborates claimed units', selected.evidence.sellThrough)}
                {evidenceRow('Payment evidence', selected.evidence.payment)}
              </Stack>
              {!selected.evidence.claim || !selected.evidence.sellThrough ? (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                  Approve is disabled until claim and sell-through evidence are present — the platform does not approve on assertion.
                </Typography>
              ) : null}
            </Box>
            <KeyValueList
              items={[
                { k: 'Product', v: `${selected.product} (${selected.sku})` },
                { k: 'Units claimed', v: fmtInt(selected.units) },
                { k: 'Support per unit', v: fmtCurrency(selected.supportPerUnit) },
                { k: 'Settled to date', v: fmtCurrency(selected.settled) },
                { k: 'Period', v: selected.period },
              ]}
            />
          </Stack>
        ) : null}
      </EntityContextPanel>
      <Snackbar open={!!toast} autoHideDuration={3500} onClose={() => setToast(null)} message={toast} anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }} />
    </Box>
  );
}

function products_idFor(sku: string): number {
  const map: Record<string, number> = { UX2780Q: 61, UX3440W: 62, UX2410F: 63, 'NBP14-I7': 71, 'NBP16-I9': 72, 'NBE15-I5': 73, 'DK-TB4': 81, 'KB-MX': 82, 'WC-4K': 83, 'PR-L2600': 91 };
  return map[sku] ?? 61;
}
