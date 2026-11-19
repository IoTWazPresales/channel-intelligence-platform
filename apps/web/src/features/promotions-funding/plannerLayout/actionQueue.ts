export type QueueCase = {
  id: number;
  case_code: string;
  case_name?: string | null;
  customer_name?: string | null;
  status: string;
  window_start?: string | null;
  window_end?: string | null;
  needs_reapproval?: boolean;
  /** Set when another case replaced this one (soft supersede); a replaced case waits on nobody. */
  superseded_by_case_id?: number | null;
  settle_readiness?: { claim_evidence_count?: number | null } | null;
};

export type ActionKind = 'reapproval' | 'awaiting_approval' | 'claim_evidence_pending';

export type ActionItem = {
  key: string;
  kind: ActionKind;
  caseId: number;
  caseCode: string;
  label: string;
  hint: string;
  tone: 'warning' | 'info';
  /** Awaiting approval and the case window has already started (needs `today`). */
  overdue: boolean;
};

/**
 * One queue of cases that wait on a person. Same conditions the planner already used in "Needs a decision":
 * money-ceiling reapproval, proposed (awaiting approval), and ended with no claim file applied.
 * Each case appears at most once per condition; reapproval and proposed are not merged.
 */
export function buildActionQueue({
  cases,
  proposed,
  ended,
  today,
}: {
  cases: readonly QueueCase[];
  proposed: readonly QueueCase[];
  ended: readonly QueueCase[];
  /** Local calendar day (YYYY-MM-DD). Without it no approval is called overdue. */
  today?: string;
}): ActionItem[] {
  const current = <T extends QueueCase>(rows: readonly T[]) => rows.filter((r) => r.superseded_by_case_id == null);
  cases = current(cases);
  proposed = current(proposed);
  ended = current(ended);
  const items: ActionItem[] = [];
  const seenReapproval = new Set<number>();
  for (const p of [...cases, ...ended, ...proposed]) {
    if (!p.needs_reapproval || seenReapproval.has(p.id)) continue;
    seenReapproval.add(p.id);
    items.push({
      key: `reapproval-${p.id}`,
      kind: 'reapproval',
      caseId: p.id,
      caseCode: p.case_code,
      label: `${p.case_code} · reapproval required`,
      hint: 'Money-ceiling reapproval — not the same as Proposed, and not claim evidence.',
      tone: 'warning',
      overdue: false,
    });
  }
  const seenProposed = new Set<number>();
  for (const p of proposed) {
    if (seenProposed.has(p.id)) continue;
    seenProposed.add(p.id);
    // Overdue = still awaiting approval although the promotion window has started (a stated rule, no new data).
    const start = p.window_start ? String(p.window_start).slice(0, 10) : null;
    const overdue = Boolean(today && start && start < today);
    items.push({
      key: `awaiting-${p.id}`,
      kind: 'awaiting_approval',
      caseId: p.id,
      caseCode: p.case_code,
      label: `${p.case_code} · awaiting approval${overdue ? ' · overdue' : ''}`,
      hint: overdue
        ? `The window started ${start}: approve or reject it now.`
        : 'In Proposed: review the lines, then approve or reject.',
      tone: 'warning',
      overdue,
    });
  }
  const seenEnded = new Set<number>();
  for (const p of ended) {
    if ((p.settle_readiness?.claim_evidence_count ?? 0) !== 0 || seenEnded.has(p.id)) continue;
    seenEnded.add(p.id);
    items.push({
      key: `claim-${p.id}`,
      kind: 'claim_evidence_pending',
      caseId: p.id,
      caseCode: p.case_code,
      label: `${p.case_code} · claim evidence pending`,
      hint: 'The window ended and no claim file is applied.',
      tone: 'info',
      overdue: false,
    });
  }
  return items;
}

export type QueueSummary = {
  total: number;
  reapproval: number;
  awaitingApproval: number;
  /** Subset of `awaitingApproval` whose window has already started. */
  overdueApprovals: number;
  evidenceOutstanding: number;
};

/** Counts of the queue by kind, for the queue cards. */
export function queueSummary(items: readonly ActionItem[]): QueueSummary {
  return {
    total: items.length,
    reapproval: items.filter((i) => i.kind === 'reapproval').length,
    awaitingApproval: items.filter((i) => i.kind === 'awaiting_approval').length,
    overdueApprovals: items.filter((i) => i.overdue).length,
    evidenceOutstanding: items.filter((i) => i.kind === 'claim_evidence_pending').length,
  };
}
