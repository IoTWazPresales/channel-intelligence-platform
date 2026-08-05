'use client';

import { Box, Button, Checkbox, Stack, Typography } from '@mui/material';
import { useMemo, type InputHTMLAttributes, type ReactNode } from 'react';

import {
  StewardDrawerChrome,
  StewardEntityTabsBar,
  StewardWorkspaceViewportShell,
} from '@/features/import-steward';

import type {
  ResolutionWorklistProps,
  WorkItemKey,
} from './resolutionWorklist.types';
import { selectAllEligibleKeys } from './selectionUtils';

/**
 * Presentation-only resolution worklist. Composes import-steward *layout*
 * primitives (viewport shell, drawer chrome, tab bar) — never the importJobId engine.
 */
export function ResolutionWorklist<TItem, TBucketId extends string = string>(
  props: ResolutionWorklistProps<TItem, TBucketId>,
) {
  const {
    items,
    getItemKey,
    getProtection,
    buckets,
    activeBucket,
    onBucketChange,
    groupBy,
    isGroupCollapsed,
    renderGroupHeader,
    renderRow,
    selection,
    actions,
    drawer,
    renderTargetPicker,
    renderFilters,
    renderToolbar,
    renderManualLinkSlot,
    renderProgress,
    emptyState,
    getCheckboxTestId,
    rootTestId = 'resolution-worklist',
    bordered = false,
  } = props;

  const checkboxTestId = (key: WorkItemKey) =>
    getCheckboxTestId?.(key) ?? `${rootTestId}-row-check-${key}`;

  const itemByKey = useMemo(() => {
    const m = new Map<WorkItemKey, TItem>();
    for (const item of items) m.set(getItemKey(item), item);
    return m;
  }, [items, getItemKey]);

  const activeItem =
    drawer?.activeKey != null ? itemByKey.get(drawer.activeKey) ?? null : null;

  const groups = useMemo(() => {
    if (!groupBy) return null;
    const map = new Map<string, TItem[]>();
    for (const item of items) {
      const g = groupBy(item);
      const list = map.get(g) ?? [];
      list.push(item);
      map.set(g, list);
    }
    return map;
  }, [items, groupBy]);

  const tabDefs = useMemo(
    () =>
      (buckets ?? []).map((b) => ({
        id: b.id,
        label: b.label,
        testId: `${rootTestId}-bucket-${b.id}`,
      })),
    [buckets, rootTestId],
  );

  const tabCounts = useMemo(() => {
    const counts: Record<string, { total: number | null; needsWork: number | null }> = {};
    for (const b of buckets ?? []) {
      counts[b.id] = {
        total: b.count,
        needsWork: b.needsWorkCount ?? null,
      };
    }
    return counts as Record<TBucketId, { total: number | null; needsWork: number | null }>;
  }, [buckets]);

  const onSelectAllEligible = () => {
    const keys = selectAllEligibleKeys(items, getItemKey, getProtection);
    selection.onReplace(keys);
  };

  const left: ReactNode = (
    <Stack spacing={1.5} data-testid={`${rootTestId}-left-stack`} sx={{ flex: 1, minHeight: 0 }}>
      {buckets && buckets.length > 0 && activeBucket != null && onBucketChange ? (
        <StewardEntityTabsBar
          tabs={tabDefs}
          activeTab={activeBucket}
          onChange={(id) => onBucketChange(id as TBucketId)}
          counts={tabCounts}
          testIdPrefix={rootTestId}
          ariaLabel="Resolution worklist buckets"
          formatTabAriaLabel={(tab, total) =>
            `${tab.label}${total == null ? '' : ` (${total})`}`
          }
        />
      ) : null}

      {renderFilters?.()}
      {renderToolbar?.()}
      {renderManualLinkSlot?.()}

      <Stack direction="row" spacing={1} alignItems="center">
        <Button
          size="small"
          variant="outlined"
          onClick={onSelectAllEligible}
          data-testid={`${rootTestId}-select-all-eligible`}
        >
          Select all eligible
        </Button>
        <Button
          size="small"
          variant="text"
          onClick={() => selection.onReplace([])}
          data-testid={`${rootTestId}-clear-selection`}
        >
          Clear
        </Button>
        <Typography variant="caption" color="text.secondary">
          {selection.selected.size} selected
        </Typography>
      </Stack>

      <Box
        data-testid={`${rootTestId}-list`}
        sx={{ flex: 1, minHeight: 0, overflow: { md: 'auto' } }}
      >
        {items.length === 0
          ? (emptyState ?? (
              <Typography variant="body2" color="text.secondary">
                No items
              </Typography>
            ))
          : groups
            ? Array.from(groups.entries()).map(([groupKey, groupItems]) => (
                <Box key={groupKey} data-testid={`${rootTestId}-group-${groupKey}`} sx={{ mb: 2 }}>
                  {renderGroupHeader?.(groupKey, groupItems) ?? (
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      {groupKey}
                    </Typography>
                  )}
                  {!isGroupCollapsed?.(groupKey) ? (
                  <Stack spacing={0.5}>
                    {groupItems.map((item) => {
                      const key = getItemKey(item);
                      const selected = selection.selected.has(key);
                      return (
                        <Box
                          key={key}
                          data-testid={`${rootTestId}-row-${key}`}
                          sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}
                        >
                          <Checkbox
                            size="small"
                            checked={selected}
                            onChange={() => selection.onToggle(key)}
                            inputProps={
                              {
                                'aria-label': `Select ${key}`,
                                'data-testid': checkboxTestId(key),
                              } as InputHTMLAttributes<HTMLInputElement>
                            }
                          />
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            {renderRow(item, {
                              selected,
                              onToggleSelect: () => selection.onToggle(key),
                            })}
                          </Box>
                        </Box>
                      );
                    })}
                  </Stack>
                  ) : null}
                </Box>
              ))
            : (
              <Stack spacing={0.5}>
                {items.map((item) => {
                  const key = getItemKey(item);
                  const selected = selection.selected.has(key);
                  return (
                    <Box
                      key={key}
                      data-testid={`${rootTestId}-row-${key}`}
                      sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}
                    >
                      <Checkbox
                        size="small"
                        checked={selected}
                        onChange={() => selection.onToggle(key)}
                        inputProps={
                          {
                            'aria-label': `Select ${key}`,
                            'data-testid': checkboxTestId(key),
                          } as InputHTMLAttributes<HTMLInputElement>
                        }
                      />
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        {renderRow(item, {
                          selected,
                          onToggleSelect: () => selection.onToggle(key),
                        })}
                      </Box>
                    </Box>
                  );
                })}
              </Stack>
            )}
      </Box>
    </Stack>
  );

  const targetAction =
    activeItem != null
      ? (actions ?? []).find((a) => a.requiresTarget && typeof a.targets === 'function')
      : undefined;

  const drawerNode =
    drawer && activeItem != null ? (
      <StewardDrawerChrome
        title={drawer.title?.(activeItem) ?? 'Work item'}
        onClose={drawer.onClose}
        rootTestId={`${rootTestId}-drawer`}
        closeTestId={`${rootTestId}-drawer-close`}
        ariaLabel="Resolution worklist drawer"
      >
        <Stack spacing={1.5}>
          {drawer.renderEvidence(activeItem)}
          {drawer.renderSuggestions?.(activeItem)}
          {/* NON-PO-ONLY SEAM: target picker for promote/merge verbs */}
          {targetAction && renderTargetPicker
            ? renderTargetPicker({
                item: activeItem,
                action: targetAction,
                targets: targetAction.targets!(activeItem),
                onPick: () => {
                  /* Consumer owns picked-target state; slot only renders choices. */
                },
              })
            : null}
          {drawer.renderDispositionActions?.(activeItem)}
        </Stack>
      </StewardDrawerChrome>
    ) : null;

  return (
    <Box data-testid={rootTestId}>
      <StewardWorkspaceViewportShell
        rootTestId={`${rootTestId}-shell`}
        left={left}
        drawer={drawerNode}
        bordered={bordered}
      />
      {/* Progress slot — consumer supplies renderer; worklist does not own apply state. */}
      {renderProgress ? (
        <Box data-testid={`${rootTestId}-progress-slot`} sx={{ mt: 1 }} />
      ) : null}
    </Box>
  );
}
