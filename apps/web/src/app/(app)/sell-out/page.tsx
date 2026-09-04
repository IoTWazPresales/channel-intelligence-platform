'use client';

import { ChannelOpsStockWorkspace } from '@/features/stock/ChannelOpsStockWorkspace';
import { PageHeader } from '@/components/PageHeader';
import { navPageChrome } from '@/features/shell/navPageChrome';

/** Legacy /sell-out route — redirects via middleware; thin fallback if middleware bypassed. */
export default function ChannelOperationsPage() {
  return (
    <>
      <PageHeader {...navPageChrome('/stock', { search: '?lens=movement' })} />
      <ChannelOpsStockWorkspace />
    </>
  );
}
