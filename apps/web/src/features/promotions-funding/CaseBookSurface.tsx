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
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import { PaymentEvidenceOverlayPanel } from '@/features/promotions-funding/PaymentEvidenceOverlay';
import { CaseScopeFilters } from '@/features/promotions-funding/CaseScopeFilters';
import {
  caseScopeClearPatch,
  caseScopeFromSearch,
  caseScopeIsActive,
  caseScopeToQuery,
} from '@/features/promotions-funding/caseScope';
import { evidenceBasisLabel, isEvidenceBasis, type EvidenceBasis } from '@/features/promotions-funding/evidenceBasis';
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
import { CategoryBars } from '@/features/workbench-ui/charts';
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
  by_evidence_basis?: Record<
    string,
    { case_count?: number; owed?: number; paid?: number; outstanding?: number }
  >;
  evidence_basis_note?: string;
};

type BookFilter = 'proposed' | 'ended' | 'settled' | 'blocked' | 'draft' | null;

type FxBackfillSuggestion = {
  case_id: number;
  case_code: string;
  status: string;
  suggested_rate: number | null;
  suggested_rate_date: string | null;
  source: string;
  is_fallback: boolean;
  will_book_on_confirm: boolean;
};

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

function windowEndAgeDays(row: CporCaseListRow): number | null {
  if (!row.window_end) return null;
  const end = Date.parse(row.window_end);
  if (!Number.isFinite(end)) return null;
  return Math.max(0, Math.floor((Date.now() - end) / 86_400_000));
}

