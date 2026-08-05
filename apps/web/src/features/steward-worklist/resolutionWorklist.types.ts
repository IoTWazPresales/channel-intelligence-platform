/**
 * ResolutionWorklist presentation contract (Unit 5a / D-036).
 *
 * Presentation-only — opaque consumer-supplied identity. Does NOT reference
 * importJobId, proposal_key, or case_id in generic types.
 *
 * Designed against the Phase-0 seam table (9 consumers), not PO alone.
 * Seams that exist ONLY for non-PO consumers are marked below.
 */
import type { ReactNode } from 'react';

/** Opaque, consumer-supplied. Component never parses it. */
export type WorkItemKey = string;

/**
 * Unit 2 protection, generalized off lineup BulkProtection.
 * contested alone ⇒ selectionProtected but NOT requiresOverride (FLAG≠BLOCK).
 */
export type WorkItemProtection = {
  selectionProtected: boolean;
  requiresOverride: boolean;
  contested: boolean;
  reasonLabels: string[];
};

export type ResolutionBucket<TBucketId extends string = string> = {
  id: TBucketId;
  label: string;
  count: number;
  needsWorkCount?: number;
  /** Optional filter; when omitted, consumer filters before passing items. */
  predicate?: (item: unknown) => boolean;
};

/**
 * NON-PO-ONLY SEAM: destination entity the steward must pick before the verb runs.
 * Used by promote (TMP → permanent code / survivor) and merge (choose survivor).
 * PO link/dismiss never supplies a target — the proposed pair is already complete.
 */
export type ResolutionTargetSelection = {
  /** Opaque target id (customer_id, distributor_id, survivor_id, permanent code, …). */
  targetKey: WorkItemKey;
  label: string;
  meta?: Record<string, string | number | boolean | null>;
};

/**
 * Disposition verb. Link/Dismiss are PO-shaped; Promote/Merge require targetSelection.
 * NON-PO-ONLY SEAM: `requiresTarget` + `targets` — promote/merge carry a verb PO does not use.
 */
export type WorklistAction<TItem> = {
  id: string;
  label: string;
  /** When true, steward must pick a destination before apply (promote/merge). */
  requiresTarget?: boolean;
  /**
   * NON-PO-ONLY: candidate destinations for this item.
   * PO actions omit this; merge/promote always populate it when requiresTarget.
   */
  targets?: (item: TItem) => ResolutionTargetSelection[];
  /** Optional preview step before confirm (promote confirm:false→true). */
  previewFirst?: boolean;
  /** Bulk-capable? Contested/protected filtering still applies via getProtection. */
  allowBulk?: boolean;
  onRun: (args: {
    items: TItem[];
    /** Present when requiresTarget; undefined for PO-style accept/reject. */
    target?: ResolutionTargetSelection;
  }) => void | Promise<void>;
};

export type ResolutionApplyProgress = {
  itemsDone: number;
  itemsTotal: number;
  batchIndex: number;
  batchTotal: number;
};

export type ResolutionApplyItemResult = {
  key: WorkItemKey;
  status: 'applied' | 'already_done' | 'skipped_protected' | 'error';
  message?: string;
};

export type ResolutionApplyResult = {
  results: ResolutionApplyItemResult[];
  applied: number;
  alreadyDone: number;
  skippedProtected: number;
  errors: number;
};

/** Sync apply adapter (PO pilot, promote). Chunking is the adapter's concern. */
export type ResolutionSyncApplyAdapter<TItem> = {
  mode: 'sync';
  chunkSize?: number;
  applyItems: (
    items: TItem[],
    opts?: {
      onProgress?: (p: ResolutionApplyProgress) => void;
      signal?: AbortSignal;
      /** NON-PO-ONLY: destination for promote/merge bulk apply. */
      target?: ResolutionTargetSelection;
    },
  ) => Promise<ResolutionApplyResult>;
};

/**
 * NON-PO-ONLY SEAM: async adapter SLOT for consumers like distributor-merge (Celery).
 * Contract type only — unimplemented for PO (S10 waived). Do not build task-slot substrate.
 */
