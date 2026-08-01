'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';

import { apiGet } from '@/lib/api';
import type { UserRole } from '@cip/types';

export type CurrentUser = {
  id: string;
  role: UserRole | string;
  tenant_id?: string | null;
  email?: string | null;
  display_name?: string | null;
  auth_mode?: string;
  roles_supported?: string[];
};

export const AUTH_ME_QUERY_KEY = ['auth', 'me'] as const;

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
