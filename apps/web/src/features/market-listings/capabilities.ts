import type { LeafStatus } from '@/features/shell/navConfig';

export type CapabilityItem = { label: string; state: LeafStatus; note: string };

/** Honest capability copy from design-lab commercialCapabilities — keep Planned / Partly built / substrate. */
export const LISTING_CAPABILITIES: CapabilityItem[] = [
  {
    label: 'Monitored listings and URLs per customer × product',
    state: 'live',
    note: 'Registry with status history; manual, CSV, feed proposals, auto-finder.',
  },
  {
    label: 'Price and availability history',
    state: 'live',
    note: 'Scheduled and manual polls; snapshots retained; re-parse without re-fetch.',
  },
  {
    label: 'Is the promotion live at the planned price?',
    state: 'live',
    note: 'Each observation is checked against the covering CPOR line SRP.',
  },
  {
    label: 'Price-change detection and alerts',
    state: 'partial',
    note: 'First→last drift per listing; no per-change events or attention signal yet.',
  },
  {
    label: 'Late activation / early deactivation',
    state: 'substrate',
    note: 'Derivable from the observation timeline and the line window; not computed.',
  },
  {
    label: 'Product content and specification evidence',
    state: 'substrate',
    note: 'Raw snapshots are stored; only price, availability and badge are extracted.',
  },
  {
    label: 'SEO / listing-quality monitoring',
    state: 'planned',
    note: 'Spec v0 non-goal; roadmap P5.',
  },
];

export const COMPETITION_CAPABILITIES: CapabilityItem[] = [
  {
    label: 'Our SKU ↔ competitor SKU mappings with approval',
    state: 'live',
    note: 'Approve / reject workflow exists; score is the stored mapping score, not a lab fixture blend.',
  },
  {
    label: 'System-proposed candidates with factor breakdown',
    state: 'substrate',
    note: 'Deterministic scorer exists in code; nothing calls it yet. No Why-this-score factor panel (BACKLOG-164).',
  },
  {
    label: 'Competitor price observations',
    state: 'substrate',
    note: 'Table and list endpoint exist; no import template.',
  },
  {
    label: 'Monitored competitor listings',
    state: 'planned',
    note: 'Extend the listing registry to competitor products (BACKLOG §9.9).',
  },
  {
    label: 'Competitor impact on our sell-out or price',
    state: 'planned',
    note: 'Not derivable from stored data; not shown.',
  },
];
