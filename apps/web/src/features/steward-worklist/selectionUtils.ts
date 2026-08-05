/**
 * Unit 2 bulk-selection helpers for ResolutionWorklist.
 * Semantics match evaluate_case_bulk_protection / BulkProtection:
 * - selectionProtected (reasons OR contested) → excluded from select-all
 * - requiresOverride (reasons only; contested alone does NOT) → excluded from bulk apply
 * - contested-only → individually selectable / linkable (FLAG≠BLOCK)
 */
import type { WorkItemKey, WorkItemProtection } from './resolutionWorklist.types';

export function selectAllEligibleKeys<TItem>(
  items: TItem[],
  getItemKey: (item: TItem) => WorkItemKey,
  getProtection?: (item: TItem) => WorkItemProtection | null,
): WorkItemKey[] {
  return items
    .filter((item) => {
      const p = getProtection?.(item);
      if (!p) return true;
      return !p.selectionProtected;
    })
    .map(getItemKey);
}

export type BulkPartition<TItem> = {
  eligible: TItem[];
  skippedProtected: TItem[];
};

/** Drop requiresOverride from bulk apply; contested-only stays eligible. */
export function partitionBulkApply<TItem>(
  items: TItem[],
  getProtection?: (item: TItem) => WorkItemProtection | null,
): BulkPartition<TItem> {
  const eligible: TItem[] = [];
  const skippedProtected: TItem[] = [];
  for (const item of items) {
    const p = getProtection?.(item);
    if (p?.requiresOverride) {
      skippedProtected.push(item);
    } else {
      eligible.push(item);
    }
  }
  return { eligible, skippedProtected };
}

/**
 * S9 apply-all-ready: true when selection has ≥1 item after Unit-2 bulk partition.
 * Contested-only counts as ready; requiresOverride does not.
 */
export function isApplyAllReady<TItem>(
  selectedItems: TItem[],
  getProtection?: (item: TItem) => WorkItemProtection | null,
): boolean {
  return partitionBulkApply(selectedItems, getProtection).eligible.length > 0;
}
