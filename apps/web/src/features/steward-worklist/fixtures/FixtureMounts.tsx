'use client';

/**
 * Fixture mounts proving two STRUCTURALLY DIFFERENT consumers.
 * Not a Storybook dependency — vitest renders these via renderToStaticMarkup.
 */
import { Button, Chip, Stack, Typography } from '@mui/material';
import { useMemo, useState } from 'react';

import { ResolutionWorklist } from '../ResolutionWorklist';
import type { ResolutionTargetSelection, WorkItemKey } from '../resolutionWorklist.types';
import {
  MERGE_PROMOTE_FIXTURE_ITEMS,
  buildMergePromoteAction,
  mergePromoteGetItemKey,
  mergePromoteGetProtection,
  type MergePromoteFixtureItem,
} from './mergePromoteFixture';
import {
  PO_FIXTURE_ITEMS,
  buildPoLinkAction,
  poGetItemKey,
  poGetProtection,
  type PoFixtureItem,
} from './poAutoLinkFixture';

export function PoWorklistFixtureMount() {
  const [selected, setSelected] = useState<Set<WorkItemKey>>(new Set());
  const [activeKey, setActiveKey] = useState<WorkItemKey | null>(null);
  const [bucket, setBucket] = useState<'all' | 'contested' | 'clean'>('all');

  const items = useMemo(() => {
    if (bucket === 'contested') {
      return PO_FIXTURE_ITEMS.filter((i) => i.protection?.contested);
    }
    if (bucket === 'clean') {
      return PO_FIXTURE_ITEMS.filter((i) => !i.protection?.contested);
    }
    return PO_FIXTURE_ITEMS;
  }, [bucket]);

  const linkAction = buildPoLinkAction(() => undefined);

  return (
    <ResolutionWorklist<PoFixtureItem, 'all' | 'contested' | 'clean'>
      rootTestId="po-fixture-worklist"
      items={items}
      getItemKey={poGetItemKey}
      getProtection={poGetProtection}
      buckets={[
        { id: 'all', label: 'All', count: PO_FIXTURE_ITEMS.length },
        {
          id: 'contested',
          label: 'Contested',
          count: PO_FIXTURE_ITEMS.filter((i) => i.protection?.contested).length,
        },
        {
          id: 'clean',
          label: 'Clean',
          count: PO_FIXTURE_ITEMS.filter((i) => !i.protection?.contested).length,
        },
      ]}
      activeBucket={bucket}
      onBucketChange={setBucket}
      selection={{
        selected,
        onToggle: (k) =>
          setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(k)) next.delete(k);
            else next.add(k);
            return next;
          }),
        onReplace: (ks) => setSelected(new Set(ks)),
      }}
      actions={[linkAction]}
      renderRow={(item) => (
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          onClick={() => setActiveKey(item.proposalKey)}
          sx={{ cursor: 'pointer' }}
        >
          <Typography variant="body2">{item.poNumber}</Typography>
          <Chip size="small" label={item.confidence} />
          {item.disposition ? (
            <Chip size="small" label={item.disposition} variant="outlined" />
          ) : null}
          {item.protection?.contested ? (
            <Chip size="small" color="warning" label="Contested" />
          ) : null}
        </Stack>
      )}
      drawer={{
        activeKey,
        onClose: () => setActiveKey(null),
        title: (item) => item.poNumber,
        renderEvidence: (item) => (
          <Typography variant="body2">
            Case {item.caseId} ↔ PO {item.purchaseOrderId} (proposed pair — no target pick)
          </Typography>
        ),
        renderDispositionActions: () => (
          <Button size="small" variant="contained" data-testid="po-fixture-link-btn">
            {linkAction.label}
          </Button>
        ),
      }}
    />
  );
}

/**
 * Merge/promote fixture — TARGET SELECTION is mandatory.
 * Default-opens first item so static markup includes the non-PO picker seam.
 */
export function MergePromoteWorklistFixtureMount() {
  const [selected, setSelected] = useState<Set<WorkItemKey>>(new Set());
  const [activeKey, setActiveKey] = useState<WorkItemKey | null>(
    MERGE_PROMOTE_FIXTURE_ITEMS[0]?.workKey ?? null,
  );
  const [picked, setPicked] = useState<ResolutionTargetSelection | null>(null);

  const mergeAction = buildMergePromoteAction(() => undefined);

  return (
    <ResolutionWorklist<MergePromoteFixtureItem>
      rootTestId="merge-promote-fixture-worklist"
      items={MERGE_PROMOTE_FIXTURE_ITEMS}
      getItemKey={mergePromoteGetItemKey}
      getProtection={mergePromoteGetProtection}
      selection={{
        selected,
        onToggle: (k) =>
          setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(k)) next.delete(k);
            else next.add(k);
            return next;
          }),
        onReplace: (ks) => setSelected(new Set(ks)),
      }}
      actions={[mergeAction]}
      renderTargetPicker={({ targets, onPick }) => (
        <Stack spacing={1} data-testid="merge-promote-target-picker">
          <Typography variant="subtitle2">
            Pick destination — steward chooses survivor / permanent code (verb PO does not use)
          </Typography>
          {targets.map((t) => (
            <Button
              key={t.targetKey}
              size="small"
              variant={picked?.targetKey === t.targetKey ? 'contained' : 'outlined'}
              onClick={() => {
                setPicked(t);
                onPick(t);
              }}
              data-testid={`merge-promote-target-${t.targetKey}`}
            >
              {t.label}
            </Button>
          ))}
        </Stack>
      )}
      renderRow={(item) => (
        <Stack
          direction="row"
          spacing={1}
          alignItems="center"
          onClick={() => {
            setActiveKey(item.workKey);
            setPicked(null);
          }}
          sx={{ cursor: 'pointer' }}
        >
          <Chip
            size="small"
            label={item.kind}
            color={item.kind === 'merge' ? 'secondary' : 'primary'}
          />
          <Typography variant="body2">{item.label}</Typography>
          <Chip size="small" variant="outlined" label={`${item.candidateTargets.length} targets`} />
        </Stack>
      )}
      drawer={{
        activeKey,
        onClose: () => setActiveKey(null),
        title: (item) => item.label,
        renderEvidence: (item) => (
          <Typography variant="body2">
            {item.kind === 'merge'
              ? 'Merge group — choose which distributor survives'
              : 'Promote TMP — choose permanent code'}
          </Typography>
        ),
        renderDispositionActions: () => (
          <Button
            size="small"
            variant="contained"
            disabled={!picked}
            data-testid="merge-promote-confirm-btn"
          >
            {mergeAction.label}
            {picked ? ` → ${picked.label}` : ' (pick target first)'}
          </Button>
        ),
      }}
    />
  );
}
