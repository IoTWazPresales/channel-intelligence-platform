import type { CapabilityItem } from '@/features/workbench-ui/CapabilityLedger';

/** Honest production capability table — same jobs as the lab, no N-0010 jargon (I5). */
export const PLANNER_CAPABILITIES: CapabilityItem[] = [
  {
    label: 'Propose a plan from history, cover, forecast and MAC',
    state: 'partial',
    note: 'Build a plan from the customer and period: the lineup first, then that customer’s history. A seed case is optional. Listing, competitor price, and observed cover show on the line and do not set the quantity.',
  },
  {
    label: 'Create and edit plans manually (lines, layers, parameters)',
    state: 'live',
    note: 'You can add and edit the case and its lines, and move it through the stages. Header and line edits are draft or rejected only.',
  },
  {
    label: 'Waterfall and validation (dealer price, support/unit, budget check, flags)',
    state: 'live',
    note: 'Figures are recalculated for you. Flags never block. List support is the sum of line totals, same as the workspace.',
  },
  {
    label: 'Evidence behind each line in one view',
    state: 'live',
    note: 'Each proposed line has an Evidence column: listed or not, competitor price or none, observed cover as a flag. It does not write cover policy. Uplift from claim evidence is not derived.',
  },
  {
    label: 'Export in the customer’s promotion-plan format',
    state: 'partial',
    note: 'A saved workbook exists. The layout is fixed. Writing a plan back into the customer layout is not built.',
  },
  {
    label: 'Uplift, elasticity, effectiveness',
    state: 'planned',
    note: 'Not derived until ≥5 settled cases with claim evidence — never estimated.',
  },
];

export const TEMPLATE_CAPABILITIES: CapabilityItem[] = [
  {
    label: 'Store a profile: sheet roles, column map, value maps',
    state: 'live',
    note: 'A stored column map for past promotion workbooks. Historical imports use it today.',
  },
  {
    label: 'Confirm a mapping in the shared mapping panel',
    state: 'live',
    note: 'This screen uses the shared column-mapping panel. A change here is applied on the next historical import.',
  },
  {
    label: 'Learn a profile from an example workbook',
    state: 'partial',
    note: 'Open Learn from a workbook to detect the headers. Suggesting a map from a file is not a separate step.',
  },
  {
    label: 'Render an export in the profile’s layout',
    state: 'planned',
    note: 'Export uses a fixed layout today. Writing a plan back into the customer layout is not built.',
  },
];
