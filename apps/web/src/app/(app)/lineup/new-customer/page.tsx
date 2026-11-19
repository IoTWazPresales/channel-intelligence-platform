'use client';

import { NewCustomerLineup } from '@/features/lineup/newCustomer/NewCustomerLineup';
import { DomainHeader } from '@/features/workbench-ui/DomainHeader';
import { WorkbenchCanvas } from '@/features/workbench-ui/WorkbenchCanvas';

export default function NewCustomerLineupPage() {
  return (
    <WorkbenchCanvas>
      <DomainHeader
        crumbs={[{ label: 'Line-up', href: '/lineup' }, { label: 'New customer' }]}
        title="New-customer line-up"
        description="Create a reporting customer's line-up from database SKUs and approve it here."
      />
      <NewCustomerLineup />
    </WorkbenchCanvas>
  );
}
