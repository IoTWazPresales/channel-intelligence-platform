import { roleMayAccess } from '@/features/shell/navConfig';
import type { UserRole } from '@cip/types';

const STEWARD_PLUS: UserRole[] = ['admin', 'steward'];
const PLANNER_PLUS: UserRole[] = ['admin', 'planner'];

/** Role-gated verbs that open screens which already do the work. Not Attention. */
export type StartVerb = {
  id: string;
  label: string;
  href: string;
  what: string;
  roles: UserRole[];
};

export const START_VERBS: StartVerb[] = [
  {
    id: 'create-lineup',
    label: 'Import a lineup',
    href: '/admin/imports?unified=1',
    what: 'Upload lineup files in Import Center. Each file becomes a case.',
    roles: STEWARD_PLUS,
  },
  {
    id: 'open-lineup',
    label: 'Open lineup cases',
    href: '/lineup/cases',
    what: 'Assortment, pending approval, and net requirement on existing cases.',
    roles: PLANNER_PLUS,
  },
  {
    id: 'create-promo-plan',
    label: 'Create promotion plan',
    href: '/promotions?propose=1',
    what: 'Propose lines from a customer and period on Promotion Planner.',
    roles: PLANNER_PLUS,
  },
  {
    id: 'import-sell-through',
    label: 'Import sell-through',
    href: '/admin/imports?template=customer_sell_through',
    what: 'Retailer CST workbook into the guided import wizard.',
    roles: STEWARD_PLUS,
  },
  {
    id: 'import-shipping',
    label: 'Import a shipping file',
    href: '/admin/imports?template=inbound_shipments',
    what: 'Inbound shipment workbook into the guided import wizard.',
    roles: STEWARD_PLUS,
  },
  {
    id: 'settle-case',
    label: 'Settle a case',
    href: '/commercial-planner/cpor-cases',
    what: 'Open the case book, then settle on the case desk.',
    roles: PLANNER_PLUS,
  },
  {
    id: 'steward-queue',
    label: 'Work the steward queue',
    href: '/admin/mappings',
    what: 'Open candidates grouped by failure type. Resolve in the existing job steward.',
    roles: STEWARD_PLUS,
  },
];

export function startVerbsForRole(role: string | null | undefined): StartVerb[] {
  return START_VERBS.filter((v) => roleMayAccess(role, v.roles));
}
