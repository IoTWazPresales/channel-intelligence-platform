'use client';

import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';

import { apiPost } from '@/lib/api';
import { registerClientBackgroundTask, finishClientBackgroundTask } from '@/features/background-tasks/backgroundTaskRegistry';

import { pollShipmentBulkTask } from './shipmentBulkTaskPoll';
import { invalidateShipmentImportJobStewardQueries } from './shipmentSteward.config';

export type ShipmentBulkAction =
  | 'map_customer'
  | 'create_provisional_customer'
  | 'map_distributor'
  | 'create_provisional_distributor'
  | 'ignore';

export function useShipmentBulkSteward({
  importJobId,
  selectedIds,
  setSelectedIds,
  setBulkMode,
  onInvalidate,
  onBulkClosed,
}: {
  importJobId: number;
  selectedIds: number[];
  setSelectedIds: (ids: number[] | ((prev: number[]) => number[])) => void;
  setBulkMode: (mode: BulkTableSelectionMode) => void;
  onInvalidate: () => void;
  onBulkClosed?: () => void;
}) {
  const qc = useQueryClient();
  const [bulkAction, setBulkAction] = useState<ShipmentBulkAction>('map_customer');
  const [bulkCustomerId, setBulkCustomerId] = useState('');
  const [bulkDistributorId, setBulkDistributorId] = useState('');
  const [bulkProvNamesById, setBulkProvNamesById] = useState<Record<number, string>>({});
  const [bulkApplySummary, setBulkApplySummary] = useState<string | null>(null);

  const bulkFormReady = useMemo(() => {
    if (selectedIds.length === 0) return false;
    if (bulkAction === 'map_customer') {
      return bulkCustomerId.trim() !== '' && Number.isFinite(Number(bulkCustomerId));
    }
    if (bulkAction === 'map_distributor') {
      return bulkDistributorId.trim() !== '' && Number.isFinite(Number(bulkDistributorId));
    }
    if (bulkAction === 'create_provisional_customer') {
      return selectedIds.every((id) => (bulkProvNamesById[id] ?? '').trim().length > 0);
    }
    if (bulkAction === 'create_provisional_distributor') return true;
    if (bulkAction === 'ignore') return true;
    return false;
  }, [bulkAction, bulkCustomerId, bulkDistributorId, bulkProvNamesById, selectedIds]);

  const bulkApply = useMutation({
    mutationFn: async () => {
      if (bulkAction === 'map_customer') {
        const enq = await apiPost<{ import_job_id: number | null; task_id: string; async_poll: boolean }>(
          '/api/v1/shipment-evidence/import-candidates/bulk-map-customer',
          {
            import_job_id: importJobId,
            candidate_ids: selectedIds,
            customer_id: Number(bulkCustomerId),
          }
        );
        registerClientBackgroundTask({
          taskId: enq.task_id,
          importJobId,
          kind: 'shipment_bulk',
          label: 'Bulk map channel partners',
        });
        const out = await pollShipmentBulkTask<{ mapped: number[]; errors: { candidate_id: number; reason: string }[] }>(
          importJobId,
          enq.task_id
        );
        finishClientBackgroundTask(enq.task_id);
        return out;
      }
      if (bulkAction === 'create_provisional_customer') {
        const display_names: Record<string, string> = {};
        for (const id of selectedIds) {
          display_names[String(id)] = (bulkProvNamesById[id] ?? '').trim();
        }
        const enq = await apiPost<{ task_id: string; async_poll: boolean }>(
          `/api/v1/shipment-evidence/import-jobs/${importJobId}/bulk-create-provisional-customers`,
          { candidate_ids: selectedIds, display_names }
        );
        registerClientBackgroundTask({
          taskId: enq.task_id,
          importJobId,
          kind: 'shipment_bulk',
          label: 'Bulk provisional channel partners',
        });
        const out = await pollShipmentBulkTask<Record<string, unknown>>(importJobId, enq.task_id);
        finishClientBackgroundTask(enq.task_id);
        return out;
      }
      if (bulkAction === 'map_distributor') {
        for (const cid of selectedIds) {
          await apiPost(`/api/v1/shipment-evidence/import-candidates/${cid}/map-distributor`, {
            distributor_id: Number(bulkDistributorId),
          });
        }
        return { mapped: selectedIds };
      }
      if (bulkAction === 'create_provisional_distributor') {
        for (const cid of selectedIds) {
          await apiPost(`/api/v1/shipment-evidence/import-candidates/${cid}/create-provisional-distributor`, {});
        }
        return { mapped: selectedIds };
      }
      if (bulkAction === 'ignore') {
        for (const cid of selectedIds) {
          await apiPost(`/api/v1/shipment-evidence/import-candidates/${cid}/reject`, {});
        }
        return { mapped: selectedIds };
      }
      throw new Error('Unsupported bulk action');
    },
    onSuccess: () => {
      setBulkApplySummary('Bulk steward action completed.');
      setSelectedIds([]);
      setBulkMode('normal');
      invalidateShipmentImportJobStewardQueries(qc, importJobId);
      onInvalidate();
      onBulkClosed?.();
    },
    onError: (err: Error) => {
      setBulkApplySummary(err.message);
    },
  });

  const resetBulkForm = useCallback(() => {
    setBulkCustomerId('');
    setBulkDistributorId('');
    setBulkProvNamesById({});
    setBulkApplySummary(null);
  }, []);

  return {
    bulkAction,
    setBulkAction,
    bulkCustomerId,
    setBulkCustomerId,
    bulkDistributorId,
    setBulkDistributorId,
    bulkProvNamesById,
    setBulkProvName: (id: number, name: string) => setBulkProvNamesById((prev) => ({ ...prev, [id]: name })),
    bulkApplySummary,
    setBulkApplySummary,
    bulkFormReady,
    bulkApply,
    resetBulkForm,
  };
}
