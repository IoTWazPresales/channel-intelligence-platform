'use client';

import { useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';

import { apiPost, safeDisplayError } from '@/lib/api';

import type { PinConfirmBulkResult, PinConfirmItem, StoreMapPayload, StoreMapStore } from '../types';
import { proposalKey } from './pinProposals';

const MAP_KEY = ['store-dc-map'];

/**
 * Steward confirm for proposed pins. One item uses the single confirm route, several use the bulk
 * route. Only a steward's click reaches here; the proposal itself never writes a coordinate.
 */
export function useProposalConfirm() {
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const busy = useRef(false);

  function merge(saved: StoreMapStore[]) {
    const byKey = new Map(saved.map((store) => [proposalKey(store), store]));
    queryClient.setQueryData<StoreMapPayload>(MAP_KEY, (current) => current && ({
      ...current,
      stores: current.stores.map((store) => byKey.get(proposalKey(store)) ?? store),
    }));
  }

  async function confirm(items: PinConfirmItem[]): Promise<void> {
    if (busy.current || items.length === 0) return;
    busy.current = true;
    setSaving(true);
    const keys = items.map(proposalKey);
    setErrors((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !keys.includes(key))));
    try {
      if (items.length === 1) {
        const saved = await apiPost<StoreMapStore>('/api/v1/store-dc/pins/confirm', items[0]);
        merge([saved]);
      } else {
        const result = await apiPost<PinConfirmBulkResult>('/api/v1/store-dc/pins/confirm-bulk', { pins: items });
        merge(result.saved);
        const failed: Record<string, string> = {};
        for (const item of result.failed) {
          failed[proposalKey({ customer_id: item.customer_id, site_label: item.site_label ?? '' })] = item.error;
        }
        if (Object.keys(failed).length > 0) setErrors((current) => ({ ...current, ...failed }));
      }
      await queryClient.invalidateQueries({ queryKey: MAP_KEY });
    } catch (error) {
      const message = safeDisplayError(error);
      setErrors((current) => ({ ...current, ...Object.fromEntries(keys.map((key) => [key, message])) }));
    } finally {
      busy.current = false;
      setSaving(false);
    }
  }

  function clearError(key: string) {
    setErrors((current) => Object.fromEntries(Object.entries(current).filter(([item]) => item !== key)));
  }

  return { confirm, saving, errors, clearError };
}
