'use client';

import type { ColDef } from 'ag-grid-community';
import { Box, Button, Stack, Typography } from '@mui/material';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';

import { fmtCurrency, fmtInt } from '../fixtures/entities';
import {
  corroborationLabel,
  lineAmount,
  settleCase,
  settleEvidence,
  settleLines,
  settleStageLabel,
  settleStages,
  type SettleLine,
} from '../fixtures/settlementDesk';
import { ScopeBar, StatusChip } from '../primitives/controls';
import { DomainHeader } from '../primitives/DomainHeader';
import { EntityContextPanel, KeyValueList } from '../primitives/EntityContextPanel';
import { HeadlineFigure, HeadlineStrip } from '../primitives/HeadlineFigure';
import { LifecycleRail } from '../primitives/LifecycleRail';
import { Panel, PanelRow } from '../primitives/Panel';

const tone = (c: SettleLine['corroboration']): 'danger' | 'warning' | 'success' | 'info' | 'neutral' =>
  c === 'match' ? 'success' : c === 'mismatch' || c === 'cip_only' ? 'danger' : c === 'pending' ? 'warning' : 'neutral';

/**
 * Composition A — Ken’s next-action desk.
 * Optimises for: one case, one current stage, one primary CTA. Grid is the work.
 * Not a new primitive: evaluated a second LifecycleRail (rejected — one rail already owns the job).
 */
export function SettlementDeskA() {
  const [mismatchOnly, setMismatchOnly] = useState(false);
  const [disti, setDisti] = useState<string | null>(null);
  const [selected, setSelected] = useState<SettleLine | null>(null);

  const distributors = useMemo(() => Array.from(new Set(settleLines.map((l) => l.distributor))), []);
  const rows = useMemo(
    () =>
      settleLines.filter(
        (l) =>
          (!disti || l.distributor === disti) &&
          (!mismatchOnly || l.corroboration !== 'match'),
      ),
    [disti, mismatchOnly],
  );

  const creditLines = settleLines.filter((l) => l.includeInCredit);
  const creditAmount = creditLines.reduce((s, l) => s + lineAmount(l.customerQty ?? 0, l.supportUnit), 0);

  const columnDefs = useMemo<ColDef<SettleLine>[]>(
    () => [
      { field: 'sku', headerName: 'SKU', width: 120, pinned: 'left' },
      { field: 'product', headerName: 'Product', minWidth: 200, flex: 1.4 },
      { field: 'distributor', headerName: 'Distributor', minWidth: 160, flex: 1 },
      { field: 'estimateQty', headerName: 'Estimate', type: 'rightAligned', width: 100, valueFormatter: (p) => fmtInt(p.value) },
      { field: 'cipQty', headerName: 'CIP qty', type: 'rightAligned', width: 100, valueFormatter: (p) => fmtInt(p.value) },
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
        width: 150,
        cellRenderer: (p: { data: SettleLine }) => (
          <StatusChip label={corroborationLabel[p.data.corroboration]} tone={tone(p.data.corroboration)} />
        ),
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

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="settlement-desk-a">
      <DomainHeader
        crumbs={[{ label: 'Promotions & Funding' }, { label: 'Settle a case' }]}
        title={`${settleCase.id} · ${settleCase.customer}`}
        description={`${settleCase.programme} · ${settleCase.window} · ${settleCase.distributor}. Ken’s desk: the next commercial action is visible without opening tabs.`}
        meta={`Opened ${settleCase.openedOn} · Ended ${settleCase.endedOn} · ${settleCase.currency}`}
        actions={
          <>
            <Button variant="outlined" size="small">
              Upload customer report
            </Button>
            <Button variant="contained" size="small">
              Raise HQ credit · {fmtCurrency(creditAmount, { compact: true })}
            </Button>
          </>
        }
      />

      <LifecycleRail stages={[...settleStages]} labels={settleStageLabel} current={settleCase.stage} />

      <HeadlineStrip columns={5}>
        <HeadlineFigure label="CIP reconciled" value={fmtCurrency(settleCase.cipAmount, { compact: true })} compact caption="Auto vs sell-out" />
        <HeadlineFigure label="Customer report" value={fmtCurrency(settleCase.customerAmount, { compact: true })} compact caption="Evidence on file" />
        <HeadlineFigure
          label="Agreed (SETTLED)"
          value={fmtCurrency(settleCase.agreedAmount, { compact: true })}
          compact
          severity="good"
          caption="Both parties agree"
        />
        <HeadlineFigure
          label="Paid"
          value={fmtCurrency(settleCase.paidAmount, { compact: true })}
          compact
          caption="Not in schema today"
        />
        <HeadlineFigure label="In HQ credit pack" value={fmtCurrency(creditAmount, { compact: true })} compact caption={`${creditLines.length} lines`} />
      </HeadlineStrip>

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
        summary={`${rows.length} of ${settleLines.length} lines · SETTLED means both agree; PAID is after money moves`}
        onClear={() => {
          setMismatchOnly(false);
          setDisti(null);
        }}
      />

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '2fr 1fr' } }}>
        <EnterpriseDataGrid<SettleLine>
          rowData={rows}
          columnDefs={columnDefs}
          height={360}
          gridOptions={{
            onRowClicked: (e) => e.data && setSelected(e.data),
            getRowId: (p) => p.data.id,
          }}
        />
        <Panel
          title="Next action"
          subtitle="One CTA for the current stage. Finance lag does not change SETTLED."
          actions={
            <Button size="small" variant="contained">
              Raise HQ credit
            </Button>
          }
        >
          <Stack spacing={0.25}>
            <PanelRow primary="Both parties agree" secondary="SETTLED — amount locked" figure={fmtCurrency(settleCase.agreedAmount, { compact: true })} severity="info" />
            <PanelRow primary="Raise credit for Meridian" secondary="Selected match lines only" figure={fmtCurrency(creditAmount, { compact: true })} />
            <PanelRow primary="Record payment" secondary="Disabled until HQ credit exists — not a status today" figure="—" />
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
            Evidence
          </Typography>
          {settleEvidence.map((e) => (
            <PanelRow key={e.id} primary={e.title} secondary={`${e.kind} · ${e.uploadedAt} · ${e.by}`} />
          ))}
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
              <HeadlineFigure label="Customer" value={selected.customerQty == null ? '—' : fmtInt(selected.customerQty)} compact />
              <HeadlineFigure label="Support / unit" value={fmtCurrency(selected.supportUnit)} compact />
            </HeadlineStrip>
          ) : null
        }
      >
        {selected ? (
          <KeyValueList
            items={[
              { k: 'Distributor', v: selected.distributor },
              { k: 'Corroboration', v: corroborationLabel[selected.corroboration] },
              { k: 'In HQ credit', v: selected.includeInCredit ? 'Yes' : 'No' },
              { k: 'Estimate', v: fmtInt(selected.estimateQty) },
            ]}
          />
        ) : null}
      </EntityContextPanel>
    </Stack>
  );
}
