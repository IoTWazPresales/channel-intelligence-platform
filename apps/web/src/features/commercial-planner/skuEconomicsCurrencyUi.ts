/** Common ISO codes for controlled-cost / PM-bottom currency pickers (not exhaustive). */
export const COMMON_SKU_COST_ISO_CODES = ['USD', 'ZAR', 'EUR', 'GBP', 'AED', 'CNY', 'JPY'] as const;

/** Select value when user enters a custom ISO code. */
export const SKU_COST_CURRENCY_OTHER = '__other__';

export function isCommonSkuCostIso(code: string): boolean {
  const u = (code || '').trim().toUpperCase();
  return (COMMON_SKU_COST_ISO_CODES as readonly string[]).includes(u);
}

/** Split stored DB currency into MUI Select value + optional "other" text field. */
export function splitCostCurrencyForSelect(stored: string | null | undefined): {
  selectValue: string;
  otherIso: string;
} {
  const u = (stored || 'USD').trim().toUpperCase();
  if (isCommonSkuCostIso(u)) return { selectValue: u, otherIso: '' };
  return { selectValue: SKU_COST_CURRENCY_OTHER, otherIso: u };
}

/** Resolved ISO code from select + other field. */
export function resolveCostCurrencyFromSelect(selectValue: string, otherIso: string): string {
  if (selectValue === SKU_COST_CURRENCY_OTHER) {
    return (otherIso || '').trim().toUpperCase().slice(0, 8);
  }
  return (selectValue || 'USD').trim().toUpperCase().slice(0, 8);
}

export type SkuEconomicsNumericValidation = {
  controlled_cost_amount: number;
  controlled_cost_currency_code: string;
  fx_plan_currency_per_cost_currency: number;
  vat_rate_pct: number;
  reserve_total_pct: number;
  promo_reserve_split_pct: number;
};

export function validateSkuEconomicsInputs(v: SkuEconomicsNumericValidation): string[] {
  const errs: string[] = [];
  if (!Number.isFinite(v.controlled_cost_amount) || v.controlled_cost_amount <= 0) {
    errs.push('Controlled cost amount must be a number greater than 0.');
  }
  const ccy = (v.controlled_cost_currency_code || '').trim().toUpperCase();
  if (ccy.length < 3 || ccy.length > 8) {
    errs.push('Controlled cost currency must be a 3–8 character ISO-style code (e.g. USD, ZAR).');
  }
  if (!Number.isFinite(v.fx_plan_currency_per_cost_currency) || v.fx_plan_currency_per_cost_currency <= 0) {
    errs.push('FX bridge must be a number greater than 0 (plan currency units per 1 controlled-cost currency).');
  }
  if (!Number.isFinite(v.vat_rate_pct) || v.vat_rate_pct < 0 || v.vat_rate_pct > 1) {
    errs.push('VAT rate must be between 0 and 1 (decimal fraction, e.g. 0.15 for 15%).');
  }
  if (!Number.isFinite(v.reserve_total_pct) || v.reserve_total_pct < 0 || v.reserve_total_pct > 1) {
    errs.push('Reserve total % must be between 0 and 1.');
  }
  if (!Number.isFinite(v.promo_reserve_split_pct) || v.promo_reserve_split_pct < 0 || v.promo_reserve_split_pct > 1) {
    errs.push('Campaign / support reserve split must be between 0 and 1.');
  }
  return errs;
}
