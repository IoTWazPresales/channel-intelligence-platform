'use client';

import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';

import { apiPost } from '@/lib/api';

import { registerClientBackgroundTask, finishClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';

import type {
  StewardBulkApplyResponse,
  StewardBulkAsyncEnqueueResponse,
  StewardBulkPreviewResponse,
  StewardEngineCandidateRow,
  StewardEngineConfig,
} from './stewardEngine.types';

export function useStewardBulkSteward({
  importJobId,
  selectedIds,
  setSelectedIds,
  setBulkMode,
  onInvalidate,
  onBulkClosed,
  onApplyPlanFallback,
  applySuggestedRegion,
  onPlanRefresh,
  onEvictResolvedCandidates,
  onShrinkPlanScope,
  config,
}: {
  importJobId: number;
  selectedIds: number[];
  setSelectedIds: (ids: number[] | ((prev: number[]) => number[])) => void;
  setBulkMode: (mode: BulkTableSelectionMode) => void;
  onInvalidate: () => void;
  onBulkClosed?: () => void;
  onApplyPlanFallback?: (args: {
    action: 'set_plan_fallback_region' | 'set_plan_fallback_channel';
    regionId: string;
    channelId: string;
  }) => Promise<void>;
  applySuggestedRegion?: (args: { candidateIds: number[] }) => Promise<void>;
  onPlanRefresh?: () => void | Promise<unknown>;
  onEvictResolvedCandidates?: (candidateIds: number[]) => void;
  onShrinkPlanScope?: (candidateIds: number[]) => void;
  config: StewardEngineConfig;
}) {
  const qc = useQueryClient();

  const [bulkAction, setBulkAction] = useState<string>('ignore');
  const [bulkNotes, setBulkNotes] = useState('');
  const [bulkCustomerId, setBulkCustomerId] = useState('');
  const [bulkDistributorId, setBulkDistributorId] = useState('');
  const [bulkProductId, setBulkProductId] = useState('');
  const [bulkRawToken, setBulkRawToken] = useState('');
  const [bulkConfirmIneligible, setBulkConfirmIneligible] = useState(false);
  const [bulkAuditNote, setBulkAuditNote] = useState('');
  const [bulkRegionId, setBulkRegionId] = useState('');
  const [bulkChannelId, setBulkChannelId] = useState('');
  const [bulkPreferredDistributorId, setBulkPreferredDistributorId] = useState('');
  const [bulkPartnerTier, setBulkPartnerTier] = useState('unmanaged');
  const [bulkProvisionalNotes, setBulkProvisionalNotes] = useState('');
  const [bulkDistSuspiciousOk, setBulkDistSuspiciousOk] = useState(false);
  const [bulkProvisionalDistCode, setBulkProvisionalDistCode] = useState('');
  const [bulkApplySummary, setBulkApplySummary] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState<StewardBulkPreviewResponse | null>(null);
  const [previewApplyToken, setPreviewApplyToken] = useState<string | null>(null);

  const buildBulkBody = useCallback(() => {
    const ids = [...selectedIds];
    const base: Record<string, unknown> = {
      action: bulkAction,
      candidate_ids: ids,
    };
    if (bulkAction === 'ignore') {
      base.notes = bulkNotes.trim() || null;
    }
    if (bulkAction === 'map_customer') {
      base.customer_id = Number(bulkCustomerId);
      base.raw_token = bulkRawToken.trim() || null;
    }
    if (bulkAction === 'map_distributor') {
      base.distributor_id = Number(bulkDistributorId);
      base.raw_token = bulkRawToken.trim() || null;
    }
    if (bulkAction === 'resolve_product') {
      base.product_id = Number(bulkProductId);
      base.raw_token = bulkRawToken.trim() || null;
      base.confirm_ineligible_product = bulkConfirmIneligible;
      base.audit_note = bulkAuditNote.trim() || null;
    }
    if (bulkAction === 'create_provisional_customer') {
      const r = bulkRegionId.trim();
      const c = bulkChannelId.trim();
      base.region_id = r !== '' && Number.isFinite(Number(r)) ? Number(r) : null;
      base.channel_id = c !== '' && Number.isFinite(Number(c)) ? Number(c) : null;
      base.partner_tier = bulkPartnerTier.trim() || 'unmanaged';
      base.provisional_notes_summary = bulkProvisionalNotes.trim() || null;
      const pd = bulkPreferredDistributorId.trim();
      base.preferred_distributor_id = pd !== '' && Number.isFinite(Number(pd)) ? Number(pd) : null;
    }
    if (bulkAction === 'create_provisional_distributor') {
      base.confirm_for_suspicious_distributor_token = bulkDistSuspiciousOk;
      base.provisional_distributor_code = bulkProvisionalDistCode.trim() || null;
    }
    return base;
  }, [
    selectedIds,
    bulkAction,
    bulkNotes,
    bulkCustomerId,
    bulkDistributorId,
    bulkProductId,
    bulkRawToken,
    bulkConfirmIneligible,
    bulkAuditNote,
    bulkRegionId,
    bulkChannelId,
    bulkPreferredDistributorId,
    bulkPartnerTier,
    bulkProvisionalNotes,
    bulkDistSuspiciousOk,
    bulkProvisionalDistCode,
  ]);

  const previewToken = useMemo(() => JSON.stringify(buildBulkBody()), [buildBulkBody]);

  const bulkFormReady = useMemo(() => {
    if (bulkAction === 'ignore') return true;
    if (bulkAction === 'map_customer') {
      return bulkCustomerId.trim() !== '' && Number.isFinite(Number(bulkCustomerId));
    }
    if (bulkAction === 'map_distributor') {
      return bulkDistributorId.trim() !== '' && Number.isFinite(Number(bulkDistributorId));
    }
    if (bulkAction === 'resolve_product') {
      const pid = bulkProductId.trim();
      if (!pid || !Number.isFinite(Number(pid))) return false;
      if (bulkConfirmIneligible && bulkAuditNote.trim().length < 8) return false;
      return true;
    }
    if (bulkAction === 'create_provisional_customer') return true;
    if (bulkAction === 'create_provisional_distributor') return true;
    if (bulkAction === 'set_plan_fallback_region' || bulkAction === 'set_plan_fallback_channel') return true;
    if (bulkAction === 'apply_suggested_region') return selectedIds.length > 0;
    return false;
  }, [
    bulkAction,
    bulkCustomerId,
    bulkDistributorId,
    bulkProductId,
    bulkConfirmIneligible,
    bulkAuditNote,
    bulkRegionId,
    bulkChannelId,
  ]);

  const bulkPreview = useMutation({
    mutationFn: async () => {
      if (
        bulkAction === 'set_plan_fallback_region' ||
        bulkAction === 'set_plan_fallback_channel' ||
        bulkAction === 'apply_suggested_region'
      ) {
        return {
          import_job_id: importJobId,
          action: bulkAction,
          results: selectedIds.map((id) => ({ candidate_id: id })),
          totals: { plan_only: true },
        } satisfies StewardBulkPreviewResponse;
      }
      const body = buildBulkBody();
      const chunkSize = config.bulkChunkSize(bulkAction);
      const chunks = config.chunkBulkCandidateIds(selectedIds, chunkSize);
      const parts: StewardBulkPreviewResponse[] = [];
      for (const candidate_ids of chunks) {
        const part = await apiPost<StewardBulkPreviewResponse>(
          config.bulkPreviewPath(importJobId),
          { ...body, candidate_ids }
        );
        parts.push(part);
      }
      return config.mergeBulkPreviewResponses(importJobId, bulkAction, parts);
    },
    onSuccess: (data) => {
      setBulkApplySummary(null);
      setPreviewData(data);
      setPreviewApplyToken(previewToken);
      setPreviewOpen(true);
    },
  });

  const bulkApply = useMutation({
    mutationFn: async () => {
      if (bulkAction === 'apply_suggested_region' && applySuggestedRegion) {
        await applySuggestedRegion({ candidateIds: [...selectedIds] });
        return {
          import_job_id: importJobId,
          action: bulkAction,
          applied: selectedIds.length,
          failed: 0,
          results: [],
        } satisfies StewardBulkApplyResponse;
      }
      if (
        (bulkAction === 'set_plan_fallback_region' || bulkAction === 'set_plan_fallback_channel') &&
        onApplyPlanFallback
      ) {
        await onApplyPlanFallback({
          action: bulkAction,
          regionId: bulkRegionId,
          channelId: bulkChannelId,
        });
        return {
          import_job_id: importJobId,
          action: bulkAction,
          applied: 0,
          failed: 0,
          results: [],
        } satisfies StewardBulkApplyResponse;
      }
      const body = buildBulkBody();
      if (bulkAction === 'ignore') {
        let taskId: string | undefined;
        try {
          const enqueued = await apiPost<StewardBulkAsyncEnqueueResponse>(
            config.bulkIgnoreAsyncPath(importJobId),
            body
          );
          taskId = enqueued.task_id;
          registerClientBackgroundTask({
            taskId: enqueued.task_id,
            importJobId,
            kind: config.bulkIgnoreBackgroundKind as never,
            label: config.bulkIgnoreBackgroundLabel(importJobId),
          });
          void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
          return config.pollBulkProvisionalTask(importJobId, enqueued.task_id, {
            rowCount: selectedIds.length,
          });
        } finally {
          if (taskId) finishClientBackgroundTask(taskId);
          void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
        }
      }
      if (bulkAction === 'create_provisional_customer') {
        let taskId: string | undefined;
        try {
          const enqueued = await apiPost<StewardBulkAsyncEnqueueResponse>(
            config.bulkProvisionalCustomersAsyncPath(importJobId),
            body
          );
          taskId = enqueued.task_id;
          registerClientBackgroundTask({
            taskId: enqueued.task_id,
            importJobId,
            kind: config.bulkProvisionalBackgroundKind as never,
            label: config.bulkProvisionalBackgroundLabel(importJobId),
          });
          void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
          return config.pollBulkProvisionalTask(importJobId, enqueued.task_id, {
            rowCount: selectedIds.length,
          });
        } finally {
          if (taskId) finishClientBackgroundTask(taskId);
          void qc.invalidateQueries({ queryKey: ['background-tasks-active'] });
        }
      }
      const chunkSize = config.bulkChunkSize(bulkAction);
      const chunks = config.chunkBulkCandidateIds(selectedIds, chunkSize);
      const parts: StewardBulkApplyResponse[] = [];
      for (const candidate_ids of chunks) {
        const part = await apiPost<StewardBulkApplyResponse>(
          config.bulkApplyPath(importJobId),
          { ...body, candidate_ids }
        );
        parts.push(part);
      }
      return config.mergeBulkApplyResponses(importJobId, bulkAction, parts);
    },
    onMutate: async () => {
      if (
        bulkAction === 'create_provisional_customer' ||
        bulkAction === 'ignore' ||
        bulkAction === 'set_plan_fallback_region' ||
        bulkAction === 'set_plan_fallback_channel' ||
        bulkAction === 'apply_suggested_region'
      ) {
        return undefined;
      }
      const stewardAction = config.bulkActionToStewardAction(bulkAction);
      if (!stewardAction || selectedIds.length === 0) return undefined;
      const previous = config.optimisticallyApplyBulk(qc, importJobId, selectedIds, stewardAction);
      return { previous, stewardAction } satisfies {
        previous?: StewardEngineCandidateRow[];
        stewardAction: string;
      };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(config.candidatesQueryKey(importJobId), ctx.previous);
      }
    },
    onSuccess: (data) => {
      const appliedIds = (data.results || [])
        .filter((r) => r.ok === true && r.candidate_id != null)
        .map((r) => Number(r.candidate_id))
        .filter((id) => Number.isFinite(id));
      const planOnly =
        bulkAction === 'set_plan_fallback_region' ||
        bulkAction === 'set_plan_fallback_channel' ||
        bulkAction === 'apply_suggested_region';
      setBulkApplySummary(
        planOnly
          ? bulkAction === 'apply_suggested_region'
            ? 'Suggested region overrides applied to the plan — review effective geo, then Apply selected ready when ready.'
            : 'Plan fallback updated — refresh suggestions if the grid does not update automatically.'
          : `Bulk steward: applied ${data.applied}, failed ${data.failed}. Re-run import validation (server) when ready.`
      );
      setPreviewOpen(false);
      setPreviewData(null);
      setPreviewApplyToken(null);
      setBulkMode('normal');
      setSelectedIds([]);
      config.invalidateStewardQueries(qc, importJobId, { includeImportJobsList: true });
      onInvalidate();
      if (appliedIds.length > 0) {
        onShrinkPlanScope?.(appliedIds);
        if (bulkAction === 'ignore') {
          onEvictResolvedCandidates?.(appliedIds);
        }
      }
      if (
        !planOnly &&
        (bulkAction === 'ignore' ||
          bulkAction === 'map_customer' ||
          bulkAction === 'map_distributor' ||
          bulkAction === 'resolve_product')
      ) {
        void Promise.resolve(onPlanRefresh?.()).catch(() => {});
      }
      onBulkClosed?.();
    },
  });

  const applyReady = previewApplyToken !== null && previewApplyToken === previewToken && previewData !== null;

  return {
    bulkAction,
    setBulkAction,
    bulkNotes,
    setBulkNotes,
    bulkCustomerId,
    setBulkCustomerId,
    bulkDistributorId,
    setBulkDistributorId,
    bulkProductId,
    setBulkProductId,
    bulkRawToken,
    setBulkRawToken,
    bulkConfirmIneligible,
    setBulkConfirmIneligible,
    bulkAuditNote,
    setBulkAuditNote,
    bulkRegionId,
    setBulkRegionId,
    bulkChannelId,
    setBulkChannelId,
    bulkPreferredDistributorId,
    setBulkPreferredDistributorId,
    bulkPartnerTier,
    setBulkPartnerTier,
    bulkProvisionalNotes,
    setBulkProvisionalNotes,
    bulkDistSuspiciousOk,
    setBulkDistSuspiciousOk,
    bulkProvisionalDistCode,
    setBulkProvisionalDistCode,
    bulkApplySummary,
    setBulkApplySummary,
    previewOpen,
    setPreviewOpen,
    previewData,
    bulkPreview,
    bulkApply,
    bulkFormReady,
    applyReady,
  };
}
