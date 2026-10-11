import type { LeafStatus } from '@/features/shell/navConfig';

export type CapabilityItem = { label: string; state: LeafStatus; note: string };

/** Honest capability copy from design-lab commercialCapabilities — keep Planned / Partly built / substrate. */
export const LISTING_CAPABILITIES: CapabilityItem[] = [
  {
    label: 'Monitored listings and URLs per customer × product',
    state: 'live',
    note: 'A listing URL per customer and product, with status history. Add one by hand, from a file, from a feed, or by search.',
  },
  {
    label: 'Price and availability history',
    state: 'live',
    note: 'Checked every 30 minutes while this computer is running, and by hand. Overnight gaps are expected. The screen shows the last check. Earlier checks are kept.',
  },
  {
    label: 'Is the promotion live at the planned price?',
    state: 'live',
    note: 'Each check is compared with the planned price on the covering promotion.',
  },
  {
    label: 'Price-change detection and alerts',
    state: 'partial',
    note: 'Shows how far the latest price has moved from the first. A separate alert for each change is not built.',
  },
  {
    label: 'Late activation / early deactivation',
    state: 'substrate',
    note: 'Can be read from the check history and the promotion window. Not calculated yet.',
  },
  {
    label: 'Product content and specification evidence',
    state: 'substrate',
    note: 'The full page is stored. Only price, availability, and badge are pulled out.',
  },
  {
    label: 'SEO / listing-quality monitoring',
    state: 'planned',
    note: 'Not in this release.',
  },
];

export const COMPETITION_CAPABILITIES: CapabilityItem[] = [
  {
    label: 'Our SKU ↔ competitor SKU mappings with approval',
    state: 'live',
    note: 'You can approve or reject a match. The score shown is the one stored with the match.',
  },
  {
    label: 'System-proposed candidates with factor breakdown',
    state: 'substrate',
    note: 'Suggested matches, and a reason for the score, are not offered yet.',
  },
  {
    label: 'Competitor price observations',
    state: 'substrate',
    note: 'No file to import yet, so this list stays empty.',
  },
  {
    label: 'Monitored competitor listings',
    state: 'planned',
    note: 'Competitor product pages are not watched yet.',
  },
  {
    label: 'Competitor impact on our sell-out or price',
    state: 'planned',
    note: 'Not calculated from what is stored, so it is not shown.',
  },
];
