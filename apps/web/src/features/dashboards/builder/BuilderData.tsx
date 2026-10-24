'use client';

/**
 * Where builder components get v2 answers from. The app uses the network (`executeV2`); the
 * design-lab page and tests inject recorded responses through `V2ExecutorProvider`, so the very
 * same components render with no network.
 */

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { createContext, useContext, type ReactNode } from 'react';

import { executeV2 } from './api';
import type { V2Request, V2Response } from './types';

export type V2Executor = (req: V2Request, signal?: AbortSignal) => Promise<V2Response>;

const ExecutorContext = createContext<V2Executor>(executeV2);

export function V2ExecutorProvider({ execute, children }: { execute: V2Executor; children: ReactNode }) {
  return <ExecutorContext.Provider value={execute}>{children}</ExecutorContext.Provider>;
}

export function useV2Executor(): V2Executor {
  return useContext(ExecutorContext);
}

/**
 * One v2 query per card (Grafana-style: each widget loads on its own). The previous answer stays on
 * screen while a new one loads (`keepPreviousData`), so a filter change shows a refetch bar, not a
 * blank card.
 */
export function useV2Query(req: V2Request | null, opts: { enabled?: boolean; tag?: string } = {}) {
  const execute = useV2Executor();
  return useQuery({
    queryKey: ['v2-execute', opts.tag ?? 'main', req],
    queryFn: ({ signal }) => execute(req as V2Request, signal),
    enabled: Boolean(req) && opts.enabled !== false,
    placeholderData: req ? keepPreviousData : undefined,
    staleTime: 60_000,
    retry: false,
  });
}
