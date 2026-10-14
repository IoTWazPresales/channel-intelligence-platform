'use client';

import { Alert, Box, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import { fmtInt, fmtMoney, fmtPct } from '@/features/promotions-funding/format';
import { HeadlineFigure, HeadlineStrip } from '@/features/workbench-ui/HeadlineFigure';
import { Panel } from '@/features/workbench-ui/Panel';
import { apiGet } from '@/lib/api';

export type CaseMarginLine = {
  line_id: number;
  product_id: number;
  product_sku: string | null;
  product_name: string | null;
  units: number | null;
  units_source: 'result_qty' | 'estimate_qty';
  margin_per_unit: number | null;
  margin_total: number | null;
  margin_pct: number | null;
  dap_per_unit: number | null;
  pm_controlled_cost_per_unit: number | null;
  landed_cost_per_unit: number | null;
  support_per_unit: number | null;
  flags: string[];
};

export type CaseMarginRead = {
  case_id: number;
  cost_basis: string;
  currency: string;
  definition: string;
  roe: number | null;
  margin_total: number | null;
  lines_included: number;
  lines_total: number;
  lines: CaseMarginLine[];
};

/** Flags in words; the raw code stays out of the UI. */
const FLAG_TEXT: Record<string, string> = {
  missing_dap: 'DAP not computable',
  missing_pm_controlled_cost: 'No PM controlled cost',
  no_sku_economics: 'No SKU economics',
  cost_currency_not_usd: 'Cost not in USD',
  no_case_roe: 'No case exchange rate',
  no_customer_rebate_term: 'No customer rebate term (0 used)',
  no_distributor_margin_term: 'No distributor margin term (0 used)',
  negative_margin: 'Below PM controlled cost',
  missing_quantity: 'No units',
};

function flagWords(flags: string[]): string {
  return flags
    .filter((f) => f !== 'landed_cost_not_recorded')
    .map((f) => FLAG_TEXT[f] ?? f.replace(/_/g, ' '))
    .join('; ');
}

/** N-0080: case margin vs PM controlled cost. DAP and landed cost sit beside it, never in it. */
export function CaseMarginPanel({ caseId }: { caseId: number }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['cpor-case-margin', caseId],
    queryFn: ({ signal }) => apiGet<CaseMarginRead>(`/api/v1/cpor/cases/${caseId}/margin`, { signal }),
    enabled: caseId > 0,
  });

  const ccy = data?.currency ?? 'USD';
  const landedKnown = (data?.lines ?? []).filter((l) => l.landed_cost_per_unit != null).length;

  return (
    <Panel
      title="Margin vs PM controlled cost"
      subtitle="DAP minus PM controlled cost minus support, per unit, times units. DAP and landed cost are shown beside it and are not part of it."
      flush
    >
      <Box sx={{ px: 2, pb: 1.5 }} data-testid="case-margin-panel">
        {isLoading ? (
          <Typography variant="body2" color="text.secondary">
            Loading margin…
          </Typography>
        ) : isError || !data ? (
          <Alert severity="error">Margin could not be loaded.</Alert>
        ) : (
          <>
            <HeadlineStrip columns={3}>
              <HeadlineFigure
                lead
                label={`Margin vs PM controlled cost (${ccy})`}
                value={data.margin_total == null ? '—' : fmtMoney(data.margin_total, ccy)}
                caption={`${fmtInt(data.lines_included ?? 0)} of ${fmtInt(data.lines_total ?? 0)} lines have every input`}
                severity={data.margin_total != null && data.margin_total < 0 ? 'bad' : 'neutral'}
                state={data.margin_total == null ? 'empty' : 'ready'}
                stateNote={data.margin_total == null ? 'No line has DAP, PM controlled cost and units.' : undefined}
                testId="case-margin-total"
              />
              <HeadlineFigure
                label="Cost basis"
                value="PM controlled cost"
                caption="SKU economics (PM bottom)"
                testId="case-margin-basis"
              />
              <HeadlineFigure
                label="Landed cost recorded"
                value={`${fmtInt(landedKnown)} of ${fmtInt(data.lines_total ?? 0)}`}
                caption="Shown per line; never subtracted"
                testId="case-margin-landed-count"
              />
            </HeadlineStrip>
            <TableContainer sx={{ mt: 1.5, overflowX: 'auto' }}>
              <Table size="small" aria-label="Margin per case line">
                <TableHead>
                  <TableRow>
                    <TableCell scope="col">Product</TableCell>
                    <TableCell scope="col" align="right">
                      Units
                    </TableCell>
                    <TableCell scope="col" align="right">
                      DAP / unit
                    </TableCell>
                    <TableCell scope="col" align="right">
                      PM controlled cost / unit
                    </TableCell>
                    <TableCell scope="col" align="right">
                      Support / unit
                    </TableCell>
                    <TableCell scope="col" align="right">
                      Margin / unit
                    </TableCell>
                    <TableCell scope="col" align="right">
                      Margin total
                    </TableCell>
                    <TableCell scope="col" align="right">
                      Landed cost / unit (not in margin)
                    </TableCell>
                    <TableCell scope="col">Notes</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(data.lines ?? []).map((l) => (
                    <TableRow key={l.line_id} data-testid={`case-margin-line-${l.line_id}`}>
                      <TableCell component="th" scope="row">
                        {l.product_sku ?? l.product_name ?? `Line ${l.line_id}`}
                      </TableCell>
                      <TableCell align="right">
                        {fmtInt(l.units)}
                        <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
                          {l.units_source === 'result_qty' ? 'result' : 'estimate'}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">{fmtMoney(l.dap_per_unit, ccy)}</TableCell>
                      <TableCell align="right">{fmtMoney(l.pm_controlled_cost_per_unit, ccy)}</TableCell>
                      <TableCell align="right">{fmtMoney(l.support_per_unit, ccy)}</TableCell>
                      <TableCell align="right">
                        {fmtMoney(l.margin_per_unit, ccy)}
                        {l.margin_pct != null ? (
                          <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
                            {fmtPct(l.margin_pct)} of DAP
                          </Typography>
                        ) : null}
                      </TableCell>
                      <TableCell align="right">{fmtMoney(l.margin_total, ccy)}</TableCell>
                      <TableCell align="right">
                        {l.landed_cost_per_unit == null ? 'Not recorded' : fmtMoney(l.landed_cost_per_unit, ccy)}
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption" color="text.secondary">
                          {flagWords(l.flags) || '—'}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}
      </Box>
    </Panel>
  );
}
