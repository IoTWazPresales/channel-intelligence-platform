import type { QueryClient } from '@tanstack/react-query';

import { administrationOverviewQueryOptions } from '@/features/administration/adminQueryOptions';
import { dashboardListQueryOptions } from '@/features/dashboards/dashboardList';
import { stewardshipSummaryQueryOptions } from '@/features/data-stewardship/stewardshipQueryOptions';
import { listingCaptureMetaQueryOptions } from '@/features/market-listings/listingMetaQueryOptions';
import { planningOverviewQueryOptions } from '@/features/planning/planningQueryOptions';
import {
  cporFundingChromeQueryOptions,
  cporSettlementBookQueryOptions,
} from '@/features/promotions-funding/cporQueryOptions';
import { briefSignalsQueryOptions } from '@/features/shell/useBriefSignals';
import { filterNavGroupsForRole, isCommercialPlannerEnabled, navGroups } from '@/features/shell/navConfig';
import { coverDistributionQueryOptions } from '@/features/stock/coverQueryOptions';
import { supplyOverviewQueryOptions } from '@/features/supply-inbound/supplyQueryOptions';
import type { CurrentUser } from '@/features/shell/useCurrentUser';
import { myAccountsChoice, type MyAccountsChoice } from '@/lib/myAccounts';

/** Attached to every warm-up prefetch so active-page fetches stay distinguishable. */
export const NAV_WARMUP_META = { navWarmup: true } as const;

export type NavWarmupQueryDef = {
  queryKey: readonly unknown[];
  queryFn: (ctx: { signal: AbortSignal }) => Promise<unknown>;
  staleTime?: number;
};

export type NavWarmupDomain = {
  id: string;
  route: string;
  queries: NavWarmupQueryDef[];
};

function groupsForRole(role: string | null | undefined): typeof navGroups {
  let groups = navGroups;
  if (!isCommercialPlannerEnabled()) {
    groups = navGroups
      .map((g) => ({
        ...g,
        items: g.items.filter(
          (i) => !i.href.startsWith('/commercial-planner') && i.href !== '/promotions',
        ),
      }))
      .filter((g) => g.items.length > 0);
  }
  return filterNavGroupsForRole(groups, role);
}

function domainQueries(id: string, me: CurrentUser | undefined, accountsChoice: MyAccountsChoice): NavWarmupQueryDef[] {
  switch (id) {
    case 'overview':
      return [
        briefSignalsQueryOptions(accountsChoice),
        dashboardListQueryOptions(me),
      ];
    case 'stock':
      return [coverDistributionQueryOptions()];
    case 'supply':
      return [supplyOverviewQueryOptions()];
    case 'planning':
      return [planningOverviewQueryOptions()];
    case 'funding':
      return [cporFundingChromeQueryOptions(), cporSettlementBookQueryOptions()];
    case 'market':
      return [listingCaptureMetaQueryOptions()];
    case 'data':
      return [stewardshipSummaryQueryOptions()];
    case 'admin':
      return [administrationOverviewQueryOptions()];
    default:
      return [];
  }
}

/** Domains the signed-in role may see, each with read-only warm-up queries (heavy reads omitted). */
export function navWarmupDomainsForRole(
  role: string | null | undefined,
  me: CurrentUser | undefined,
  accountsChoice: MyAccountsChoice = myAccountsChoice(),
): NavWarmupDomain[] {
  const visible = new Set(groupsForRole(role).map((g) => g.id));
  const out: NavWarmupDomain[] = [];
  for (const g of navGroups) {
    if (!visible.has(g.id)) continue;
    const queries = domainQueries(g.id, me, accountsChoice);
    if (queries.length === 0) continue;
    const route = (g.href ?? g.items[0]?.href ?? '/brief').split('?')[0];
    out.push({ id: g.id, route, queries });
  }
  return out;
}

export async function prefetchNavWarmupQuery(
  qc: QueryClient,
  def: NavWarmupQueryDef,
): Promise<void> {
  await qc.prefetchQuery({
    ...def,
    meta: NAV_WARMUP_META,
  });
}