function bucketOutstanding(
  items: CporCaseListRow[],
  daysOf: (row: CporCaseListRow) => number | null,
): Array<{ bucket: string; value: number }> {
  const buckets = [
    { bucket: '0–14d', value: 0 },
    { bucket: '15–30d', value: 0 },
    { bucket: '31–60d', value: 0 },
    { bucket: '60d+', value: 0 },
  ];
  for (const r of items) {
    if (r.status === 'settled') continue;
    const d = daysOf(r);
    if (d == null) continue;
    const v = Number(r.outstanding_amount) || 0;
    if (d <= 14) buckets[0].value += v;
    else if (d <= 30) buckets[1].value += v;
    else if (d <= 60) buckets[2].value += v;
    else buckets[3].value += v;
  }
  return buckets;
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
  const evidenceParam = search.get('evidence');
  const evidenceFilter: EvidenceBasis | null = isEvidenceBasis(evidenceParam) ? evidenceParam : null;
  const testDataOnly = search.get('test_data') === 'only';
  const scope = caseScopeFromSearch(search);
  const hasEntityScope = caseScopeIsActive(scope);
  const hasGridScope = hasEntityScope || testDataOnly;
  const [toastAction, setToastAction] = useState<string | null>(null);
  const [backfillItems, setBackfillItems] = useState<FxBackfillSuggestion[] | null>(null);
  const [declareModeOpen, setDeclareModeOpen] = useState(false);

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

  const { data: scopedPage, isLoading: scopedLoading } = useQuery({
    queryKey: ['cpor', 'cases', 'book', 'scoped', scope, testDataOnly],
    enabled: hasGridScope,
    queryFn: ({ signal }) => {
      const sp = new URLSearchParams({ page: '1', page_size: '500' });
      if (testDataOnly) sp.set('test_data', 'only');
      caseScopeToQuery(scope).forEach((v, k) => sp.set(k, v));
      return apiGet<CporCasesPage>(`/api/v1/cpor/cases?${sp.toString()}`, { signal });
    },
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
  const rateNoModeRows = allItems.filter(
    (r) => Boolean(r.settle_readiness?.fx_declared) && r.settle_readiness?.fx_mode_declared === false,
  );
  const missingRateRows = allItems.filter((r) => r.settle_readiness?.fx_declared === false);

  const scopedItems = hasGridScope ? (scopedPage?.items ?? []) : allItems;
  const rows = useMemo(() => {
    let next = scopedItems;
    if (filter === 'blocked') {
      next = next.filter(
        (r) => isFxBlocked(r) && isOpenBookStatus(r.status) && (Number(r.outstanding_amount) || 0) > 0,
      );
    } else if (filter) {
      next = next.filter((r) => r.status === filter);
    }
    if (evidenceFilter) next = next.filter((r) => r.evidence_basis === evidenceFilter);
    return next;
  }, [scopedItems, filter, evidenceFilter]);

  const selectedId = selectedParam && /^\d+$/.test(selectedParam) ? Number(selectedParam) : null;
  const { data: selectedDetail } = useQuery({
    queryKey: ['cpor', 'case', selectedId, 'book-drawer'],
    enabled: selectedId != null,
    queryFn: ({ signal }) => apiGet<CporCaseListRow>(`/api/v1/cpor/cases/${selectedId}`, { signal }),
  });
  const selected =
    allItems.find((r) => r.id === selectedId) ??
    rows.find((r) => r.id === selectedId) ??
    (selectedDetail && selectedId != null && selectedDetail.id === selectedId ? selectedDetail : null);

  const ageingClaim = useMemo(() => bucketOutstanding(allItems, ageDays), [allItems]);
  const ageingWindow = useMemo(() => bucketOutstanding(allItems, windowEndAgeDays), [allItems]);
  const hasClaimAge = allItems.some((r) => r.last_claim_sale_date);
  const ageing = hasClaimAge ? ageingClaim : ageingWindow;
  const evidenceCounts = data?.evidence_basis_counts ?? {
    claim_evidenced: allItems.filter((r) => r.evidence_basis === 'claim_evidenced').length,
    source_attested: allItems.filter((r) => r.evidence_basis === 'source_attested').length,
    none: allItems.filter((r) => (r.evidence_basis ?? 'none') === 'none').length,
  };

  const loadFxSuggestions = useMutation({
    mutationFn: () =>
      apiGet<{
        items: FxBackfillSuggestion[];
        count: number;
        missing_rate_count?: number;
        rate_no_mode_count?: number;
      }>('/api/v1/cpor/fx/backfill-suggestions'),
    onSuccess: (payload) => setBackfillItems(payload.items),
  });

  const declareBookedMode = useMutation({
    mutationFn: () =>
      apiPost<{ declared: number; mode: string }>('/api/v1/cpor/fx/declare-mode', {
        confirm: true,
        mode: 'booked',
      }),
    onSuccess: async (payload) => {
      setDeclareModeOpen(false);
      setToastAction(`Declared booked FX mode on ${payload.declared} case(s). Rates were not changed.`);
      await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', 'book'] });
    },
  });

  const confirmFxBackfill = useMutation({
    mutationFn: () =>
      apiPost<{ confirmed: number; booked: number }>('/api/v1/cpor/fx/backfill-confirm', {
        items: (backfillItems ?? [])
          .filter((row) => row.suggested_rate != null)
          .map((row) => ({ case_id: row.case_id, rate: row.suggested_rate })),
      }),
    onSuccess: async (payload) => {
      setToastAction(
        `Confirmed ${payload.confirmed} rate(s); booked ${payload.booked} already-approved case(s)`,
      );
      setBackfillItems(null);
      await qc.invalidateQueries({ queryKey: ['cpor', 'cases'] });
      await qc.invalidateQueries({ queryKey: ['cpor', 'settlement', 'book'] });
    },
  });

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
        headerName: hasClaimAge ? 'Age (claim sale)' : 'Age (window end)',
        type: 'rightAligned',
        width: 110,
        valueGetter: (p) =>
          hasClaimAge
            ? ageDays(p.data as CporCaseListRow)
            : windowEndAgeDays(p.data as CporCaseListRow),
        valueFormatter: (p) => (p.value == null ? '—' : `${p.value}d`),
      },
      {
        colId: 'evidence_basis',
        headerName: 'Evidence',
        width: 140,
        valueGetter: (p) => evidenceBasisLabel((p.data as CporCaseListRow | undefined)?.evidence_basis),
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
    [ccy, hasClaimAge],
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

  const evidenceChips = (
    [
      ['claim_evidenced', 'Claim evidenced', evidenceCounts.claim_evidenced ?? 0],
      ['source_attested', 'Source attested', evidenceCounts.source_attested ?? 0],
      ['none', 'No evidence', evidenceCounts.none ?? 0],
    ] as const
  ).map(([key, label, n]) => ({
    key,
    label: `${label} · ${n}`,
    active: evidenceFilter === key,
    onToggle: () => setParams({ evidence: evidenceFilter === key ? null : key, case: null }),
    tone: key === 'none' ? ('default' as const) : key === 'source_attested' ? ('warning' as const) : ('success' as const),
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
            after the window — not a second object. Pending payment/CN disputes (Latest Comment) and
            unmatched file Case IDs are listed below. Claim-sale ageing is used when claim lines exist;
            otherwise outstanding is aged from window end (a different clock — labeled).
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
          caption={`${book?.open_case_count ?? '—'} non-settled, non-cancelled cases (draft + ended). Owed = Σ line ttl_support. Mix: claim ${book?.by_evidence_basis?.claim_evidenced?.case_count ?? 0} · attested ${book?.by_evidence_basis?.source_attested?.case_count ?? 0} · none ${book?.by_evidence_basis?.none?.case_count ?? 0}.`}
        />
        <HeadlineFigure
          label="Paid on the open book"
          value={fmtCompact(book?.settled_amount, ccy)}
          compact
          severity="good"
          caption="Same-currency payment evidence only (paid/processed/closed). USD pending-report rows do not pay this ZAR book — R0 is expected until FX is declared."
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

      <PaymentEvidenceOverlayPanel />

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '2fr 3fr' } }}>
        <Panel
          title="Outstanding by age"
          subtitle={
            hasClaimAge
              ? 'Unsettled value by days since claim sale_date — not window end'
              : 'Unsettled value by days since window end. Claim-sale ageing stays available when claim lines exist — not estimated as sale_date.'
          }
        >
          <Box data-testid="case-book-ageing">
            <CategoryBars
              data={ageing}
              x="bucket"
              y="value"
              height={170}
              format={(v) => fmtCompact(v, ccy)}
              colorBy={(r) =>
                String(r.bucket) === '60d+'
                  ? theme.palette.error.main
                  : String(r.bucket) === '31–60d'
                    ? theme.palette.warning.main
                    : theme.palette.primary.main
              }
            />
          </Box>
        </Panel>
        <Panel title="Blocked cases — reasons" subtitle="FX settle refuses until ROE and mode are declared" flush>
          <Stack spacing={0.25} sx={{ px: 1, pb: 1 }}>
            <Stack direction="row" spacing={1} sx={{ px: 1, pt: 1, pb: 0.5 }} flexWrap="wrap" useFlexGap>
              {rateNoModeRows.length > 0 ? (
                <Button
                  size="small"
                  variant="contained"
                  onClick={() => setDeclareModeOpen(true)}
                  data-testid="fx-declare-mode"
                >
                  Declare booked FX mode · {rateNoModeRows.length}
                </Button>
              ) : null}
              {missingRateRows.length > 0 ? (
                <Button
                  size="small"
                  variant="outlined"
                  disabled={loadFxSuggestions.isPending}
                  onClick={() => loadFxSuggestions.mutate()}
                  data-testid="fx-backfill-suggest"
                >
                  {loadFxSuggestions.isPending
                    ? 'Loading suggestions…'
                    : `Suggest rates for ${missingRateRows.length} case${missingRateRows.length === 1 ? '' : 's'} missing a rate`}
                </Button>
              ) : null}
              {backfillItems && backfillItems.length > 0 ? (
                <Button
                  size="small"
                  variant="contained"
                  disabled={confirmFxBackfill.isPending}
                  onClick={() => confirmFxBackfill.mutate()}
                  data-testid="fx-backfill-confirm"
                >
                  Confirm {backfillItems.filter((r) => r.suggested_rate != null).length} suggestion
                  {backfillItems.filter((r) => r.suggested_rate != null).length === 1 ? '' : 's'}
                </Button>
              ) : null}
            </Stack>
            {missingRateRows.length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 0.5 }}>
                No cases are missing a rate. Rate suggestion is not offered. {rateNoModeRows.length} case
                {rateNoModeRows.length === 1 ? '' : 's'} have a rate and need booked or floating mode.
              </Typography>
            ) : null}
            {backfillItems && backfillItems.length === 0 && missingRateRows.length > 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ px: 1.5, py: 0.5 }}>
                No missing-rate cases received a window-start suggestion.
              </Typography>
            ) : null}
            {backfillItems
              ?.filter((row) => row.suggested_rate != null)
              .slice(0, 8)
              .map((row) => (
                <PanelRow
                  key={`sug-${row.case_id}`}
                  severity="warning"
                  primary={`${row.case_code} · ${row.suggested_rate?.toFixed(2)} ZAR/USD`}
                  secondary={`${row.source}${row.is_fallback ? ' (fallback)' : ''} · ${row.suggested_rate_date ?? 'no date'} · ${
                    row.will_book_on_confirm ? 'confirm books (already approved)' : 'confirm proposes only'
                  }`}
                />
              ))}
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
        chips={[
          ...chips,
          ...evidenceChips,
          {
            key: 'test_data',
            label: `Test data · ${data?.test_data_count ?? 0}`,
            active: testDataOnly,
            onToggle: () => setParams({ test_data: testDataOnly ? null : 'only', case: null }),
            tone: 'warning' as const,
          },
        ]}
        summary={`${rows.length} of ${hasGridScope ? (scopedPage?.total ?? rows.length) : (data?.total ?? rows.length)} cases${hasGridScope ? ' in this find' : ''}`}
        onClear={() =>
          setParams({ status: null, evidence: null, case: null, test_data: null, ...caseScopeClearPatch() })
        }
        clearAvailable={hasGridScope}
        filters={<CaseScopeFilters scope={scope} onPatch={setParams} />}
      />

      <ModuleDataSection
        isLoading={isLoading || (hasGridScope && scopedLoading)}
        isError={isError}
        error={error as Error | null}
        onRetry={() => void refetch()}
        isEmpty={rows.length === 0}
        empty={{
          title: 'No cases in this scope',
          description: 'Clear the status chips or find filters, or import claim / payment evidence from the domain actions.',
          primary: {
            label: 'Clear scope',
            onClick: () => setParams({ status: null, evidence: null, test_data: null, ...caseScopeClearPatch() }),
          },
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
      <Dialog
        open={declareModeOpen}
        onClose={() => !declareBookedMode.isPending && setDeclareModeOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Declare booked FX mode</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            This sets <code>fx_mode = booked</code> on {rateNoModeRows.length} case
            {rateNoModeRows.length === 1 ? '' : 's'} that already have a positive rate and no valid
            mode. It does not change <code>roe_snapshot</code>. It does not run unless you confirm.
            Booked is the settled default; floating remains available on a single case.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeclareModeOpen(false)} disabled={declareBookedMode.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => declareBookedMode.mutate()}
            disabled={declareBookedMode.isPending || rateNoModeRows.length === 0}
            data-testid="fx-declare-mode-confirm"
          >
            {declareBookedMode.isPending ? 'Declaring…' : `Confirm booked on ${rateNoModeRows.length}`}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
