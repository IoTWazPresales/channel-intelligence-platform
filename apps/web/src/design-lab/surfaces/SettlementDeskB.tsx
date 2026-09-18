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
 * Composition B — two-tape corroboration desk.
 * Optimises for: seeing CIP recon and the customer report at the same time, then agreeing.
 * Evaluated a second grid wrapper (rejected — EnterpriseDataGrid already hosts both tapes’ lines).
 * Evaluated a new split-pane primitive (rejected — Panel + PanelRow already do two columns).
 */
export function SettlementDeskB() {
  const [packetOpen, setPacketOpen] = useState(false);
  const contested = settleLines.filter((l) => l.corroboration !== 'match');
  const matched = settleLines.filter((l) => l.corroboration === 'match');

  const columnDefs = useMemo<ColDef<SettleLine>[]>(
    () => [
      { field: 'sku', headerName: 'SKU', width: 120, pinned: 'left' },
      { field: 'product', headerName: 'Product', minWidth: 180, flex: 1.3 },
      { field: 'cipQty', headerName: 'CIP', type: 'rightAligned', width: 90, valueFormatter: (p) => fmtInt(p.value) },
      {
        field: 'customerQty',
        headerName: 'Customer',
        type: 'rightAligned',
        width: 100,
        valueFormatter: (p) => (p.value == null ? '—' : fmtInt(p.value)),
      },
      {
        headerName: 'Delta qty',
        width: 100,
        type: 'rightAligned',
        valueGetter: (p) => (p.data?.customerQty == null ? null : p.data.cipQty - p.data.customerQty),
        valueFormatter: (p) => (p.value == null ? '—' : fmtInt(p.value)),
      },
      {
        headerName: 'Delta value',
        width: 120,
        type: 'rightAligned',
        valueGetter: (p) =>
          p.data?.customerQty == null ? null : lineAmount(p.data.cipQty - p.data.customerQty, p.data.supportUnit),
        valueFormatter: (p) => (p.value == null ? '—' : fmtCurrency(p.value)),
      },
      {
        field: 'corroboration',
        headerName: 'Tape',
        width: 150,
        cellRenderer: (p: { data: SettleLine }) => (
          <StatusChip label={corroborationLabel[p.data.corroboration]} tone={tone(p.data.corroboration)} />
        ),
      },
    ],
    [],
  );

  return (
    <Stack spacing={2} sx={{ mt: 2 }} data-testid="settlement-desk-b">
      <DomainHeader
        crumbs={[{ label: 'Promotions & Funding' }, { label: 'Settle a case' }]}
        title={`${settleCase.id} · corroborate the two tapes`}
        description="CIP recon on the left. Customer confirmation on the right. SETTLED is the overlap. PAID is later and is not a column today."
        meta={`${settleCase.customer} · ${settleCase.programme} · ${settleCase.window}`}
        actions={
          <>
            <Button variant="outlined" size="small" onClick={() => setPacketOpen(true)}>
              Open evidence packet
            </Button>
            <Button variant="contained" size="small">
              Lock agreed amount
            </Button>
          </>
        }
      />

      <LifecycleRail stages={[...settleStages]} labels={settleStageLabel} current={settleCase.stage} dense />

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' } }}>
        <Panel title="CIP tape" subtitle="Automatic recon of sell-out against the case window. System-owned.">
          <HeadlineStrip columns={2}>
            <HeadlineFigure label="Reconciled" value={fmtCurrency(settleCase.cipAmount, { compact: true })} compact />
            <HeadlineFigure label="Lines" value={fmtInt(settleLines.length)} compact />
          </HeadlineStrip>
          <Stack spacing={0.25} sx={{ mt: 1 }}>
            {settleLines.map((l) => (
              <PanelRow
                key={`cip-${l.id}`}
                primary={`${l.sku} · ${fmtInt(l.cipQty)}`}
                secondary={l.product}
                figure={fmtCurrency(lineAmount(l.cipQty, l.supportUnit), { compact: true })}
              />
            ))}
          </Stack>
        </Panel>
        <Panel title="Customer tape" subtitle="Confirmation workbook returned as evidence. Customer-owned.">
          <HeadlineStrip columns={2}>
            <HeadlineFigure label="Reported" value={fmtCurrency(settleCase.customerAmount, { compact: true })} compact />
            <HeadlineFigure label="Pending lines" value={fmtInt(settleLines.filter((l) => l.customerQty == null).length)} compact severity="warn" />
          </HeadlineStrip>
          <Stack spacing={0.25} sx={{ mt: 1 }}>
            {settleLines.map((l) => (
              <PanelRow
                key={`cust-${l.id}`}
                primary={`${l.sku} · ${l.customerQty == null ? 'missing' : fmtInt(l.customerQty)}`}
                secondary={l.corroboration === 'match' ? 'Agrees with CIP' : corroborationLabel[l.corroboration]}
                figure={l.customerQty == null ? '—' : fmtCurrency(lineAmount(l.customerQty, l.supportUnit), { compact: true })}
                severity={l.corroboration === 'mismatch' || l.corroboration === 'cip_only' ? 'danger' : l.corroboration === 'pending' ? 'warning' : 'neutral'}
              />
            ))}
          </Stack>
        </Panel>
      </Box>

      <Panel title="Overlap — what SETTLED would lock" subtitle={`${matched.length} matched · ${contested.length} still open. Do not mix this with paid.`}>
        <ScopeBar
          chips={[
            { key: 'matched', label: `Matched · ${matched.length}`, active: true, onToggle: () => undefined, tone: 'success' },
            { key: 'open', label: `Open · ${contested.length}`, active: true, onToggle: () => undefined, tone: 'warning' },
          ]}
          summary="Matched lines can lock. Open lines stay on the grid until Ken or a PM agrees a qty."
        />
        <EnterpriseDataGrid<SettleLine>
          rowData={contested}
          columnDefs={columnDefs}
          height={240}
          gridOptions={{ getRowId: (p) => p.data.id }}
        />
      </Panel>

      <EntityContextPanel
        open={packetOpen}
        onClose={() => setPacketOpen(false)}
        kicker="Evidence packet"
        title={settleCase.id}
        subtitle="CIP recon and customer report are both evidence. Neither is payment."
        figures={
          <HeadlineStrip columns={2}>
            <HeadlineFigure label="CIP" value={fmtCurrency(settleCase.cipAmount, { compact: true })} compact />
            <HeadlineFigure label="Customer" value={fmtCurrency(settleCase.customerAmount, { compact: true })} compact />
          </HeadlineStrip>
        }
        footer={
          <Button size="small" variant="outlined">
            Upload another file
          </Button>
        }
      >
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
          Files on this case
        </Typography>
        {settleEvidence.map((e) => (
          <PanelRow key={e.id} primary={e.title} secondary={`${e.kind} · ${e.uploadedAt} · ${e.by}`} />
        ))}
        <Box sx={{ mt: 2 }}>
          <KeyValueList
            items={[
              { k: 'Distributor for credit', v: settleCase.distributor },
              { k: 'Agreed if locked', v: fmtCurrency(settleCase.agreedAmount) },
              { k: 'Paid today', v: 'No paid/closed status on cpor_case' },
            ]}
          />
        </Box>
      </EntityContextPanel>
    </Stack>
  );
}
