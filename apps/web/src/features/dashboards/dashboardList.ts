'use client';

import { useQuery } from '@tanstack/react-query';

import { useCurrentUser, type CurrentUser } from '@/features/shell/useCurrentUser';
import { apiGet } from '@/lib/api';

import type { Dashboard } from './types';

export type DashboardList = { items: Dashboard[] };

/**
 * The one cache key for `GET /api/v1/dashboards` (PR #111). The list depends on who asks, so it is kept per
 * tenant and user: one person's fresh list never answers for another. Every screen that reads the list
 * (dashboards editor, Overview, Reports) and every write that invalidates it must use this key, or an edit
 * on one screen leaves another showing the old dashboard.
 */
export function dashboardListKey(me: Pick<CurrentUser, 'id' | 'tenant_id'> | null | undefined) {
  return ['dashboards', me?.tenant_id ?? null, me?.id ?? null] as const;
}

/** The current user's dashboard list, under {@link dashboardListKey}. */
export function dashboardListQueryOptions(me: Pick<CurrentUser, 'id' | 'tenant_id'> | null | undefined) {
  return {
    queryKey: dashboardListKey(me),
    queryFn: ({ signal }: { signal: AbortSignal }) => apiGet<DashboardList>('/api/v1/dashboards', { signal }),
    retry: false,
  };
}

export function useDashboardList() {
  const { data: me } = useCurrentUser();
  const query = useQuery(dashboardListQueryOptions(me));
  return { me, queryKey: dashboardListKey(me), query };
}
