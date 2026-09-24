'use client';

import type { ColDef } from 'ag-grid-community';
import { Alert, Box, Button, Checkbox, FormControlLabel, Stack, Switch, Typography } from '@mui/material';
import Link from 'next/link';
import { useMemo, useRef, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { DualMoney } from '@/features/cpor/DualMoney';
import { buildSettleReadinessChips, formatLocalMoney, type ReadinessChip } from '@/features/cpor/fxDisplay';
import { useLineIdentifierPreference } from '@/features/tenant/useLineIdentifierPreference';
import { ScopeBar, StatusChip } from '@/features/workbench-ui/controls';
import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { EntityContextPanel, KeyValueList } from '@/features/workbench-ui/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { LifecycleRail } from '@/features/workbench-ui/LifecycleRail';
import { Panel, PanelRow } from '@/features/workbench-ui/Panel';

import {
  CORROBORATION_CHIP,
  SETTLE_STAGE_LABEL,
  SETTLE_STAGES,
  corroborationTone,
  fmtInt,
  type SettlementDeskLine,
  type SettlementDeskView,
} from './settlementDeskModel';

type Props = {
  view: SettlementDeskView;
  testId?: string;
  embedded?: boolean;
  uploading?: boolean;
  settling?: boolean;
  formatMoney?: (amount: number | null, currency: string) => string;
  onUploadCustomerReport?: (file: File) => void;
  onSettle?: () => void;
  onRaiseHqCredit?: () => void;
  /** BACKLOG-138 — open the supersede preview→confirm dialog. Hidden when absent or already superseded. */
  onSupersede?: () => void;
  /** BACKLOG-138 — clear the supersession pointer. Only rendered when the case is superseded. */
  onRestoreSupersession?: () => void;
  restoringSupersession?: boolean;
  /** N-0044 — post-live lifecycle actions (end / cancel). The caller confirms before posting. */
  onLifecycleAction?: (action: 'end' | 'cancel') => void;
  transitioning?: boolean;
  /** Pre-approval actions (propose, approve, reject, resend, activate) live in the planner. */
  plannerHref?: string;
  includeOutOfWindow?: boolean;
  onIncludeOutOfWindowChange?: (include: boolean) => void;
  onRerollup?: () => void;
  rerolling?: boolean;
  onIntelligenceExcludeChange?: (exclude: boolean) => void;
  excludingIntelligence?: boolean;
};

const READINESS_TONE: Record<ReadinessChip['tone'], 'success' | 'warning' | 'danger'> = {
  pass: 'success',
  open: 'warning',
  fail: 'danger',
};

/** Targets reached from the planner, not the desk — any of these in allowed_next shows "Open in planner". */
const PLANNER_TARGETS = ['proposed', 'approved', 'rejected', 'active'];

/**
 * Shared Ken next-action settlement desk (composition A, with three B ports).
 * Primitives: DomainHeader, LifecycleRail, HeadlineStrip, ScopeBar, Panel/PanelRow,
 * EnterpriseDataGrid, EntityContextPanel — all workbench-ui. No new primitive:
 * a second LifecycleRail was rejected (one rail already owns the job); a split-pane
 * tape layout was rejected (Warren: do not build B's two-column tapes).
 */
export function SettlementDesk({
  view,
  testId = 'settlement-desk',
  embedded = false,
  uploading = false,
  settling = false,
  formatMoney = formatLocalMoney,
  onUploadCustomerReport,
  onSettle,
  onRaiseHqCredit,
  onSupersede,
  onRestoreSupersession,
  restoringSupersession = false,
  onLifecycleAction,
  transitioning = false,
  plannerHref,
  includeOutOfWindow = false,
  onIncludeOutOfWindowChange,
  onRerollup,
  rerolling = false,
  onIntelligenceExcludeChange,
  excludingIntelligence = false,
}: Props) {
  const [mismatchOnly, setMismatchOnly] = useState(false);
  const [disti, setDisti] = useState<string | null>(null);
  const [selected, setSelected] = useState<SettlementDeskLine | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const lineId = useLineIdentifierPreference();

  const distributors = useMemo(
    () => Array.from(new Set(view.lines.map((l) => l.distributor).filter(Boolean))),
    [view.lines],
  );
  const rows = useMemo(
    () =>
      view.lines.filter(
        (l) => (!disti || l.distributor === disti) && (!mismatchOnly || l.corroboration !== 'match'),
      ),
    [disti, mismatchOnly, view.lines],
  );

  const money = (amount: number | null) => formatMoney(amount, view.currency);
  const moneyDual = (amount: number | null, testId: string) => (
    <DualMoney
      amount={amount}
      currencyCode={view.currency}
      roeSnapshot={view.roeSnapshot}
      missingRoe={!view.fxDeclared}
      testId={testId}
    />
  );
  const readinessChips = view.settleReadiness ? buildSettleReadinessChips(view.settleReadiness) : [];
  const unresolvedCount = view.unresolvedProducts?.length ?? 0;
  const cst = view.cstReconciliation;
  const cstDivergence = cst?.available ? (cst.divergence_count ?? 0) : 0;
  const approvedCaption = view.fxDeclared
    ? [
        `Booked ${view.roeSnapshot != null ? view.roeSnapshot.toFixed(2) : '—'}${view.fxMode ? ` · ${view.fxMode}` : ''}`,
        view.fxBookedBy ? `by ${view.fxBookedBy}` : null,
        view.fxBookedAt ? view.fxBookedAt.slice(0, 10) : null,
      ]
        .filter(Boolean)
        .join(' · ')
    : view.fxProposedRate != null
      ? `Proposed ${view.fxProposedRate.toFixed(2)}${view.fxProposedSource ? ` · ${view.fxProposedSource}` : ''} · not booked`
      : 'No rate booked or proposed';
  const lifecycleActions = (['end', 'cancel'] as const).filter((a) =>
    view.allowedNext.includes(a === 'end' ? 'ended' : 'cancelled'),
  );
  const showPlannerLink = Boolean(plannerHref) && view.allowedNext.some((t) => PLANNER_TARGETS.includes(t));
  const paidCaption = 'Not in schema today';
  const customerEmpty = view.claimRowCount === 0;
  const raiseEnabled = view.status === 'settled' && view.hqCreditLineCount > 0 && Boolean(onRaiseHqCredit);
  const settleEnabled =
    view.canSettle && view.fxSettleAllowed && view.allowedNext.includes('settled') && Boolean(onSettle);

  let primaryCta: { label: string; onClick?: () => void; disabled: boolean; reason?: string };
  if (customerEmpty) {
    primaryCta = {
      label: 'Upload customer report',
      onClick: onUploadCustomerReport ? () => fileRef.current?.click() : undefined,
      disabled: !onUploadCustomerReport || uploading,
    };
  } else if (settleEnabled) {
    primaryCta = {
      label: 'Record both-agree (SETTLED)',
      onClick: onSettle,
      disabled: settling,
    };
  } else if (view.status === 'settled') {
    primaryCta = {
      label: `Raise HQ credit · ${money(view.hqCreditAmount)}`,
      onClick: onRaiseHqCredit,
      disabled: !raiseEnabled,
      reason: raiseEnabled ? undefined : 'No matched lines can lock — HQ credit pack is empty',
    };
  } else {
    primaryCta = {
      label: 'Upload customer report',
      onClick: onUploadCustomerReport ? () => fileRef.current?.click() : undefined,
      disabled: !onUploadCustomerReport || uploading,
    };
  }

  const columnDefs = useMemo<ColDef<SettlementDeskLine>[]>(
    () => [
      {
        colId: 'line_identifier',
        headerName: lineId.header,
        width: 140,
        pinned: 'left',
        valueGetter: (p) => lineId.value(p.data?.sku, p.data?.salesModel),
      },
      { field: 'product', headerName: 'Product', minWidth: 200, flex: 1.4 },
      { field: 'distributor', headerName: 'Distributor', minWidth: 160, flex: 1 },
      {
        field: 'estimateQty',
        headerName: 'Estimate',
        type: 'rightAligned',
        width: 100,
        valueFormatter: (p) => fmtInt(p.value),
      },
      {
        field: 'cipQty',
        headerName: 'CIP qty',
        type: 'rightAligned',
        width: 100,
        valueFormatter: (p) => fmtInt(p.value),
      },
      {
        field: 'customerQty',
        headerName: 'Customer qty',
        type: 'rightAligned',
        width: 120,
        valueFormatter: (p) => (p.value == null ? '—' : fmtInt(p.value)),
      },
      {
        field: 'corroboration',
        headerName: 'Corroboration',
        minWidth: 168,
        width: 188,
        flex: 0.7,
        wrapText: true,
        autoHeight: true,
        cellRenderer: (p: { data?: SettlementDeskLine }) =>
          p.data ? (
            <StatusChip
              label={CORROBORATION_CHIP[p.data.corroboration]}
              tone={corroborationTone(p.data.corroboration)}
            />
          ) : null,
      },
      {
        field: 'corroborationReason',
        headerName: 'Reason',
        minWidth: 150,
        flex: 0.8,
      },
      {
        field: 'includeInCredit',
        headerName: 'In credit',
        width: 100,
        valueFormatter: (p) => (p.value ? 'Yes' : 'No'),
      },
    ],
    [lineId],
  );


  return (
    <Stack spacing={2} sx={{ mt: embedded ? 0 : 2 }} data-testid={testId}>
      <input
        ref={fileRef}
        type="file"
        hidden
        accept=".csv,.xlsx,.xls"
        data-testid="settlement-desk-claim-file"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (file && onUploadCustomerReport) onUploadCustomerReport(file);
        }}
      />
      <DomainHeader
        crumbs={
          embedded
            ? undefined
            : [
                { label: 'Promotions & Funding', href: '/commercial-planner/cpor-cases' },
                { label: 'Settle a case' },
              ]
        }
        title={`${view.caseCode} · ${view.customerName}`}
        description={`${view.programme} · ${view.windowLabel} · ${view.distributorName}. Ken’s desk: the next commercial action is visible without opening tabs.`}
        meta={`Opened ${view.openedOn ?? '—'} · Ended ${view.endedOn ?? '—'} · ${view.currency}${
          view.fxSettleAllowed && view.fxBasisLine ? ` · ${view.fxBasisLine}` : ''
        }`}
        actions={
          <>
            {showPlannerLink && plannerHref ? (
              <Button
                variant="text"
                size="small"
                component={Link}
                href={plannerHref}
                data-testid="settlement-desk-open-planner"
              >
                Open in planner
              </Button>
            ) : null}
            {onLifecycleAction
              ? lifecycleActions.map((a) => (
                  <Button
                    key={a}
                    variant="outlined"
                    size="small"
                    color={a === 'cancel' ? 'warning' : 'primary'}
                    disabled={transitioning}
                    onClick={() => onLifecycleAction(a)}
                    data-testid={`settlement-desk-action-${a}`}
                  >
                    {a === 'end' ? 'End case…' : 'Cancel case…'}
                  </Button>
                ))
              : null}
            {onSupersede && view.supersededByCaseId == null && view.status !== 'settled' ? (
              <Button
                variant="outlined"
                size="small"
                color="warning"
                onClick={onSupersede}
                data-testid="settlement-desk-supersede"
              >
                Supersede…
              </Button>
            ) : null}
            {primaryCta.label !== 'Upload customer report' ? (
              <Button
                variant="outlined"
                size="small"
                disabled={!onUploadCustomerReport || uploading}
                onClick={() => fileRef.current?.click()}
                data-testid="settlement-desk-upload"
              >
                {uploading ? 'Uploading…' : 'Upload customer report'}
              </Button>
            ) : null}
            <Button
              variant="contained"
              size="small"
              disabled={primaryCta.disabled}
              onClick={primaryCta.onClick}
              data-testid="settlement-desk-primary"
            >
              {primaryCta.label}
            </Button>
          </>
        }
      />

      <LifecycleRail stages={[...SETTLE_STAGES]} labels={SETTLE_STAGE_LABEL} current={view.stage} />

      {view.supersededByCaseId != null ? (
        <Alert
          severity="info"
          data-testid="settlement-desk-superseded"
          action={
            onRestoreSupersession ? (
              <Button
                size="small"
                color="inherit"
                disabled={restoringSupersession}
                onClick={onRestoreSupersession}
                data-testid="settlement-desk-supersede-restore"
              >
                {restoringSupersession ? 'Restoring…' : 'Restore'}
              </Button>
            ) : undefined
          }
        >
          Superseded by{' '}
          <Link href={`/commercial-planner/cpor-cases/${view.supersededByCaseId}`}>
            case #{view.supersededByCaseId}
          </Link>
          . Status unchanged ({view.status}); excluded from the settlement book, owed/paid recon, norms and
          comparables. Lines, claims and events are kept.
        </Alert>
      ) : null}

      {view.needsReapproval ? (
        <Alert severity="warning" data-testid="settlement-desk-needs-reapproval">
          Needs reapproval (over budget). The money ceiling is exceeded — reapprove with over-budget
          confirmation in the planner, or reduce support.
        </Alert>
      ) : null}

      {!view.fxSettleAllowed ? (
        <Alert severity="warning" data-testid="settlement-desk-fx-blocked">
          {view.fxBasisLine ||
            'FX basis is not ready — settlement is blocked until rate of exchange is declared and FX mode is valid.'}
        </Alert>
      ) : null}

      {view.settledWithoutClaims ? (
        <Alert severity="warning" data-testid="settlement-desk-settled-without-claims">
          This case is SETTLED with no customer report on file. That is a real signal, not a label
          bug — the customer tape stays empty until a claim file is imported.
        </Alert>
      ) : null}

      {customerEmpty && !view.settledWithoutClaims ? (
        <Alert severity="info" data-testid="settlement-desk-empty-customer-tape">
          Customer qty has no rows yet. CIP qty is still shown. The customer column stays empty
          until a claim-evidence file is imported — CIP is not substituted.
        </Alert>
      ) : null}

      <HeadlineStrip columns={6}>
        <HeadlineFigure
          label="Approved support"
          value={
            <DualMoney
              amount={view.approvedAmount ?? null}
              currencyCode={view.currency}
              roeSnapshot={view.roeSnapshot}
              missingRoe={!view.fxDeclared}
              usdAmount={view.fxDeclared ? (view.approvedUsd ?? null) : null}
              // DualMoney prints usdNote in place of the USD when missingRoe — only label a booked sum.
              usdNote={view.fxDeclared ? 'Σ line USD at the booked rate' : undefined}
              testId="desk-approved"
            />
          }
          compact
          caption={approvedCaption}
        />
        <HeadlineFigure
          label="CIP reconciled"
          value={moneyDual(view.cipAmount, 'desk-cip')}
          compact
          caption="System-owned"
        />
        <HeadlineFigure
          label="Customer report"
          value={customerEmpty ? '—' : moneyDual(view.customerAmount, 'desk-customer')}
          compact
          caption="Customer-owned"
        />
        <HeadlineFigure
          label="Agreed (SETTLED)"
          value={moneyDual(view.agreedAmount, 'desk-agreed')}
          compact
          severity={view.status === 'settled' ? 'good' : 'neutral'}
          caption={
            view.agreedActor
              ? `Both parties agree · ${view.agreedActor}`
              : view.status === 'settled'
                ? 'Both parties agree · actor not stamped on this case'
                : 'Both parties agree'
          }
        />
        <HeadlineFigure label="Paid" value="R0" compact caption={paidCaption} />
        <HeadlineFigure
          label="In HQ credit pack"
          value={moneyDual(view.hqCreditAmount, 'desk-hq-credit')}
          compact
          caption={`${view.hqCreditLineCount} lines`}
        />
      </HeadlineStrip>

      <Box data-testid="settlement-desk-overlap">
      <Panel
        title="Overlap — what SETTLED would lock"
        subtitle={`${view.matchedCount} matched · ${view.openCount} still open. Do not mix this with paid.`}
      >
        <ScopeBar
          chips={[
            {
              key: 'matched',
              label: `Matched · ${view.matchedCount}`,
              active: !mismatchOnly,
              onToggle: () => setMismatchOnly(false),
              tone: 'success',
            },
            {
              key: 'open',
              label: `Open · ${view.openCount}`,
              active: mismatchOnly,
              onToggle: () => setMismatchOnly(true),
              tone: 'warning',
            },
          ]}
          summary="Matched lines can lock. Open lines stay on the grid until Ken or a PM agrees a qty."
        />
      </Panel>
      </Box>

      <ScopeBar
        chips={[
          {
            key: 'mismatch',
            label: 'Mismatches only',
            active: mismatchOnly,
            onToggle: () => setMismatchOnly((v) => !v),
            tone: 'warning',
          },
          ...distributors.map((d) => ({
            key: d,
            label: d,
            active: disti === d,
            onToggle: () => setDisti(disti === d ? null : d),
          })),
        ]}
        summary={`${rows.length} of ${view.lines.length} lines · SETTLED means both agree; PAID is after money moves`}
        onClear={() => {
          setMismatchOnly(false);
          setDisti(null);
        }}
      />

      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1fr) minmax(240px, 280px)' },
          alignItems: 'start',
          minWidth: 0,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
        <EnterpriseDataGrid<SettlementDeskLine>
          rowData={rows}
          columnDefs={columnDefs}
          height={embedded ? 280 : 360}
          gridOptions={{
            onRowClicked: (e) => e.data && setSelected(e.data),
            getRowId: (p) => p.data.id,
          }}
        />
        </Box>
        <Panel
          title="Next action"
          subtitle={`One CTA for the current stage — “${primaryCta.label}” in the header above. Finance lag does not change SETTLED.`}
        >
          {readinessChips.length ? (
            <Box
              role="group"
              aria-label="Settle readiness"
              data-testid="settlement-desk-readiness"
              sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mb: 1.5 }}
            >
              {readinessChips.map((c) => (
                <Box component="span" key={c.key} data-testid={`settlement-desk-readiness-${c.key}`} data-tone={c.tone}>
                  <StatusChip label={c.label} tone={READINESS_TONE[c.tone]} />
                </Box>
              ))}
            </Box>
          ) : null}
          <Stack spacing={0.25}>
            <PanelRow
              primary="Both parties agree"
              secondary={
                view.status === 'settled'
                  ? view.agreedActor
                    ? `SETTLED — amount locked by ${view.agreedActor}`
                    : 'SETTLED — amount locked · actor not stamped on this case'
                  : 'SETTLED — amount locked'
              }
              figure={moneyDual(view.agreedAmount, 'desk-next-agreed')}
              severity="info"
            />
            <PanelRow
              primary={`Raise credit for ${view.distributorName || 'the named distributor'}`}
              secondary={primaryCta.reason ?? 'Selected match lines only'}
              figure={moneyDual(view.hqCreditAmount, 'desk-next-credit')}
            />
            <PanelRow
              primary="Record payment"
              secondary="Disabled until HQ credit exists — not a status today"
              figure="—"
            />
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
            Evidence
          </Typography>
          {view.evidence.length === 0 ? (
            <PanelRow primary="No customer report on file" secondary="Claim-evidence import is empty" />
          ) : (
            view.evidence.map((e) => (
              <PanelRow key={e.id} primary={e.title} secondary={e.secondary} />
            ))
          )}
          <Box
            role="group"
            aria-label="Claim diagnostics"
            data-testid="settlement-desk-diagnostics"
            sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.75, mt: 1 }}
          >
            <StatusChip
              label={`Out-of-window rows · ${view.outOfWindowClaimRows ?? 0}`}
              tone={(view.outOfWindowClaimRows ?? 0) > 0 ? 'warning' : 'neutral'}
            />
            <StatusChip
              label={`Unresolved products · ${unresolvedCount}`}
              tone={unresolvedCount > 0 ? 'warning' : 'neutral'}
            />
            <StatusChip
              label={cst?.available ? `CST divergence · ${cstDivergence}` : `CST · ${cst?.reason ?? 'n/a'}`}
              tone={cstDivergence > 0 ? 'warning' : 'neutral'}
            />
          </Box>
          {unresolvedCount > 0 ? (
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: 'block', mt: 0.5 }}
              data-testid="settlement-desk-unresolved-tokens"
            >
              Unresolved tokens: {(view.unresolvedProducts ?? []).map((u) => `${u.token} (${u.units})`).join(', ')}
            </Typography>
          ) : null}
          {onIncludeOutOfWindowChange || onRerollup || onIntelligenceExcludeChange ? (
            <Stack spacing={0.5} sx={{ mt: 1.5 }} data-testid="settlement-desk-claim-controls">
              <Typography variant="caption" color="text.secondary">
                Claims &amp; intelligence
              </Typography>
              {onIncludeOutOfWindowChange ? (
                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={includeOutOfWindow}
                      onChange={(e) => onIncludeOutOfWindowChange(e.target.checked)}
                      slotProps={{
                        input: { 'data-testid': 'settlement-desk-include-oow' } as React.InputHTMLAttributes<HTMLInputElement>,
                      }}
                    />
                  }
                  label={<Typography variant="caption">Include out-of-window rows on the next upload</Typography>}
                />
              ) : null}
              {onIntelligenceExcludeChange ? (
                <FormControlLabel
                  control={
                    <Switch
                      size="small"
                      checked={Boolean(view.intelligenceExclude)}
                      disabled={excludingIntelligence}
                      onChange={(e) => onIntelligenceExcludeChange(e.target.checked)}
                      slotProps={{
                        input: {
                          'data-testid': 'settlement-desk-intelligence-exclude',
                        } as React.InputHTMLAttributes<HTMLInputElement>,
                      }}
                    />
                  }
                  label={
                    <Typography variant="caption">Exclude from intelligence (comparables, norms, book totals)</Typography>
                  }
                />
              ) : null}
              {onRerollup ? (
                <Box>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={rerolling}
                    onClick={onRerollup}
                    data-testid="settlement-desk-rerollup"
                  >
                    {rerolling ? 'Re-rolling…' : 'Re-rollup from claims'}
                  </Button>
                </Box>
              ) : null}
            </Stack>
          ) : null}
        </Panel>
      </Box>

      <EntityContextPanel
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        kicker="Line"
        title={selected ? lineId.value(selected.sku, selected.salesModel) : ''}
        subtitle={selected?.product}
        figures={
          selected ? (
            <HeadlineStrip columns={3}>
              <HeadlineFigure label="CIP" value={fmtInt(selected.cipQty)} compact />
              <HeadlineFigure
                label="Customer"
                value={selected.customerQty == null ? '—' : fmtInt(selected.customerQty)}
                compact
              />
              <HeadlineFigure
                label="Support / unit"
                value={
                  selected.supportUnit == null
                    ? '—'
                    : moneyDual(selected.supportUnit, 'desk-line-support')
                }
                compact
              />
            </HeadlineStrip>
          ) : null
        }
      >
        {selected ? (
          <KeyValueList
            items={[
              { k: 'SKU', v: selected.sku },
              { k: 'Sales model', v: selected.salesModel ?? '—' },
              { k: 'Distributor', v: selected.distributor },
              { k: 'Corroboration', v: CORROBORATION_CHIP[selected.corroboration] },
              { k: 'Reason', v: selected.corroborationReason },
              { k: 'In HQ credit', v: selected.includeInCredit ? 'Yes' : 'No' },
              { k: 'Estimate', v: fmtInt(selected.estimateQty) },
            ]}
          />
        ) : null}
      </EntityContextPanel>
    </Stack>
  );
}
