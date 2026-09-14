import { inRail, navGroups, roleMayAccess, type NavLeaf } from '@/features/shell/navConfig';

/** Rail-only Data destinations — listed in-page so the four grouped tabs are not the only door. */
export function dataAlsoHereItems(role: string | null | undefined, tabHrefs: string[]): NavLeaf[] {
  const tabs = new Set(tabHrefs);
  const data = navGroups.find((g) => g.id === 'data');
  const leaves = (data?.items ?? []).filter((l) => inRail(l) && !tabs.has(l.href));
  if (role == null || String(role).trim() === '') return leaves;
  return leaves.filter((l) => roleMayAccess(role, l.roles));
}
