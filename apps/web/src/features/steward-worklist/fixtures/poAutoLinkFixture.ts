/**
 * PO-shaped fixture — accept/link a proposed (case, PO) pair.
 * Does NOT use requiresTarget / renderTargetPicker.
 */
import type {
  ResolutionSyncApplyAdapter,
  WorkItemProtection,
  WorklistAction,
} from '../resolutionWorklist.types';

export type PoFixtureItem = {
  proposalKey: string;
  caseId: number;
  purchaseOrderId: number;
  poNumber: string;
  confidence: 'high' | 'medium';
  disposition?: string;
  protection: WorkItemProtection | null;
};

export const PO_FIXTURE_ITEMS: PoFixtureItem[] = [
  {
    proposalKey: '90:12:PURMIDR25005866',
    caseId: 90,
    purchaseOrderId: 16355,
    poNumber: 'PURMIDR25005866',
    confidence: 'high',
    disposition: 'w3_tie_open_question',
    protection: {
      selectionProtected: true,
      requiresOverride: true,
      contested: true,
      reasonLabels: ['status po_issued', 'has 23 PO link(s)', 'contested PO'],
    },
  },
  {
    proposalKey: '125:0:957090',
    caseId: 125,
    purchaseOrderId: 14602,
    poNumber: '957090',
    confidence: 'high',
    disposition: 'w1_cross_period_slip',
    protection: {
      selectionProtected: true,
      requiresOverride: true,
      contested: false,
      reasonLabels: ['status po_pending', 'has 12 PO link(s)'],
    },
  },
  {
    proposalKey: '118:47:US-E3237-IC',
    caseId: 118,
    purchaseOrderId: 14420,
    poNumber: 'US-E3237-IC',
    confidence: 'medium',
    disposition: 'leave_live_annotate',
    protection: {
      selectionProtected: true,
      requiresOverride: false,
      contested: true,
      reasonLabels: ['contested PO'],
    },
  },
  {
    proposalKey: '120:12:CLEAN-HIGH-001',
    caseId: 120,
    purchaseOrderId: 99901,
    poNumber: 'CLEAN-HIGH-001',
    confidence: 'high',
    disposition: undefined,
    protection: null,
  },
];

export function poGetItemKey(item: PoFixtureItem): string {
  return item.proposalKey;
}

export function poGetProtection(item: PoFixtureItem): WorkItemProtection | null {
  return item.protection;
}

export function buildPoLinkAction(
  onLink: (items: PoFixtureItem[]) => void,
): WorklistAction<PoFixtureItem> {
  return {
    id: 'link',
    label: 'Link PO to case',
    allowBulk: true,
    // PO does NOT set requiresTarget — pair is already proposed
    onRun: ({ items }) => onLink(items),
  };
}

export function buildPoSyncAdapter(
  linked: Set<string>,
): ResolutionSyncApplyAdapter<PoFixtureItem> {
  return {
    mode: 'sync',
    chunkSize: 100,
    applyItems: async (items) => {
      const results = items.map((item) => {
        const key = `${item.caseId}:${item.purchaseOrderId}`;
        if (linked.has(key)) {
          return { key: item.proposalKey, status: 'already_done' as const };
        }
        if (item.protection?.requiresOverride) {
          return { key: item.proposalKey, status: 'skipped_protected' as const };
        }
        linked.add(key);
        return { key: item.proposalKey, status: 'applied' as const };
      });
      return {
        results,
        applied: results.filter((r) => r.status === 'applied').length,
        alreadyDone: results.filter((r) => r.status === 'already_done').length,
        skippedProtected: results.filter((r) => r.status === 'skipped_protected').length,
        errors: 0,
      };
    },
  };
}
