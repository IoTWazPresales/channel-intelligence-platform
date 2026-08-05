/**
 * Promote/merge-shaped fixture — steward picks a DESTINATION entity.
 * STRUCTURALLY different from PO accept/reject: uses requiresTarget + targets +
 * renderTargetPicker. This is the non-PO seam Phase 0 requires.
 */
import type {
  ResolutionSyncApplyAdapter,
  ResolutionTargetSelection,
  WorkItemProtection,
  WorklistAction,
} from '../resolutionWorklist.types';

export type MergePromoteFixtureItem = {
  /** Opaque work-item key (similarity_key or tmp_code). */
  workKey: string;
  kind: 'merge' | 'promote';
  label: string;
  /** Candidate destinations the steward must choose among. */
  candidateTargets: ResolutionTargetSelection[];
  protection: WorkItemProtection | null;
};

export const MERGE_PROMOTE_FIXTURE_ITEMS: MergePromoteFixtureItem[] = [
  {
    workKey: 'sim:acme-dist-group',
    kind: 'merge',
    label: 'ACME Dist / Acme Distribution / ACME DIST PTY',
    candidateTargets: [
      { targetKey: 'dist:101', label: 'ACME Dist (id 101) — survivor A' },
      { targetKey: 'dist:204', label: 'Acme Distribution (id 204) — survivor B' },
      { targetKey: 'dist:308', label: 'ACME DIST PTY (id 308) — survivor C' },
    ],
    protection: null,
  },
  {
    workKey: 'tmp:TMP-CUST-0042',
    kind: 'promote',
    label: 'TMP-CUST-0042 → permanent code',
    candidateTargets: [
      { targetKey: 'code:CUST-ACZA-0042', label: 'Promote as CUST-ACZA-0042' },
      { targetKey: 'code:CUST-ACZA-0042B', label: 'Promote as CUST-ACZA-0042B (alt)' },
    ],
    protection: null,
  },
  {
    workKey: 'sim:nb-twin',
    kind: 'merge',
    label: 'NB Twin A / NB Twin B',
    candidateTargets: [
      { targetKey: 'dist:501', label: 'NB Twin A (id 501)' },
      { targetKey: 'dist:502', label: 'NB Twin B (id 502)' },
    ],
    protection: {
      selectionProtected: false,
      requiresOverride: false,
      contested: false,
      reasonLabels: [],
    },
  },
];

export function mergePromoteGetItemKey(item: MergePromoteFixtureItem): string {
  return item.workKey;
}

export function mergePromoteGetProtection(
  item: MergePromoteFixtureItem,
): WorkItemProtection | null {
  return item.protection;
}

/**
 * NON-PO verb: merge/promote with TARGET SELECTION.
 * PO Link action must never set requiresTarget.
 */
export function buildMergePromoteAction(
  onResolve: (items: MergePromoteFixtureItem[], target: ResolutionTargetSelection) => void,
): WorklistAction<MergePromoteFixtureItem> {
  return {
    id: 'merge_or_promote',
    label: 'Merge / Promote to target',
    requiresTarget: true,
    allowBulk: false,
    targets: (item) => item.candidateTargets,
    previewFirst: true,
    onRun: ({ items, target }) => {
      if (!target) {
        throw new Error('merge/promote requires a target selection');
      }
      onResolve(items, target);
    },
  };
}

export function buildMergePromoteSyncAdapter(
  resolved: Map<string, string>,
): ResolutionSyncApplyAdapter<MergePromoteFixtureItem> {
  return {
    mode: 'sync',
    chunkSize: 500,
    applyItems: async (items, opts) => {
      const target = opts?.target;
      if (!target) {
        return {
          results: items.map((i) => ({
            key: i.workKey,
            status: 'error' as const,
            message: 'target required',
          })),
          applied: 0,
          alreadyDone: 0,
          skippedProtected: 0,
          errors: items.length,
        };
      }
      const results = items.map((item) => {
        if (resolved.has(item.workKey)) {
          return { key: item.workKey, status: 'already_done' as const };
        }
        resolved.set(item.workKey, target.targetKey);
        return { key: item.workKey, status: 'applied' as const };
      });
      return {
        results,
        applied: results.filter((r) => r.status === 'applied').length,
        alreadyDone: results.filter((r) => r.status === 'already_done').length,
        skippedProtected: 0,
        errors: 0,
      };
    },
  };
}

/** Structural proof: merge/promote actions require targets; PO actions must not. */
export function fixtureShapesDiffer(
  poAction: WorklistAction<unknown>,
  mergeAction: WorklistAction<unknown>,
): boolean {
  return (
    mergeAction.requiresTarget === true &&
    typeof mergeAction.targets === 'function' &&
    poAction.requiresTarget !== true &&
    poAction.targets == null
  );
}
