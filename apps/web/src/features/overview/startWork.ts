import { roleMayAccess } from '@/features/shell/navConfig';
import type { UserRole } from '@cip/types';

const STEWARD_PLUS: UserRole[] = ['admin', 'steward'];
const PLANNER_PLUS: UserRole[] = ['admin', 'planner'];

export type StartGroup = 'plan' | 'data' | 'funding';

export const START_GROUP_LABEL: Record<StartGroup, string> = {
  plan: 'Plan',
  data: 'Data',
  funding: 'Funding',
};

/** Role-gated verbs that open screens which already do the work. Not Attention. */
export type StartVerb = {
  id: string;
  label: string;
  href: string;
  what: string;
  roles: UserRole[];
  group: StartGroup;
};

export const START_VERBS: StartVerb[] = [
  {
    id: 'create-lineup',
    label: 'Import a lineup',
    href: '/admin/imports?unified=1',
    what: 'Send workbooks to Import Center. Each file becomes a lineup case.',
    roles: STEWARD_PLUS,
    group: 'plan',
  },
  {
    id: 'open-lineup',
    label: 'Review lineup cases',
    href: '/lineup/cases',
    what: 'Assortment, pending approval, and net requirement in one list.',
    roles: PLANNER_PLUS,
    group: 'plan',
  },
  {
    id: 'create-promo-plan',
    label: 'Propose a promotion',
    href: '/promotions?propose=1',
    what: 'Build plan lines from a customer and a period.',
    roles: PLANNER_PLUS,
    group: 'plan',
  },
  {
    id: 'import-sell-through',
    label: 'Load retailer sell-through',
    href: '/admin/imports?template=customer_sell_through',
    what: 'Put a CST workbook through the guided wizard.',
    roles: STEWARD_PLUS,
    group: 'data',
  },
  {
    id: 'import-shipping',
    label: 'Load inbound shipments',
    href: '/admin/imports?template=inbound_shipments',
    what: 'Put a shipment workbook through the guided wizard.',
    roles: STEWARD_PLUS,
    group: 'data',
  },
  {
    id: 'steward-queue',
    label: 'Resolve unmatched tokens',
    href: '/admin/mappings',
    what: 'Unmatched tokens from imports, resolved in one place.',
    roles: STEWARD_PLUS,
    group: 'data',
  },
  {
    id: 'settle-case',
    label: 'Settle a funding case',
    href: '/commercial-planner/cpor-cases',
    what: 'Reconcile a funding case and close it out.',
    roles: PLANNER_PLUS,
    group: 'funding',
  },
];

export function startVerbsForRole(role: string | null | undefined): StartVerb[] {
  return START_VERBS.filter((v) => roleMayAccess(role, v.roles));
}
