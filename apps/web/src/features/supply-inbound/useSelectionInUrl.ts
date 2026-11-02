import { useEffect, useRef } from 'react';

/**
 * The address for a grid selection made on the page (a clicked vessel, the "needs a look" cohort): the current address with
 * `vessel` and `cohort=needs_look` set or removed and everything else kept. Pure, so it can be tested.
 */
export function selectionHref(current: string, sel: { vessel: string; cohort: string }): string {
  const url = new URL(current, 'http://localhost');
  if (sel.vessel) url.searchParams.set('vessel', sel.vessel);
  else url.searchParams.delete('vessel');
  if (sel.cohort === 'needs_look') url.searchParams.set('cohort', 'needs_look');
  else if (url.searchParams.get('cohort') === 'needs_look') url.searchParams.delete('cohort');
  const qs = url.searchParams.toString();
  return `${url.pathname}${qs ? `?${qs}` : ''}${url.hash}`;
}

/**
 * Keeps the address in step with the selection without a navigation: `history.replaceState` only, no router push, no reload, no
 * new page request. Next.js reads the change into `useSearchParams`, nothing else re-renders on its account, and a reload or a
 * shared link lands on the same selection. The first render leaves the address alone.
 */
export function useSelectionInUrl(vessel: string, cohort: string): void {
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (typeof window === 'undefined') return;
    const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    const next = selectionHref(current, { vessel, cohort });
    if (next !== current) window.history.replaceState(window.history.state, '', next);
  }, [vessel, cohort]);
}
