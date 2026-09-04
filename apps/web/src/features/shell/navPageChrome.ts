import { navGroups, navHrefMatches, type NavGroup, type NavLeaf } from '@/features/shell/navConfig';

export type PageCrumb = { label: string; href?: string };

export type NavPageChrome = {
  crumbs: PageCrumb[];
  title: string;
};

function normalizeSearch(search: string | undefined): string {
  if (!search) return '';
  return search.startsWith('?') ? search : `?${search}`;
}

function hrefPath(href: string): string {
  const qIdx = href.indexOf('?');
  return qIdx >= 0 ? href.slice(0, qIdx) : href;
}

function queryLeafMatches(pathname: string, search: string, href: string): boolean {
  const qIdx = href.indexOf('?');
  if (qIdx < 0) return false;
  const path = href.slice(0, qIdx);
  if (pathname !== path) return false;
  if (path === '/admin/customers/duplicates') {
    return navHrefMatches(pathname, search, href);
  }
  const want = new URLSearchParams(href.slice(qIdx + 1));
  const have = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  for (const [k, v] of want.entries()) {
    if (have.get(k) !== v) return false;
  }
  return true;
}

function matchScore(pathname: string, search: string, href: string): number | null {
  const path = hrefPath(href);
  if (href.includes('?')) {
    return queryLeafMatches(pathname, search, href) ? 2000 + path.length : null;
  }
  if (!navHrefMatches(pathname, search, href)) return null;
  if (pathname === path) return 1000 + path.length;
  return path.length;
}

export function matchNavLeaf(pathname: string, search = ''): { group: NavGroup; item: NavLeaf } | null {
  const normalized = normalizeSearch(search);
  let best: { group: NavGroup; item: NavLeaf; score: number } | null = null;
  for (const group of navGroups) {
    for (const item of group.items) {
      const score = matchScore(pathname, normalized, item.href);
      if (score == null) continue;
      if (!best || score > best.score) best = { group, item, score };
    }
  }
  return best ? { group: best.group, item: best.item } : null;
}

/**
 * Domain that owns the current location. Exact leaf match first (query-aware); otherwise the
 * domain whose home path or a leaf path is the longest prefix of the pathname (e.g. bare `/stock`
 * with no lens, nested case routes). Null when nothing in the IA owns the route.
 */
export function activeNavGroup(pathname: string, search = ''): NavGroup | null {
  const exact = matchNavLeaf(pathname, search);
  if (exact) return exact.group;
  let best: { group: NavGroup; len: number } | null = null;
  const consider = (group: NavGroup, href: string | undefined) => {
    if (!href) return;
    const path = hrefPath(href);
    if (pathname === path || (path !== '/' && pathname.startsWith(`${path}/`))) {
      if (!best || path.length > best.len) best = { group, len: path.length };
    }
  };
  for (const group of navGroups) {
    consider(group, group.href);
    for (const item of group.items) consider(group, item.href);
  }
  return best ? (best as { group: NavGroup }).group : null;
}

export function navPageChrome(
  pathname: string,
  opts?: {
    search?: string;
    extraCrumbs?: PageCrumb[];
    title?: string;
  },
): NavPageChrome {
  const extra = opts?.extraCrumbs ?? [];
  const match = matchNavLeaf(pathname, opts?.search);
  if (!match) {
    return {
      crumbs: extra.length ? extra : [{ label: opts?.title ?? pathname }],
      title: opts?.title ?? pathname,
    };
  }

  const itemPath = hrefPath(match.item.href);
  const groupHome = match.group.href;
  const currentIsGroupHome = Boolean(groupHome && match.item.href === groupHome && extra.length === 0);

  const groupCrumb: PageCrumb = { label: match.group.label };
  if (groupHome && !currentIsGroupHome) groupCrumb.href = groupHome;

  const leafCrumb: PageCrumb = { label: match.item.label };
  if (extra.length) leafCrumb.href = itemPath;

  const crumbs: PageCrumb[] = [groupCrumb, leafCrumb, ...extra];

  const lastExtra = extra.length ? extra[extra.length - 1] : undefined;
  return {
    crumbs,
    title: opts?.title ?? lastExtra?.label ?? match.item.label,
  };
}
