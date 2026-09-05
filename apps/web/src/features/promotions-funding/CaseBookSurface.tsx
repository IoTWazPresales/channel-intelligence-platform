'use client';

import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUnchecked';
import type { ColDef, RowClickedEvent } from 'ag-grid-community';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Stack,
  Typography,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { fmtCompact, fmtInt } from '@/features/promotions-funding/format';
import {
  LIFECYCLE_STAGES,
  STAGE_LABEL,
  stageTone,
  type PlanStage,
} from '@/features/promotions-funding/lifecycle';
import type { CporCaseListRow, CporCasesPage } from '@/features/promotions-funding/types';
import { apiGet, apiPost } from '@/lib/api';
import { EntityContextPanel, KeyValueList } from '@/features/workbench-ui/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { LifecycleRail } from '@/features/workbench-ui/LifecycleRail';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';
import { ScopeBar, StatusChip } from '@/features/workbench-ui/controls';

type SettlementBook = {
  open_case_count?: number;
  book_total?: number;
  settled_amount?: number;
  outstanding_amount?: number;
  blocked_amount?: number;
  currency_code?: string;
};

type BookFilter = 'proposed' | 'ended' | 'settled' | 'blocked' | 'draft' | null;

function fxBlockedReason(row: CporCaseListRow): string | undefined {
  const r = row.settle_readiness;
  if (!r || r.fx_settle_allowed !== false) return undefined;
  if (!r.fx_declared) return 'FX undeclared — no positive ROE snapshot';
  if (!r.fx_mode_declared) return 'FX mode not declared (booked / floating)';
  return 'FX settle blocked';
}

function isOpenBookStatus(status: string): boolean {
  const s = (status || '').toLowerCase();
  return s !== 'settled' && s !== 'cancelled';
}

function isFxBlocked(row: CporCaseListRow): boolean {
  return row.settle_readiness?.fx_settle_allowed === false;
}

function ageDays(row: CporCaseListRow): number | null {
  if (!row.last_claim_sale_date) return null;
  const sale = Date.parse(row.last_claim_sale_date);
  if (!Number.isFinite(sale)) return null;
  return Math.max(0, Math.floor((Date.now() - sale) / 86_400_000));
}

