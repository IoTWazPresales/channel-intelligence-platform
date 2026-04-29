'use client';

import { Alert, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';

type Row = {
  concept: string;
  dbField: string;
  userLabel: string;
  kind: 'input' | 'evidence' | 'output' | 'override' | 'system';
  editedIn: string;
  displayedIn: string;
  readiness: 'yes' | 'no' | 'partial';
  calculator: 'yes' | 'no' | 'partial';
  currencyNote: string;
  notes: string;
};

const ROWS: Row[] = [
  {
    concept: 'Open-channel placeholder customer',
    dbField: 'dim_customer (code OPEN_CHANNEL)',
    userLabel: 'System reference customer',
    kind: 'system',
    editedIn: 'Seed / migration (not from uploads)',
    displayedIn: 'Commercial planner sync / readiness',
    readiness: 'yes',
    calculator: 'no',
    currencyNote: '—',
    notes: 'Required for lineup→plan workflows when customer is unknown.',
  },
  {
    concept: 'Unassigned placeholder distributor',
    dbField: 'dim_distributor (code UNASSIGNED)',
    userLabel: 'System reference distributor',
    kind: 'system',
    editedIn: 'Seed / migration (not from uploads)',
    displayedIn: 'Commercial planner sync / readiness',
    readiness: 'yes',
    calculator: 'no',
    currencyNote: '—',
    notes: 'Holds lines until distributor is resolved; economics need real distributor terms.',
  },
  {
    concept: 'Customer default margin',
    dbField: 'commercial_customer_term.customer_margin_pct',
    userLabel: 'Customer margin %',
    kind: 'input',
    editedIn: 'Customer admin · Planner defaults',
    displayedIn: 'Planner line effective columns · economics',
    readiness: 'yes',
    calculator: 'yes',
    currencyNote: 'Unitless %',
    notes: 'Missing row → calculator may use 0% with flags; configure on Customer page.',
  },
  {
    concept: 'Customer default rebate / support',
    dbField: 'commercial_customer_term.customer_rebate_pct',
    userLabel: 'Customer rebate / support %',
    kind: 'input',
    editedIn: 'Customer admin · Planner defaults',
    displayedIn: 'Planner line effective columns · economics',
    readiness: 'yes',
    calculator: 'yes',
    currencyNote: 'Unitless %',
    notes: 'Not CPOR workflow—percentage stack only.',
  },
  {
    concept: 'Distributor default margin',
    dbField: 'commercial_distributor_term.distributor_margin_pct',
    userLabel: 'Distributor margin %',
    kind: 'input',
    editedIn: 'Distributor admin · Planner defaults',
    displayedIn: 'Planner line effective columns · economics',
    readiness: 'yes',
    calculator: 'yes',
    currencyNote: 'Unitless %',
    notes: 'Missing row → calculator may use 0% with flags.',
  },
  {
    concept: 'SKU controlled cost (PM bottom)',
    dbField: 'commercial_sku_assumption.landed_cost_usd',
    userLabel: 'Controlled cost (stored USD amount today)',
    kind: 'input',
    editedIn: 'Planner defaults (Product admin link later)',
    displayedIn: 'Planner line effective controlled cost',
    readiness: 'yes',
    calculator: 'yes',
    currencyNote: 'DB column name contains USD; not logistics landed cost',
    notes: 'Risk: “landed” in DB name is misleading—true landed = controlled + logistics (future). Not populated from DAP.',
  },
  {
    concept: 'SKU VAT / FX / reserves',
    dbField: 'commercial_sku_assumption.vat_rate_pct, fx_rate_to_usd, reserve_*',
    userLabel: 'VAT %, FX (plan CCY per 1 USD), reserves',
    kind: 'input',
    editedIn: 'Planner defaults',
    displayedIn: 'Planner effective columns',
    readiness: 'partial',
    calculator: 'yes',
    currencyNote: 'FX bridges plan-currency SRP to USD economics path',
    notes: 'fx_rate_to_usd = local currency units per 1 USD (see calculator + read_model).',
  },
  {
    concept: 'Plan line customer-facing prices',
    dbField: 'commercial_plan_line.target_srp_local, promo_srp_local',
    userLabel: 'Customer-facing list price, campaign/event price',
    kind: 'input',
    editedIn: 'Planner grid · sync from lineup',
    displayedIn: 'Planner grid · line detail',
    readiness: 'partial',
    calculator: 'yes',
    currencyNote: 'Same currency as commercial_plan.currency_code',
    notes: 'SRP naming in API; UI uses flexible customer-facing labels.',
  },
  {
    concept: 'Line overrides',
    dbField: 'commercial_plan_line.override_*',
    userLabel: 'Override margins, controlled cost, VAT, FX, reserves',
    kind: 'override',
    editedIn: 'Planner line edit (where exposed)',
    displayedIn: 'Line detail chips · effective columns',
    readiness: 'no',
    calculator: 'yes',
    currencyNote: 'override_landed_cost_usd is USD scalar today',
    notes: 'Explicit per-line; audited in persisted row.',
  },
  {
    concept: 'Economics outputs',
    dbField: 'commercial_plan_line.calc_sell_in_price_usd, calc_buy_price_usd, calc_internal_gp_usd, …',
    userLabel: 'Estimated sell-in, distributor net, internal GP, reserves (USD path)',
    kind: 'output',
    editedIn: 'Recalculate (POST …/recalculate)',
    displayedIn: 'Planner grid · line detail',
    readiness: 'partial',
    calculator: 'yes',
    currencyNote: 'Stored USD; local columns derived via FX',
    notes: 'calc_customer_gp_pct / calc_distributor_gp_pct echo input margins, not derived GP%.',
  },
  {
    concept: 'DAP (lineup)',
    dbField: 'commercial_lineup_line.dap_evidence_local; historical dap_local',
    userLabel: 'DAP evidence',
    kind: 'evidence',
    editedIn: 'Lineup import / sync (evidence only)',
    displayedIn: 'Workbench · lineup coverage · line evidence chips',
    readiness: 'no',
    calculator: 'no',
    currencyNote: 'Line / header currency context',
    notes: 'Must never map to landed_cost_usd, SKU assumption, or cost fields.',
  },
  {
    concept: 'Disti-reported cost (import)',
    dbField: 'historical_lineup_import_line.disti_cost_local',
    userLabel: 'Disti-reported cost evidence',
    kind: 'evidence',
    editedIn: 'Historical lineup import',
    displayedIn: 'Lineup coverage / gaps (where exposed)',
    readiness: 'no',
    calculator: 'no',
    currencyNote: 'Import currency context',
    notes: 'Evidence until governed; not PM bottom.',
  },
  {
    concept: 'Pricing facts',
    dbField: 'fact_pricing.net_price, list_price, currency',
    userLabel: 'Price facts',
    kind: 'evidence',
    editedIn: 'Pricing page / API',
    displayedIn: 'Planner suggestions (latest net)',
    readiness: 'no',
    calculator: 'no',
    currencyNote: 'Per fact row',
    notes: 'Hints for SRP; separate from controlled cost.',
  },
  {
    concept: 'Product master',
    dbField: 'dim_product.*, specs_json',
    userLabel: 'SKU, catalogue, specs',
    kind: 'input',
    editedIn: 'Product master import · admin products',
    displayedIn: 'Planner catalogue/spec columns',
    readiness: 'no',
    calculator: 'no',
    currencyNote: '—',
    notes: 'Identity anchor; optional logistics keys may live in specs/EAV later.',
  },
];

export function CommercialDataMap() {
  return (
    <Stack spacing={2} data-testid="commercial-data-map">
      <Alert severity="info" sx={{ py: 0.75 }}>
        Read-only field map for commercial planner economics. DB/API names stay unchanged; labels here match the UI
        naming pass. DAP and import costs are <strong>evidence only</strong>—never treated as controlled cost.
      </Alert>
      <Paper variant="outlined" sx={{ overflow: 'auto' }}>
        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell>Concept</TableCell>
              <TableCell>DB / API field</TableCell>
              <TableCell>User-facing label</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Edited in</TableCell>
              <TableCell>Displayed in</TableCell>
              <TableCell>Readiness</TableCell>
              <TableCell>Calculator</TableCell>
              <TableCell>Currency / basis</TableCell>
              <TableCell>Notes / risk</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {ROWS.map((r) => (
              <TableRow key={r.concept}>
                <TableCell>{r.concept}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>{r.dbField}</TableCell>
                <TableCell>{r.userLabel}</TableCell>
                <TableCell>{r.kind}</TableCell>
                <TableCell>{r.editedIn}</TableCell>
                <TableCell>{r.displayedIn}</TableCell>
                <TableCell>{r.readiness}</TableCell>
                <TableCell>{r.calculator}</TableCell>
                <TableCell>{r.currencyNote}</TableCell>
                <TableCell>{r.notes}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      <Typography variant="caption" color="text.secondary">
        Deferred (needs migration / future modules): payment terms, distributor rebate, cost currency & source,
        logistics assumptions, FX scenario table, true landed cost stack, pricing simulation, BOM/configurator.
      </Typography>
    </Stack>
  );
}
