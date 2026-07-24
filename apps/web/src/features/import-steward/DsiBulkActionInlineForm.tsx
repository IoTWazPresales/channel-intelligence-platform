'use client';

import type { BulkTableSelectionMode } from '@/components/bulkTable/BulkSelectionToolbar';

import { DsiCustomerSearchFields } from './DsiCustomerSearchFields';
import { DSI_ENGINE_CONFIG } from './dsiSteward.engineConfig';
import type { DsiCatalogOpt } from './dsiSteward.types';
import { StewardBulkActionInlineForm } from './StewardBulkActionInlineForm';
import type { useDsiBulkSteward } from './useDsiBulkSteward';

type BulkSteward = ReturnType<typeof useDsiBulkSteward>;

/** @deprecated Prefer {@link StewardBulkActionInlineForm} with engine testIds. */
export function DsiBulkActionInlineForm({
  bulk,
  regions,
  channels,
  onCancel,
}: {
  bulk: BulkSteward;
  regions: DsiCatalogOpt[];
  channels: DsiCatalogOpt[];
  onCancel: () => void;
}) {
  return (
    <StewardBulkActionInlineForm
      bulk={bulk}
      regions={regions}
      channels={channels}
      onCancel={onCancel}
      testIds={DSI_ENGINE_CONFIG.bulkTestIds}
      renderMapCustomerFields={(args) => <DsiCustomerSearchFields {...args} />}
    />
  );
}
