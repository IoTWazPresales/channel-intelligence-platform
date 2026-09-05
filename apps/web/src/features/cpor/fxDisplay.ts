/** FX display honesty helpers — NS-1a (no silent conversion). */

export type SettleReadiness = {
  fx_declared: boolean;
  roe_snapshot: number | null;
  fx_mode?: string | null;
  fx_mode_declared?: boolean;
  fx_settle_allowed?: boolean;
  fx_basis_line?: string | null;
  open_assumption_count: number;
  claim_evidence_count: number;
  evidence_basis?: 'claim_evidenced' | 'source_attested' | 'none' | null;
};

export type FxMoneyDisplay = {
  localLabel: string;
  localAmount: string;
  usdBasisLine: string | null;
  fxUndeclared: boolean;
};

const moneyFmt = new Intl.NumberFormat(undefined, {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function isFxDeclared(
  roeSnapshot: number | null | undefined,
  missingRoe?: boolean,
): boolean {
  if (missingRoe) return false;
  return roeSnapshot != null && roeSnapshot > 0;
}

export function formatLocalMoney(
  amount: number | null | undefined,
  currencyCode: string | null | undefined,
): string {
  if (amount == null || Number.isNaN(amount)) return '—';
  const ccy = (currencyCode || 'ZAR').toUpperCase();
  const formatted = moneyFmt.format(amount);
  if (ccy === 'ZAR') return `R ${formatted}`;
  if (ccy === 'USD') return `$ ${formatted}`;
  return `${ccy} ${formatted}`;
}

export function formatUsdMoney(amount: number | null | undefined): string {
  if (amount == null || Number.isNaN(amount)) return '—';
  return `$ ${moneyFmt.format(amount)}`;
}

export function buildUsdBasisLine(
  roeSnapshot: number | null | undefined,
  usdAmount: number | null | undefined,
  missingRoe?: boolean,
): string | null {
  if (!isFxDeclared(roeSnapshot, missingRoe)) return null;
  if (usdAmount == null || Number.isNaN(usdAmount)) return null;
  const roe = Number(roeSnapshot).toFixed(2);
  return `USD ${moneyFmt.format(usdAmount)} at declared case rate ZAR ${roe}`;
}

export function buildFxMoneyDisplay(input: {
  currencyCode?: string | null;
  roeSnapshot?: number | null;
  missingRoe?: boolean;
  localAmount?: number | null;
  usdAmount?: number | null;
  localLabel?: string;
}): FxMoneyDisplay {
  const currencyCode = input.currencyCode ?? 'ZAR';
  const fxUndeclared = !isFxDeclared(input.roeSnapshot, input.missingRoe);
  return {
    localLabel: input.localLabel ?? 'Case support',
    localAmount: formatLocalMoney(input.localAmount, currencyCode),
    usdBasisLine: buildUsdBasisLine(input.roeSnapshot, input.usdAmount, input.missingRoe),
    fxUndeclared,
  };
}

export type ReadinessChip = {
  key: 'fx' | 'assumptions' | 'evidence';
  tone: 'pass' | 'open' | 'fail';
  label: string;
};

export function buildSettleReadinessChips(readiness: SettleReadiness): ReadinessChip[] {
  const fxChip: ReadinessChip = readiness.fx_declared
    ? {
        key: 'fx',
        tone: readiness.fx_settle_allowed === false ? 'open' : 'pass',
        label:
          readiness.fx_basis_line ??
          `FX declared · ${readiness.roe_snapshot?.toFixed(2) ?? '—'}${readiness.fx_mode ? ` · ${readiness.fx_mode}` : ''}`,
      }
    : { key: 'fx', tone: 'fail', label: 'FX undeclared' };

  const assumptionCount = readiness.open_assumption_count;
  const assumptionsChip: ReadinessChip =
    assumptionCount === 0
      ? { key: 'assumptions', tone: 'pass', label: 'Assumptions clear' }
      : {
          key: 'assumptions',
          tone: 'open',
          label: `${assumptionCount} assumption${assumptionCount === 1 ? '' : 's'} open`,
        };

  const evidenceCount = readiness.claim_evidence_count;
  const basis = readiness.evidence_basis;
  let evidenceChip: ReadinessChip;
  if (basis === 'claim_evidenced' || evidenceCount > 0) {
    evidenceChip = {
      key: 'evidence',
      tone: 'pass',
      label: `${evidenceCount} claim line${evidenceCount === 1 ? '' : 's'}`,
    };
  } else if (basis === 'source_attested') {
    evidenceChip = {
      key: 'evidence',
      tone: 'open',
      label: 'Source attested (closed/paid) — no claim files',
    };
  } else {
    evidenceChip = { key: 'evidence', tone: 'fail', label: 'No claim files · not source-attested' };
  }

  return [fxChip, assumptionsChip, evidenceChip];
}

export function formatGridMoney(
  amount: number | null | undefined,
  kind: 'local' | 'usd',
  ctx: {
    currencyCode?: string | null;
    roeSnapshot?: number | null;
    missingRoe?: boolean;
  },
): string {
  if (kind === 'usd' && !isFxDeclared(ctx.roeSnapshot, ctx.missingRoe)) {
    return 'FX undeclared';
  }
  if (amount == null || Number.isNaN(amount)) return '—';
  if (kind === 'usd') return formatUsdMoney(amount);
  return formatLocalMoney(amount, ctx.currencyCode);
}
