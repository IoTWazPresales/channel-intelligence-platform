'use client';

import type { ColDef } from 'ag-grid-community';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useMemo, useRef, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { DualMoney } from '@/features/cpor/DualMoney';
import { formatLocalMoney } from '@/features/cpor/fxDisplay';
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
};

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
}: Props) {
  const [mismatchOnly, setMismatchOnly] = useState(false);
  const [disti, setDisti] = useState<string | null>(null);
  const [selected, setSelected] = useState<SettlementDeskLine | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

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
      { field: 'sku', headerName: 'SKU', width: 120, pinned: 'left' },
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
    [],
  );

  const codeMeta = view.customerCode ? ` · ${view.customerCode}` : '';

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
        meta={`Opened ${view.openedOn ?? '—'} · Ended ${view.endedOn ?? '—'} · ${view.currency}${codeMeta}`}
        actions={
          <>
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

      <HeadlineStrip columns={5}>
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
          subtitle="One CTA for the current stage. Finance lag does not change SETTLED."
          actions={
            <Button
              size="small"
              variant="contained"
              disabled={primaryCta.disabled}
              onClick={primaryCta.onClick}
              data-testid="settlement-desk-next-cta"
            >
              {primaryCta.label}
            </Button>
          }
        >
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
        </Panel>
      </Box>

      <EntityContextPanel
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        kicker="Line"
        title={selected?.sku ?? ''}
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