export type ResolutionAsyncApplyAdapter<TItem> = {
  mode: 'async';
  dispatch: (
    items: TItem[],
    opts?: { target?: ResolutionTargetSelection },
  ) => Promise<{ async: true; taskId: string }>;
  pollTask: (taskId: string) => Promise<{
    status: 'pending' | 'running' | 'success' | 'failed';
    progress?: ResolutionApplyProgress;
    result?: ResolutionApplyResult;
    error?: string;
  }>;
};

export type ResolutionApplyAdapter<TItem> =
  | ResolutionSyncApplyAdapter<TItem>
  | ResolutionAsyncApplyAdapter<TItem>;

export type ResolutionAuditEvent = {
  action: string;
  itemKeys: WorkItemKey[];
  targetKey?: WorkItemKey;
  payload?: Record<string, unknown>;
};

export type ResolutionWorklistSelectionApi = {
  selected: ReadonlySet<WorkItemKey>;
  onToggle: (key: WorkItemKey) => void;
  onReplace: (keys: WorkItemKey[]) => void;
};

export type ResolutionWorklistProps<TItem, TBucketId extends string = string> = {
  items: TItem[];
  getItemKey: (item: TItem) => WorkItemKey;
  getProtection?: (item: TItem) => WorkItemProtection | null;

  buckets?: ResolutionBucket<TBucketId>[];
  activeBucket?: TBucketId;
  onBucketChange?: (id: TBucketId) => void;

  groupBy?: (item: TItem) => string;
  /** When true, group rows are hidden but renderGroupHeader still renders (PO card collapse). */
  isGroupCollapsed?: (groupKey: string) => boolean;
  renderGroupHeader?: (groupKey: string, items: TItem[]) => ReactNode;
  renderRow: (
    item: TItem,
    api: { selected: boolean; onToggleSelect: () => void },
  ) => ReactNode;

  selection: ResolutionWorklistSelectionApi;

  /** Per-item + bulk disposition verbs (Link/Dismiss AND Promote/Merge+target). */
  actions?: WorklistAction<TItem>[];
  bulkActions?: WorklistAction<TItem>[];

  /**
   * NON-PO-ONLY SEAM: render a target picker when an action.requiresTarget.
   * PO never mounts this; promote/merge fixtures must.
   */
  renderTargetPicker?: (args: {
    item: TItem;
    action: WorklistAction<TItem>;
    targets: ResolutionTargetSelection[];
    onPick: (target: ResolutionTargetSelection) => void;
  }) => ReactNode;

  drawer?: {
    activeKey: WorkItemKey | null;
    onClose: () => void;
    title?: (item: TItem) => ReactNode;
    renderEvidence: (item: TItem) => ReactNode;
    renderDispositionActions?: (item: TItem) => ReactNode;
    /** S7 slot — ranked suggestions; PO fills in 5b. */
    renderSuggestions?: (item: TItem) => ReactNode;
  };

  /**
   * S7 slot — exact-match manual link when no proposal exists.
   * NEVER auto-create. Built into the component; PO wires in 5b.
   */
  onManualLink?: (query: string) => void | Promise<void>;
  renderManualLinkSlot?: () => ReactNode;

  applyAdapter?: ResolutionApplyAdapter<TItem>;
  renderProgress?: (p: ResolutionApplyProgress) => ReactNode;
  onAudit?: (event: ResolutionAuditEvent) => void;

  /** Optional filter toolbar slot (S3 — consumer-owned). */
  renderFilters?: () => ReactNode;
  /** Optional toolbar / CTA row. */
  renderToolbar?: () => ReactNode;

  rootTestId?: string;
  /** Override default `${rootTestId}-row-check-${key}` checkbox test id. */
  getCheckboxTestId?: (key: WorkItemKey) => string;
  emptyState?: ReactNode;
  bordered?: boolean;
};

/**
 * Seams that exist ONLY because of non-PO consumers (VERIFY 5a must list these).
 * If this list is empty, the contract is PO-shaped — STOP.
 */
export const NON_PO_ONLY_CONTRACT_SEAMS = [
  'WorklistAction.requiresTarget',
  'WorklistAction.targets',
  'ResolutionTargetSelection',
  'ResolutionWorklistProps.renderTargetPicker',
  'ResolutionApplyAdapter async mode (ResolutionAsyncApplyAdapter)',
  'applyItems opts.target / dispatch opts.target',
] as const;
