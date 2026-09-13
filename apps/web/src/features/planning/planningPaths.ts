export const PLANNING_TITLE = 'Planning';

export const PLANNING_DESCRIPTION =
  'Lineup cases and plan lines per customer, readiness, line economics, PO reconciliation and rankings.';

export type PlanningLens = 'hub' | 'cases' | 'plans' | 'roadmap';

export const PLANNING_LEAVES: { value: Exclude<PlanningLens, 'hub'>; label: string; href: string }[] = [
  { value: 'cases', label: 'Lineup cases', href: '/lineup/cases' },
  { value: 'plans', label: 'Plans & line economics', href: '/commercial-planner' },
  { value: 'roadmap', label: 'Product roadmap', href: '/roadmap' },
];

export function planningLensFromPath(pathname: string): PlanningLens {
  if (pathname.startsWith('/lineup/cases')) return 'cases';
  if (pathname === '/commercial-planner') return 'plans';
  if (pathname.startsWith('/roadmap')) return 'roadmap';
  return 'hub';
}

/** Relocate the N-0009 workspace off the Planning hub without changing rail hrefs. */
export function planningWorkflowHref(href: string): string {
  return href === '/lineup' ? '/lineup/cases' : href;
}