export function CaseBookSurface() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'), { noSsr: true });
  const router = useRouter();
  const search = useSearchParams();
  const qc = useQueryClient();
  const statusParam = search.get('status');
  const filter: BookFilter =
    statusParam === 'blocked'
      ? 'blocked'
      : statusParam === 'proposed' ||
          statusParam === 'ended' ||
          statusParam === 'settled' ||
          statusParam === 'draft'
        ? statusParam
        : null;
  const selectedParam = search.get('case');
  const [toastAction, setToastAction] = useState<string | null>(null);

  const setParams = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(search.toString());
      Object.entries(patch).forEach(([k, v]) => (v == null || v === '' ? next.delete(k) : next.set(k, v)));
      const qs = next.toString();
      router.replace(qs ? `/commercial-planner/cpor-cases?${qs}` : '/commercial-planner/cpor-cases', {
        scroll: false,
      });
    },
    [router, search],
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['cpor', 'cases', 'book'],
    queryFn: ({ signal }) =>
      apiGet<CporCasesPage>('/api/v1/cpor/cases?page=1&page_size=500', { signal }),
  });

  const { data: book } = useQuery({
    queryKey: ['cpor', 'settlement', 'book'],
    queryFn: ({ signal }) => apiGet<SettlementBook>('/api/v1/cpor/settlement/book', { signal }),
    staleTime: 15_000,
  });

  const counts = data?.status_counts ?? {};
  const proposedN = counts.proposed ?? 0;
  const ccy = book?.currency_code ?? 'ZAR';
  const allItems = data?.items ?? [];
  const fxBlockedRows = allItems.filter(isFxBlocked);
  const fxBlockedPositive = fxBlockedRows.filter(
    (r) => isOpenBookStatus(r.status) && (Number(r.outstanding_amount) || 0) > 0,
  );
  const negativeSupport = allItems.filter(
    (r) => isOpenBookStatus(r.status) && (Number(r.outstanding_amount) || 0) < -0.005,
  );

  const rows = useMemo(() => {
    if (filter === 'blocked') return fxBlockedPositive;
    if (filter) return allItems.filter((r) => r.status === filter);
    return allItems;
  }, [allItems, filter, fxBlockedPositive]);

  const selectedId = selectedParam && /^\d+$/.test(selectedParam) ? Number(selectedParam) : null;
  const selected = allItems.find((r) => r.id === selectedId) ?? rows.find((r) => r.id === selectedId) ?? null;

  const ageing = useMemo(() => {
    const buckets = [
      { bucket: '0–14d', value: 0 },
      { bucket: '15–30d', value: 0 },
      { bucket: '31–60d', value: 0 },
      { bucket: '60d+', value: 0 },
    ];
    for (const r of allItems) {
      if (r.status === 'settled') continue;
      const d = ageDays(r);
      if (d == null) continue;
      const v = Number(r.outstanding_amount) || 0;
      if (d <= 14) buckets[0].value += v;
      else if (d <= 30) buckets[1].value += v;
      else if (d <= 60) buckets[2].value += v;
      else buckets[3].value += v;
    }
    return buckets;
  }, [allItems]);
  const hasClaimAge = allItems.some((r) => r.last_claim_sale_date);

  const transition = useMutation({
    mutationFn: (payload: { id: number; action: string; comment?: string }) =>
      apiPost(`/api/v1/cpor/cases/${payload.id}/transition`, {
        action: payload.action,
        comment: payload.comment,
      }),
    onSuccess: async (_r, vars) => {
      setToastAction(`${vars.action} recorded`);
      setParams({ case: null });
      await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', 'book'] });
    },
  });

  const columnDefs = useMemo<ColDef<CporCaseListRow>[]>(
    () => [
      { field: 'case_code', headerName: 'Case', width: 130, pinned: 'left' },
      { field: 'customer_name', headerName: 'Customer', minWidth: 160, flex: 1 },
      { field: 'promotion_type', headerName: 'Type', minWidth: 150, flex: 1 },
      {
        field: 'estimate_qty_sum',
        headerName: 'Est. units',
        type: 'rightAligned',
        width: 110,
        valueFormatter: (p) => fmtInt(p.value as number | null),
      },
      {
        field: 'owed_amount',
        headerName: 'Owed',
        type: 'rightAligned',
        width: 120,
        valueFormatter: (p) => fmtCompact(p.value as number | null, p.data?.currency_code ?? ccy),
      },
      {
        field: 'outstanding_amount',
        headerName: 'Outstanding',
        type: 'rightAligned',
        width: 130,
        valueFormatter: (p) => fmtCompact(p.value as number | null, p.data?.currency_code ?? ccy),
        sort: 'desc',
      },
      {
        colId: 'age',
        headerName: 'Age',
        type: 'rightAligned',
        width: 80,
        valueGetter: (p) => ageDays(p.data as CporCaseListRow),
        valueFormatter: (p) => (p.value == null ? '—' : `${p.value}d`),
      },
      {
        field: 'status',
        headerName: 'Status',
        width: 120,
        cellRenderer: (p: { data?: CporCaseListRow }) =>
          p.data ? (
            <StatusChip label={STAGE_LABEL[p.data.status as PlanStage] ?? p.data.status} tone={stageTone(p.data.status)} />
          ) : null,
      },
      {
        colId: 'blocked_reason',
        headerName: 'Blocked reason',
        minWidth: 220,
        flex: 1.4,
        valueGetter: (p) => fxBlockedReason(p.data as CporCaseListRow) ?? '',
      },
    ],
    [ccy],
  );

  const chips = (
    [
      ['proposed', 'Awaiting approval', proposedN, 'warning'],
      ['ended', 'Ended', counts.ended ?? 0, 'default'],
      ['blocked', 'FX blocked', fxBlockedPositive.length, 'danger'],
      ['settled', 'Settled', counts.settled ?? 0, 'success'],
      ['draft', 'Draft', counts.draft ?? 0, 'default'],
    ] as const
  ).map(([key, label, n, tone]) => ({
    key,
    label: `${label} · ${n}`,
    active: filter === key,
    onToggle: () => setParams({ status: filter === key ? null : key, case: null }),
    tone: tone as 'danger' | 'warning' | 'success' | 'default',
  }));

  const evidenceRow = (label: string, ok: boolean) => (
    <Stack direction="row" spacing={1} alignItems="center" key={label}>
      {ok ? <CheckCircleOutlineIcon fontSize="small" color="success" /> : <RadioButtonUncheckedIcon fontSize="small" color="disabled" />}
      <Typography variant="body2" color={ok ? 'text.primary' : 'text.secondary'}>
        {label} {ok ? '' : '— missing'}
      </Typography>
    </Stack>
  );

  const canApprove = !!selected?.allowed_next?.includes('approved');
  const canReject = !!selected?.allowed_next?.includes('rejected');

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="funding-case-book">
      <Alert severity="info" variant="outlined" icon={false} sx={{ '& .MuiAlert-message': { width: '100%' } }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }} justifyContent="space-between">
          <Typography variant="body2">
            <b>The Case book is the settlement half of the same lifecycle.</b> Cases here were authored
            or approved in the Promotion planner; owed, paid and blocked describe what is still open
            after the window — not a second object.
          </Typography>
          <Box sx={{ minWidth: { md: 520 } }}>
            <LifecycleRail
              stages={[...LIFECYCLE_STAGES]}
              labels={STAGE_LABEL}
              counts={counts}
              dense
              onSelect={(s) => {
                if (s === 'ended' || s === 'settled') {
                  setParams({ status: filter === s ? null : s, case: null });
                } else {
                  router.push(`/promotions?stage=${s}`);
                }
              }}
            />
          </Box>
        </Stack>
      </Alert>

      <HeadlineStrip columns={5}>
        <HeadlineFigure
          label="Open book total"
          value={fmtCompact(book?.book_total, ccy)}
          compact
          caption={`${book?.open_case_count ?? '—'} non-settled, non-cancelled cases (draft + ended). Owed = Σ line ttl_support.`}
        />
        <HeadlineFigure
          label="Paid on the open book"
          value={fmtCompact(book?.settled_amount, ccy)}
          compact
          severity="good"
          caption="Payment evidence with status paid/processed/closed — not the settled-status cohort"
        />
        <HeadlineFigure
          label="Outstanding"
          value={fmtCompact(book?.outstanding_amount, ccy)}
          compact
          caption="Owed − paid on the open book"
        />
        <HeadlineFigure
          label="FX blocked"
          value={fxBlockedPositive.length}
          unit="cases"
          compact
          severity="bad"
          caption={`${fmtCompact(book?.blocked_amount, ccy)} positive outstanding on the open book (excludes settled and negative-support cases)`}
          onClick={() => setParams({ status: 'blocked' })}
        />
        <HeadlineFigure
          label="Awaiting approval"
          value={proposedN}
          unit="cases"
          compact
          severity={proposedN ? 'warn' : 'neutral'}
          caption="Proposed — planner decision. Not ended cases waiting on claims."
          onClick={() => setParams({ status: 'proposed' })}
        />
      </HeadlineStrip>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '2fr 3fr' } }}>
        <Panel title="Outstanding by age" subtitle="Unsettled value by days since claim sale_date — not window end">
          {hasClaimAge ? (
            <Stack spacing={0.25}>
              {ageing.map((b) => (
                <PanelRow
                  key={b.bucket}
                  severity={b.bucket === '60d+' ? 'danger' : b.bucket === '31–60d' ? 'warning' : 'neutral'}
                  primary={b.bucket}
                  figure={fmtCompact(b.value, ccy)}
                />
              ))}
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              No <code>cpor_claim_evidence_line</code> rows on this database. Ageing is not estimated
              from window end.
            </Typography>
          )}
        </Panel>
        <Panel title="Blocked cases — reasons" subtitle="FX settle refuses until ROE and mode are declared" flush>
          <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
            {negativeSupport.map((c) => (
              <PanelRow
                key={`neg-${c.id}`}
                severity="warning"
                primary={`${c.case_code} · ${c.customer_name}`}
                secondary="Negative line ttl_support — a stored credit, not FX. This is why FX-blocked positive outstanding exceeds the open book."
                figure={fmtCompact(c.outstanding_amount, c.currency_code ?? ccy)}
                onClick={() => setParams({ case: String(c.id) })}
              />
            ))}
            {fxBlockedPositive.slice(0, 6).map((c) => (
              <PanelRow
                key={c.id}
                severity="danger"
                primary={`${c.case_code} · ${c.customer_name}`}
                secondary={fxBlockedReason(c)}
                figure={fmtCompact(c.outstanding_amount, c.currency_code ?? ccy)}
                onClick={() => setParams({ case: String(c.id) })}
              />
            ))}
            {!fxBlockedPositive.length && !negativeSupport.length ? (
              <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 1 }}>
                No FX-blocked cases in this page.
              </Typography>
            ) : null}
          </Stack>
        </Panel>
      </Box>

      <ScopeBar
        chips={chips}
        summary={`${rows.length} of ${data?.total ?? rows.length} cases`}
        onClear={() => setParams({ status: null, case: null })}
      />

      <ModuleDataSection
        isLoading={isLoading}
        isError={isError}
        error={error as Error | null}
        onRetry={() => void refetch()}
        isEmpty={rows.length === 0}
        empty={{
          title: 'No cases in this scope',
          description: 'Clear the status chips, or import claim / payment evidence from the domain actions.',
          primary: { label: 'Clear scope', onClick: () => setParams({ status: null }) },
        }}
      >
        {isMobile ? (
          <Stack spacing={1} data-testid="funding-record-cards">
            {rows.map((c) => (
              <Card key={c.id} variant="outlined" sx={{ boxShadow: 'none' }}>
                <CardActionArea onClick={() => setParams({ case: String(c.id) })}>
                  <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {c.customer_name} · {c.case_code}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                          {c.promotion_type}
                        </Typography>
                      </Box>
                      <StatusChip label={STAGE_LABEL[c.status as PlanStage] ?? c.status} tone={stageTone(c.status)} />
                    </Stack>
                    <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
                      <Typography variant="caption">
                        Owed <b>{fmtCompact(c.owed_amount, c.currency_code)}</b>
                      </Typography>
                      <Typography variant="caption">
                        Outstanding <b>{fmtCompact(c.outstanding_amount, c.currency_code)}</b>
                      </Typography>
                    </Stack>
                    {fxBlockedReason(c) ? (
                      <Typography variant="caption" color="error.main" sx={{ display: 'block', mt: 0.5 }}>
                        {fxBlockedReason(c)}
                      </Typography>
                    ) : null}
                  </CardContent>
                </CardActionArea>
              </Card>
            ))}
          </Stack>
        ) : (
          <EnterpriseDataGrid<CporCaseListRow>
            rowData={rows}
            columnDefs={columnDefs}
            height={420}
            gridOptions={{
              onRowClicked: (e: RowClickedEvent<CporCaseListRow>) => e.data && setParams({ case: String(e.data.id) }),
              getRowId: (p) => String(p.data.id),
            }}
          />
        )}
      </ModuleDataSection>

      {toastAction ? (
        <Alert severity="success" onClose={() => setToastAction(null)}>
          {toastAction}
        </Alert>
      ) : null}

      <EntityContextPanel
        open={!!selected}
        onClose={() => setParams({ case: null })}
        kicker={selected ? STAGE_LABEL[selected.status as PlanStage] ?? selected.status : undefined}
        title={selected ? `${selected.case_code} · ${selected.customer_name}` : ''}
        subtitle={selected ? `${selected.promotion_type} · ${selected.window_start} → ${selected.window_end}` : undefined}
        width={480}
        figures={
          selected ? (
            <HeadlineStrip columns={3}>
              <HeadlineFigure
                label="Owed"
                value={fmtCompact(selected.owed_amount, selected.currency_code)}
                dense
                caption={`${fmtInt(selected.estimate_qty_sum)} est. units`}
              />
              <HeadlineFigure
                label="Outstanding"
                value={fmtCompact(selected.outstanding_amount, selected.currency_code)}
                dense
                severity={(selected.outstanding_amount ?? 0) > 0 ? 'warn' : 'good'}
              />
              <HeadlineFigure
                label="Age"
                value={ageDays(selected) ?? '—'}
                unit={ageDays(selected) != null ? 'days' : undefined}
                dense
                caption={selected.last_claim_sale_date ? 'Since last claim sale_date' : 'No claim sale_date'}
              />
            </HeadlineStrip>
          ) : null
        }
        related={
          selected
            ? [
                {
                  label: 'Open in Promotion planner',
                  href: `/promotions?plan=${selected.id}`,
                  hint: 'Same cpor_case — planning workspace',
                },
                {
                  label: 'Settlement workspace (claims, settle, FX)',
                  href: `/commercial-planner/cpor-cases/${selected.id}`,
                  hint: 'Claim upload, settle, events, exports',
                },
                {
                  label: 'Was the promotion live at the planned price?',
                  href: '/listing-capture?tab=intelligence',
                  hint: 'Market & Listings › Activation',
                },
                { label: 'Stock cover', href: '/stock?lens=cover', hint: 'Stock & Sell-through › Cover' },
                {
                  label: 'Customer terms',
                  href: '/admin/customer-commercial-terms',
                  hint: 'Terms & assumptions',
                },
              ]
            : []
        }
        footer={
          selected && (canApprove || canReject) ? (
            <>
              {canReject ? (
                <Button
                  variant="outlined"
                  color="error"
                  size="small"
                  onClick={() =>
                    transition.mutate({
                      id: selected.id,
                      action: 'reject',
                      comment: 'Returned from case book — evidence or terms insufficient',
                    })
                  }
                  data-testid="case-return"
                >
                  Return with reason
                </Button>
              ) : null}
              {canApprove ? (
                <Button
                  variant="contained"
                  size="small"
                  onClick={() => transition.mutate({ id: selected.id, action: 'approve' })}
                  disabled={(selected.settle_readiness?.claim_evidence_count ?? 0) < 1}
                  data-testid="case-approve"
                >
                  Approve
                </Button>
              ) : null}
            </>
          ) : selected ? (
            <Button size="small" variant="outlined" onClick={() => setParams({ case: null })}>
              Close
            </Button>
          ) : null
        }
      >
        {selected ? (
          <Stack spacing={2}>
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Lifecycle
              </Typography>
              <Box sx={{ mt: 1 }}>
                <LifecycleRail
                  stages={[...LIFECYCLE_STAGES]}
                  labels={STAGE_LABEL}
                  current={
                    LIFECYCLE_STAGES.includes(selected.status as (typeof LIFECYCLE_STAGES)[number])
                      ? (selected.status as (typeof LIFECYCLE_STAGES)[number])
                      : undefined
                  }
                  dense
                />
              </Box>
            </Box>
            {fxBlockedReason(selected) ? (
              <Alert severity="error" variant="outlined">
                {fxBlockedReason(selected)}
              </Alert>
            ) : null}
            {(Number(selected.outstanding_amount) || 0) < -0.005 ? (
              <Alert severity="warning" variant="outlined">
                Outstanding is negative because stored line <code>ttl_support</code> sums below zero.
                That is a stored fact, not FX rounding.
              </Alert>
            ) : null}
            <Box>
              <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Evidence
              </Typography>
              <Stack spacing={0.75} sx={{ mt: 1 }}>
                {evidenceRow('Claim file matched', (selected.settle_readiness?.claim_evidence_count ?? 0) > 0)}
                {evidenceRow('Payment evidence', (selected.payment_evidence_count ?? 0) > 0)}
                {evidenceRow(
                  'Sell-through corroborates claimed units',
                  false,
                )}
              </Stack>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                Sell-through corroboration is not joined onto the case list — open the settlement
                workspace. Approve in this drawer is only offered when the case may actually transition
                to approved.
              </Typography>
            </Box>
            <KeyValueList
              items={[
                { k: 'Type', v: selected.promotion_type },
                { k: 'Est. units', v: fmtInt(selected.estimate_qty_sum) },
                { k: 'Owed (Σ ttl_support)', v: fmtCompact(selected.owed_amount, selected.currency_code) },
                { k: 'Paid', v: fmtCompact(selected.paid_amount_sum, selected.currency_code) },
                { k: 'Window', v: `${selected.window_start ?? '—'} → ${selected.window_end ?? '—'}` },
              ]}
            />
          </Stack>
        ) : null}
      </EntityContextPanel>
    </Stack>
  );
}
