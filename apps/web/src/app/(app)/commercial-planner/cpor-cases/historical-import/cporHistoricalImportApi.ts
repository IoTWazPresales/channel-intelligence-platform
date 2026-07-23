import { apiGet, apiPost, apiUrl, parseApiErrorDetailText } from '@/lib/api';

import type {
  CporEntityTabId,
  CporHistoricalCandidate,
  CporHistoricalSummary,
} from './cporHistoricalSteward.config';

const ADMIN = { headers: { 'X-User-Role': 'admin' } } as const;

export type CporDimPick =
  | { id: number; sku: string; name: string }
  | { id: number; customer_code: string; customer_name: string }
  | { id: number; distributor_code: string; distributor_name: string };

export function cporDimLabel(o: CporDimPick): string {
  if ('sku' in o) return `${o.sku} — ${o.name}`;
  if ('customer_code' in o) return `${o.customer_code} — ${o.customer_name}`;
  return `${o.distributor_code} — ${o.distributor_name}`;
}

export async function fetchCporHistoricalSummary(
  jobId: number,
  signal?: AbortSignal
): Promise<CporHistoricalSummary> {
  return apiGet<CporHistoricalSummary>(`/api/v1/cpor/historical-import/jobs/${jobId}/summary`, {
    signal,
    ...ADMIN,
  });
}

export async function fetchCporHistoricalCandidates(
  jobId: number,
  entity: CporEntityTabId,
  signal?: AbortSignal
): Promise<{
  candidates: CporHistoricalCandidate[];
  counts: Record<string, number>;
  plan_class_counts?: CporHistoricalSummary['plan_class_counts'];
}> {
  return apiGet<{
    candidates: CporHistoricalCandidate[];
    counts: Record<string, number>;
    plan_class_counts?: CporHistoricalSummary['plan_class_counts'];
  }>(`/api/v1/cpor/historical-import/jobs/${jobId}/candidates?entity=${entity}`, {
    signal,
    ...ADMIN,
  });
}

export async function mapCporHistoricalToken(args: {
  jobId: number;
  entity: CporEntityTabId;
  token: string;
  dimId: number;
}): Promise<{ updated: number }> {
  return apiPost<{ updated: number }>(
    `/api/v1/cpor/historical-import/jobs/${args.jobId}/map-token`,
    { entity: args.entity, token: args.token, dim_id: args.dimId },
    ADMIN
  );
}

/**
 * Prefer bulk-map-token; if the endpoint is missing (404), fall back to sequential map-token.
 */
export async function bulkMapCporHistoricalTokens(args: {
  jobId: number;
  entity: CporEntityTabId;
  tokens: string[];
  dimId: number;
}): Promise<{ updated: number; fallback?: boolean }> {
  const tokens = args.tokens.map((t) => t.trim()).filter(Boolean);
  if (tokens.length === 0) return { updated: 0 };

  const res = await fetch(apiUrl(`/api/v1/cpor/historical-import/jobs/${args.jobId}/bulk-map-token`), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Role': 'admin',
      'X-User-Id': 'demo-user',
    },
    body: JSON.stringify({ entity: args.entity, tokens, dim_id: args.dimId }),
    cache: 'no-store',
  });

  if (res.status === 404) {
    let updated = 0;
    for (const token of tokens) {
      const one = await mapCporHistoricalToken({
        jobId: args.jobId,
        entity: args.entity,
        token,
        dimId: args.dimId,
      });
      updated += one.updated ?? 0;
    }
    return { updated, fallback: true };
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseApiErrorDetailText(text) || `Bulk map failed (${res.status})`);
  }

  const body = (await res.json()) as { updated?: number };
  return { updated: body.updated ?? 0 };
}

export async function validateCporHistoricalJob(
  jobId: number
): Promise<{ async: boolean; task_id: string | null }> {
  const res = await fetch(apiUrl(`/api/v1/cpor/historical-import/jobs/${jobId}/validate`), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Role': 'admin',
      'X-User-Id': 'demo-user',
    },
    body: '{}',
    cache: 'no-store',
  });
  if (res.status === 404) {
    const processRes = await fetch(apiUrl(`/api/v1/imports/jobs/${jobId}/process`), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Role': 'admin',
        'X-User-Id': 'demo-user',
      },
      body: '{}',
      cache: 'no-store',
    });
    if (!processRes.ok) {
      const text = await processRes.text();
      throw new Error(text.trim() || `Process failed (${processRes.status})`);
    }
    return (await processRes.json()) as { async: boolean; task_id: string | null };
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text.trim() || `Validate failed (${res.status})`);
  }
  return (await res.json()) as { async: boolean; task_id: string | null };
}

export async function applyCporHistoricalJob(
  jobId: number
): Promise<{ async: boolean; task_id: string | null }> {
  return apiPost<{ async: boolean; task_id: string | null }>(
    `/api/v1/cpor/historical-import/jobs/${jobId}/apply`,
    { confirm: true },
    ADMIN
  );
}

export async function fetchCporDimOptions(
  entity: CporEntityTabId,
  q: string,
  signal: AbortSignal
): Promise<CporDimPick[]> {
  if (entity === 'product') {
    const res = await apiGet<{ items: Array<{ id: number; sku: string; name: string }> }>(
      `/api/v1/products?page=1&page_size=25&q=${encodeURIComponent(q)}`,
      { signal }
    );
    return res.items ?? [];
  }
  if (entity === 'customer') {
    const res = await apiGet<{
      items: Array<{ id: number; customer_code: string; customer_name: string }>;
    }>(`/api/v1/customers?page=1&page_size=25&q=${encodeURIComponent(q)}`, { signal });
    return res.items ?? [];
  }
  const res = await apiGet<{
    items: Array<{ id: number; distributor_code: string; distributor_name: string }>;
  }>(`/api/v1/distributors?page=1&page_size=25&q=${encodeURIComponent(q)}`, { signal });
  return res.items ?? [];
}

/** Stable numeric id from token string for workspace row keys. */
export function cporTokenRowId(token: string): number {
  let h = 0;
  for (let i = 0; i < token.length; i += 1) h = (h * 31 + token.charCodeAt(i)) | 0;
  return Math.abs(h) || 1;
}
