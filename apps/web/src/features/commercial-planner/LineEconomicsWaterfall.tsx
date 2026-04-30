'use client';

import { Alert, Chip, Divider, Stack, Typography } from '@mui/material';

function fmtMarginPct(v: number | null | undefined): string {
  if (v == null) return '—';
  const pct = v < 1.0 ? v * 100 : v;
  return `${pct.toFixed(2)}%`;
}

function fmtCurrency(v: number | null | undefined): string {
  if (v == null) return '—';
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtMoneyWithCcy(v: number | null | undefined, currencyCode: string): string {
  if (v == null) return '—';
  return `${fmtCurrency(v)} ${currencyCode}`;
}

export type WaterfallLine = {
  /** Present when parent passes through API flags (e.g. missing controlled cost). */
  calc_flags?: string[];
  target_srp_local: number;
  promo_srp_local: number | null;
  effective_vat_rate_pct?: number | null;
  effective_fx_plan_currency_per_cost_currency?: number | null;
  effective_customer_margin_pct?: number | null;
  effective_customer_rebate_pct?: number | null;
  effective_distributor_margin_pct?: number | null;
  effective_reserve_total_pct?: number | null;
  effective_promo_reserve_split_pct?: number | null;
  effective_controlled_cost_amount?: number | null;
  effective_controlled_cost_currency_code?: string | null;
  economics_calc_currency_code?: string | null;
  override_controlled_cost_amount?: number | null;
  calc_oem_sell_in_amount: number | null;
  calc_distributor_net_amount: number | null;
  calc_campaign_support_reserve_amount: number | null;
  calc_non_campaign_reserve_amount: number | null;
  calc_internal_gp_amount: number | null;
  economics_line_trust?: string;
  economics_line_trust_reasons?: string[];
  economics_field_provenance?: Record<string, { source: string; trusted?: boolean; detail?: string }>;
};

const SOURCE_LABELS: Record<string, string> = {
  line_override: 'Line override',
  planner_default_terms: 'Planner default terms',
  sku_economics_input: 'SKU economics input',
  placeholder_or_missing: 'Placeholder / missing',
  missing: 'Missing',
  unknown: 'Unknown',
};

function provChip(p: { source: string; trusted?: boolean; detail?: string } | undefined) {
  if (!p) return null;
  const label = SOURCE_LABELS[p.source] ?? p.source;
  const untrusted = p.trusted === false;
  return (
    <Chip
      size="small"
      variant="outlined"
      label={untrusted ? `${label} (untrusted)` : label}
      color={untrusted ? 'warning' : 'default'}
      sx={{ height: 22, fontSize: '0.65rem' }}
    />
  );
}

type Props = {
  line: WaterfallLine;
  planCurrencyCode: string;
  /** Fallback when line.economics_calc_currency_code is absent (older payloads). */
  economicsReportingCurrency?: string;
  /** Map calc_flag / trust reason codes to readable text (from planner page). */
  formatTrustReason?: (code: string) => string;
  dapEvidenceLocal?: number | null;
};

/** Per-line economics waterfall (read-only; uses persisted calc_* and effective_* from API). */
export function LineEconomicsWaterfall({
  line,
  planCurrencyCode,
  economicsReportingCurrency = 'USD',
  formatTrustReason,
  dapEvidenceLocal,
}: Props) {
  const prov = line.economics_field_provenance ?? {};
  const tier = line.economics_line_trust ?? 'ok';
  const reasons = line.economics_line_trust_reasons ?? [];
  const econCcy = (line.economics_calc_currency_code ?? economicsReportingCurrency).trim() || economicsReportingCurrency;
  const costCcy = (line.effective_controlled_cost_currency_code ?? '').trim() || econCcy;
  const flags = line.calc_flags ?? [];
  const costMissing =
    flags.includes('missing_or_invalid_landed_cost') ||
    flags.includes('missing_or_invalid_controlled_cost') ||
    flags.includes('missing_sku_assumption');

  return (
    <Stack spacing={1.25} data-testid="line-economics-waterfall">
      {line.calc_oem_sell_in_amount == null ? (
        <Typography variant="caption" color="text.secondary" display="block" data-testid="line-detail-not-calculated">
          Not calculated yet — press <strong>Recalculate</strong>.
        </Typography>
      ) : null}
      <Alert
        severity={tier === 'blocked' ? 'error' : tier === 'warning' ? 'warning' : 'success'}
        sx={{ py: 0.5 }}
        data-testid="line-economics-trust-alert"
      >
        <Typography variant="body2" fontWeight={600}>
          Economics trust: {tier === 'blocked' ? 'Blocked / unreliable' : tier === 'warning' ? 'Review required' : 'Ok'}
        </Typography>
        {reasons.length ? (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            Reasons: {reasons.map((r) => (formatTrustReason ? formatTrustReason(r) : r)).join(' · ')}
          </Typography>
        ) : (
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            No blocking flags on this line.
          </Typography>
        )}
      </Alert>

      {costMissing ? (
        <Typography variant="caption" color="warning.main" display="block" data-testid="line-detail-cost-missing">
          Controlled cost unavailable — add SKU economics in Planner defaults or a line override. DAP evidence is not PM
          bottom.
        </Typography>
      ) : null}

      <Typography variant="caption" color="text.secondary" display="block">
        Calculator amounts (sell-in, distributor net, reserves, internal GP) are shown in{' '}
        <strong>{econCcy}</strong> per persisted <code>economics_calc_currency_code</code>. Controlled cost uses{' '}
        <strong>{costCcy}</strong> when set on the SKU or line override.
      </Typography>

      <Typography variant="subtitle2">Price / commercial stack</Typography>
      <Stack spacing={0.5}>
        <Typography variant="body2">
          Customer-facing list price ({planCurrencyCode}): {fmtCurrency(line.target_srp_local)}
        </Typography>
        {line.promo_srp_local != null ? (
          <Typography variant="body2">
            Campaign / event price ({planCurrencyCode}): {fmtCurrency(line.promo_srp_local)}
          </Typography>
        ) : null}
        <Stack direction="row" alignItems="center" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Typography variant="body2">VAT (effective): {fmtMarginPct(line.effective_vat_rate_pct ?? null)}</Typography>
          {provChip(prov['vat_rate_pct'])}
        </Stack>
        <Stack direction="row" alignItems="center" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Typography variant="body2">
            FX bridge ({planCurrencyCode} per 1 {costCcy}): {line.effective_fx_plan_currency_per_cost_currency ?? '—'}
          </Typography>
          {provChip(prov['fx_plan_currency_per_cost_currency'])}
        </Stack>
        <Stack direction="row" alignItems="center" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Typography variant="body2">Customer margin % (input): {fmtMarginPct(line.effective_customer_margin_pct ?? null)}</Typography>
          {provChip(prov['customer_margin_pct'])}
        </Stack>
        <Stack direction="row" alignItems="center" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Typography variant="body2">
            Customer rebate / support % (input): {fmtMarginPct(line.effective_customer_rebate_pct ?? null)}
          </Typography>
          {provChip(prov['customer_rebate_pct'])}
        </Stack>
        <Stack direction="row" alignItems="center" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Typography variant="body2">
            Distributor margin % (input): {fmtMarginPct(line.effective_distributor_margin_pct ?? null)}
          </Typography>
          {provChip(prov['distributor_margin_pct'])}
        </Stack>
        <Divider sx={{ my: 0.5 }} />
        <Typography variant="body2">
          Estimated OEM/channel sell-in ({econCcy} / unit):{' '}
          {line.calc_oem_sell_in_amount != null
            ? fmtMoneyWithCcy(line.calc_oem_sell_in_amount, econCcy)
            : '— (recalculate)'}
          <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
            (calculated output)
          </Typography>
        </Typography>
        <Typography variant="body2">
          Estimated distributor net ({econCcy} / unit):{' '}
          {line.calc_distributor_net_amount != null ? fmtMoneyWithCcy(line.calc_distributor_net_amount, econCcy) : '—'}
          <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
            (calculated output)
          </Typography>
        </Typography>
      </Stack>

      <Typography variant="subtitle2">Cost / PM bottom stack</Typography>
      <Stack spacing={0.5}>
        <Stack direction="row" alignItems="center" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Typography variant="body2">
            Controlled cost / PM bottom ({costCcy} / unit, effective):{' '}
            {fmtMoneyWithCcy(line.effective_controlled_cost_amount ?? null, costCcy)}
          </Typography>
          {provChip(prov['controlled_cost_amount'])}
        </Stack>
        {line.override_controlled_cost_amount != null ? (
          <Typography variant="caption" color="text.secondary">
            Line override controlled cost is set — overrides SKU assumption for this line.
          </Typography>
        ) : null}
        <Alert severity="info" sx={{ py: 0.25 }}>
          <Typography variant="caption">
            Logistics, duties, freight, and true landed / loaded cost are <strong>not modeled</strong> in this version
            (deferred). Do not treat controlled cost as full landed cost.
          </Typography>
        </Alert>
        <Stack direction="row" alignItems="center" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Typography variant="body2">
            Reserve total % (effective): {fmtMarginPct(line.effective_reserve_total_pct ?? null)}
          </Typography>
          {provChip(prov['reserve_total_pct'])}
        </Stack>
        <Stack direction="row" alignItems="center" spacing={0.75} flexWrap="wrap" useFlexGap>
          <Typography variant="body2">
            Campaign / support reserve split (effective): {fmtMarginPct(line.effective_promo_reserve_split_pct ?? null)}
          </Typography>
          {provChip(prov['promo_reserve_split_pct'])}
        </Stack>
        <Typography variant="body2">
          Campaign support reserve ({econCcy}): {line.calc_campaign_support_reserve_amount ?? '—'}
        </Typography>
        <Typography variant="body2">
          Non-campaign reserve ({econCcy}): {line.calc_non_campaign_reserve_amount ?? '—'}
        </Typography>
        <Typography variant="body2">
          Estimated internal GP ({econCcy}, total, after reserves):{' '}
          {line.calc_internal_gp_amount != null ? fmtMoneyWithCcy(line.calc_internal_gp_amount, econCcy) : '—'}
        </Typography>
      </Stack>

      {dapEvidenceLocal != null ? (
        <>
          <Divider />
          <Typography variant="subtitle2">Sell-in evidence (not cost)</Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            DAP / lineup evidence: {fmtCurrency(dapEvidenceLocal)} {planCurrencyCode} — reference only; not PM bottom or
            controlled cost.
          </Typography>
        </>
      ) : null}
    </Stack>
  );
}
