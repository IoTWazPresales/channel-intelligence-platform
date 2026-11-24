'use client';

import { type Query, useIsFetching, useQueryClient } from '@tanstack/react-query';
import { usePathname, useSearchParams, useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef } from 'react';

import { railNavGroups } from '@/features/shell/navConfig';
import { activeNavGroup } from '@/features/shell/navPageChrome';
import { useCurrentUser } from '@/features/shell/useCurrentUser';
import { myAccountsChoice } from '@/lib/myAccounts';

import {
  navWarmupDomainsForRole,
  prefetchNavWarmupQuery,
  type NavWarmupQueryDef,
} from './navWarmupRegistry';
import {
  flattenDomainQueue,
  NavWarmupScheduler,
  scheduleAfterIdle,
} from './navWarmupScheduler';

function isNavWarmupMeta(meta: unknown): boolean {
  return Boolean(meta && typeof meta === 'object' && (meta as { navWarmup?: boolean }).navWarmup);
}

function hrefPath(href: string): string {
  const q = href.indexOf('?');
  return q >= 0 ? href.slice(0, q) : href;
}

function useNavRoutePrefetch(role: string | null | undefined, enabled: boolean) {
  const router = useRouter();
  useEffect(() => {
    if (!enabled) return;
    const paths = new Set<string>();
    for (const g of railNavGroups(role)) {
      paths.add(hrefPath(g.href ?? g.items[0]?.href ?? '/brief'));
      for (const item of g.items) paths.add(hrefPath(item.href));
    }
    for (const path of paths) {
      try {
        router.prefetch(path);
      } catch {
        /* best-effort route code warm-up */
      }
    }
  }, [enabled, role, router]);
}

/** Low-priority background prefetch of other capability domains after the active page settles. */
export function useNavQueryWarmup() {
  const pathname = usePathname() || '/';
  const searchParams = useSearchParams();
  const searchStr = searchParams.toString();
  const qc = useQueryClient();
  const { data: me, isError: meError } = useCurrentUser();
  const authenticated = Boolean(me && !meError);
  const role = me?.role ? String(me.role) : null;

  const activeDomainId = activeNavGroup(pathname, searchStr ? `?${searchStr}` : '')?.id ?? null;

  const activeFetchingCount = useIsFetching({
    predicate: (q: Query) => !isNavWarmupMeta(q.meta),
  });

  const schedulerRef = useRef<NavWarmupScheduler | null>(null);
  if (!schedulerRef.current) {
    schedulerRef.current = new NavWarmupScheduler({
      concurrency: 2,
      prefetch: async (item) => {
        await prefetchNavWarmupQuery(qc, item.query);
      },
    });
  }
  const scheduler = schedulerRef.current;

  const domains = useMemo(
    () => (authenticated ? navWarmupDomainsForRole(role, me, myAccountsChoice()) : []),
    [authenticated, role, me],
  );

  const loggedOutOrLogin = !authenticated || pathname.startsWith('/login');

  useEffect(() => {
    if (loggedOutOrLogin) {
      scheduler.pause();
      return;
    }
    scheduler.pause();
    scheduler.setQueue(flattenDomainQueue(domains, activeDomainId));
  }, [loggedOutOrLogin, pathname, activeDomainId, domains, scheduler]);

  useEffect(() => {
    if (loggedOutOrLogin) return;
    if (activeFetchingCount > 0) {
      scheduler.pause();
      return;
    }
    const cancel = scheduleAfterIdle(() => {
      scheduler.setQueue(flattenDomainQueue(domains, activeDomainId));
      scheduler.unpause();
      scheduler.tryPump();
    });
    return cancel;
  }, [activeFetchingCount, loggedOutOrLogin, activeDomainId, domains, scheduler]);

  useNavRoutePrefetch(role, !loggedOutOrLogin);
}

/** @internal test helper — ensures registry entries are GET-shaped only. */
export function isReadWarmupQuery(def: NavWarmupQueryDef): boolean {
  return typeof def.queryFn === 'function' && Array.isArray(def.queryKey);
}