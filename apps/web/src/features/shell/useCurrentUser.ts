'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';
import type { UserRole } from '@cip/types';

export type CurrentUser = {
  id: string;
  role: UserRole | string;
  /** N-0100 part B: what the person does; not a role, grants nothing. */
  job?: string | null;
  tenant_id?: string | null;
  email?: string | null;
  display_name?: string | null;
  auth_mode?: string;
  roles_supported?: string[];
  my_accounts?: {
    assigned_count: number;
    filter_on: boolean;
    /** D-0141: whether the filter starts on for this user (older APIs omit it: on with accounts). */
    filter_default_on?: boolean;
  };
  /** D-0141: where sign-in lands, e.g. '/brief' or '/dashboards?start=my_accounts'. */
  starting_screen?: { path: string; policy: string };
};

export const AUTH_ME_QUERY_KEY = ['auth', 'me'] as const;

/** Where sign-in lands (D-0141). Only an in-app path is followed; anything else is Brief. */
export function startingPath(me: Pick<CurrentUser, 'starting_screen'> | null | undefined): string {
  const path = me?.starting_screen?.path;
  if (typeof path === 'string' && path.startsWith('/') && !path.startsWith('//')) return path;
  return '/brief';
}

export function useCurrentUser() {
  return useQuery({
    queryKey: AUTH_ME_QUERY_KEY,
    queryFn: () => apiGet<CurrentUser>('/api/v1/auth/me'),
    staleTime: 60_000,
    retry: false,
  });
}

export function useInvalidateCurrentUser() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: AUTH_ME_QUERY_KEY });
}
