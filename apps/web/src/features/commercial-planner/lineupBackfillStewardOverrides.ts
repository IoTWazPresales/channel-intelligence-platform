export type StewardOverrideEntry = {
  period_label?: string;
  business_unit?: string;
};

export type StewardOverrides = Record<string, StewardOverrideEntry>;

export type AutoBaselineEntry = {
  period: string | null;
  business_unit: string | null;
};

export type AutoBaseline = Record<string, AutoBaselineEntry>;

export type ProposalLike = {
  proposal_key: string;
  period_label: string | null;
  business_unit: string | null;
};

/** Snapshot auto-detected period/BU on first preview — anchor for cumulative overrides. */
export function buildAutoBaseline(proposals: ProposalLike[]): AutoBaseline {
  const out: AutoBaseline = {};
  for (const p of proposals) {
    out[p.proposal_key] = {
      period: p.period_label,
      business_unit: p.business_unit,
    };
  }
  return out;
}

/**
 * Full override map for API: every row whose UI value differs from first-preview auto baseline.
 * Re-send on every re-run so earlier fixes are not dropped.
 */
export function buildCumulativeStewardPayload(
  proposals: ProposalLike[],
  periodOverrides: Record<string, string>,
  buOverrides: Record<string, string>,
  autoBaseline: AutoBaseline,
): StewardOverrides {
  const out: StewardOverrides = {};
  for (const p of proposals) {
    const pk = p.proposal_key;
    const base = autoBaseline[pk] ?? {
      period: p.period_label,
      business_unit: p.business_unit,
    };
    const period = (periodOverrides[pk] ?? p.period_label ?? '').trim();
    const bu = (buOverrides[pk] ?? p.business_unit ?? '').trim().toUpperCase();
    const entry: StewardOverrideEntry = {};
    if (period && period !== (base.period ?? '').trim()) {
      entry.period_label = period;
    }
    if (bu && bu !== (base.business_unit ?? '').toUpperCase()) {
      entry.business_unit = bu;
    }
    if (Object.keys(entry).length) {
      out[pk] = entry;
    }
  }
  return out;
}

/** Edits not yet applied via re-run (UI vs current preview response). */
export function collectPendingStewardDeltas(
  proposals: ProposalLike[],
  periodOverrides: Record<string, string>,
  buOverrides: Record<string, string>,
): StewardOverrides {
  const out: StewardOverrides = {};
  for (const p of proposals) {
    const pk = p.proposal_key;
    const period = periodOverrides[pk]?.trim();
    const bu = buOverrides[pk]?.trim();
    const entry: StewardOverrideEntry = {};
    if (period && period !== (p.period_label ?? '').trim()) {
      entry.period_label = period;
    }
    if (bu && bu.toUpperCase() !== (p.business_unit ?? '').toUpperCase()) {
      entry.business_unit = bu.toUpperCase();
    }
    if (Object.keys(entry).length) {
      out[pk] = entry;
    }
  }
  return out;
}

export function hasPendingStewardDeltas(
  proposals: ProposalLike[],
  periodOverrides: Record<string, string>,
  buOverrides: Record<string, string>,
): boolean {
  return Object.keys(collectPendingStewardDeltas(proposals, periodOverrides, buOverrides)).length > 0;
}

export function displayFieldsFromPreview(
  proposals: ProposalLike[],
  cumulativePayload: StewardOverrides,
): { periodOverrides: Record<string, string>; buOverrides: Record<string, string> } {
  const periodOverrides: Record<string, string> = {};
  const buOverrides: Record<string, string> = {};
  for (const p of proposals) {
    const steward = cumulativePayload[p.proposal_key];
    periodOverrides[p.proposal_key] = steward?.period_label ?? p.period_label ?? '';
    buOverrides[p.proposal_key] = steward?.business_unit ?? p.business_unit ?? '';
  }
  return { periodOverrides, buOverrides };
}

export function mergeCollisionWinners(
  collisions: Array<{ supersession_group_key: string; winner_proposal_key: string }>,
  previous: Record<string, string>,
): Record<string, string> {
  const defaults: Record<string, string> = {};
  for (const g of collisions) {
    defaults[g.supersession_group_key] = g.winner_proposal_key;
  }
  return { ...defaults, ...previous };
}
