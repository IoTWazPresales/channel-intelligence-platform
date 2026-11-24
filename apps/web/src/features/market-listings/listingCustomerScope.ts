'use client';

import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { apiGet } from '@/lib/api';

export type ListingCustomerPick = {
  id: number;
  customer_code: string;
  customer_name: string;
};

type CustomerList = { items?: ListingCustomerPick[] };

const STORAGE_KEY = 'cip.listing-customer-scope.v1';

function readStoredIds(): number[] | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return null;
    return parsed.map((x) => Number(x)).filter((x) => Number.isFinite(x));
  } catch {
    return null;
  }
}

function writeStoredIds(ids: number[]) {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    /* ignore quota */
  }
}

export function customersListUrl(reportingOnly: boolean, extra?: { q?: string; customer_id?: number }) {
  const params = new URLSearchParams({ page: '1', page_size: '200' });
  if (reportingOnly) params.set('reporting_only', 'true');
  if (extra?.q) params.set('q', extra.q);
  if (extra?.customer_id != null) params.set('customer_id', String(extra.customer_id));
  return `/api/v1/customers?${params.toString()}`;
}

export function useListingCustomerScope(storageKey = STORAGE_KEY) {
  const reporting = useQuery({
    queryKey: ['customers', 'listing-scope', 'reporting'],
    queryFn: ({ signal }) => apiGet<CustomerList>(customersListUrl(true), { signal }),
    staleTime: 60_000,
  });
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const stored = readStoredIds();
    if (stored && stored.length) {
      setSelectedIds(stored);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated || selectedIds.length) return;
    const defaults = (reporting.data?.items ?? []).map((c) => c.id);
    if (defaults.length) setSelectedIds(defaults);
  }, [hydrated, reporting.data, selectedIds.length]);

  useEffect(() => {
    if (!hydrated) return;
    writeStoredIds(selectedIds);
  }, [hydrated, selectedIds, storageKey]);

  const labels = useMemo(() => {
    const m = new Map<number, string>();
    for (const c of reporting.data?.items ?? []) {
      m.set(c.id, (c.customer_name || c.customer_code || '').trim());
    }
    return m;
  }, [reporting.data]);

  const toggleCustomer = useCallback((id: number, on: boolean) => {
    setSelectedIds((prev) => {
      if (on) return prev.includes(id) ? prev : [...prev, id].sort((a, b) => a - b);
      return prev.filter((x) => x !== id);
    });
  }, []);

  const setCustomers = useCallback((ids: number[]) => {
    setSelectedIds([...new Set(ids)].sort((a, b) => a - b));
  }, []);

  const resetToReporting = useCallback(() => {
    const defaults = (reporting.data?.items ?? []).map((c) => c.id);
    setSelectedIds(defaults);
  }, [reporting.data]);

  return {
    reportingCustomers: reporting.data?.items ?? [],
    reportingLoading: reporting.isLoading,
    selectedIds,
    labels,
    toggleCustomer,
    setCustomers,
    resetToReporting,
    hydrated,
  };
}

export async function searchCustomers(q: string, signal: AbortSignal): Promise<ListingCustomerPick[]> {
  const page = await apiGet<CustomerList>(customersListUrl(false, { q }), { signal });
  return page.items ?? [];
}

/** Default open list = reporting customers; typed search (2+ chars) searches the full directory. */
export async function fetchEntityCustomerOptions(q: string, signal: AbortSignal): Promise<ListingCustomerPick[]> {
  const trimmed = q.trim();
  if (trimmed.length >= 2) return searchCustomers(trimmed, signal);
  const page = await apiGet<CustomerList>(customersListUrl(true), { signal });
  return page.items ?? [];
}