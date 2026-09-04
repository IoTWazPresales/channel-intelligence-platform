import type { CapabilityItem } from '@/features/workbench-ui/CapabilityLedger';

/** Honest production capability table — same jobs as the lab, no N-0010 jargon (I5). */
export const PLANNER_CAPABILITIES: CapabilityItem[] = [
  {
    label: 'Propose a plan from history, cover, forecast and MAC',
    state: 'partial',
    note: 'Draft exists (B4) but needs a seed case id; no proposal from customer + period alone.',
  },
  {
    label: 'Create and edit plans manually (lines, layers, parameters)',
    state: 'live',
    note: 'Case + line CRUD and lifecycle transitions with events. Header and line edits are draft or rejected only.',
  },
  {
    label: 'Waterfall and validation (dealer price, support/unit, budget check, flags)',
    state: 'live',
    note: 'Server-side recompute; flags never block. List support is the sum of line totals, same as the workspace.',
  },
  {
    label: 'Evidence behind each line in one view',
    state: 'partial',
    note: 'Waterfall and stored flags on the line. Cover, listings and competitor counts are not joined onto the line yet — open those domains from Related.',
  },
  {
    label: 'Export in the customer’s promotion-plan format',
    state: 'partial',
    note: 'Versioned XLSX exists; layout is one frozen 32-column tuple in code. Template-driven export is not built.',
  },
  {
    label: 'Uplift, elasticity, effectiveness',
    state: 'planned',
    note: 'Not derived until ≥5 settled cases with claim evidence — never estimated.',
  },
];
