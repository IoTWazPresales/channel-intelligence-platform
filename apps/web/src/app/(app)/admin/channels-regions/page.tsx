'use client';

import { Alert, Tab, Tabs } from '@mui/material';
import { useState } from 'react';

import { DataChrome } from '@/features/data-stewardship/DataChrome';
import {
  CatalogDimensionGridPanel,
  type CatalogDimensionGridConfig,
} from '@/features/admin/CatalogDimensionGridPanel';

const CHANNEL_CONFIG: CatalogDimensionGridConfig = {
  dimensionTitle: 'Channel',
  tableName: 'dim_channel',
  listPath: '/api/v1/catalog/channels',
  deletePath: (id) => `/api/v1/catalog/channels/${id}`,
  bulkPreviewPath: '/api/v1/catalog/channels/bulk-delete-preview',
  bulkConfirmPath: '/api/v1/catalog/channels/bulk-delete-confirm',
  queryKey: 'admin-catalog-channels',
  entityLabel: 'channels',
  deleteConfirmMessage:
    'Delete this channel from the catalogue? Rows in products, customers, sell-out, and planning that still reference this code will block the delete.',
};

const REGION_CONFIG: CatalogDimensionGridConfig = {
  dimensionTitle: 'Region',
  tableName: 'dim_region',
  listPath: '/api/v1/catalog/regions',
  deletePath: (id) => `/api/v1/catalog/regions/${id}`,
  bulkPreviewPath: '/api/v1/catalog/regions/bulk-delete-preview',
  bulkConfirmPath: '/api/v1/catalog/regions/bulk-delete-confirm',
  queryKey: 'admin-catalog-regions',
  entityLabel: 'regions',
  deleteConfirmMessage:
    'Delete this region from the catalogue? Customers and locations that still reference this region will block the delete.',
};

export default function AdminChannelsRegionsPage() {
  const [tab, setTab] = useState(0);

  return (
    <DataChrome>
      <Alert severity="info" sx={{ mb: 2 }}>
        Govern channel and region dimensions used across product defaults, customer classification, and import
        mapping. Use bulk actions to preview reference blockers before deleting multiple rows.
      </Alert>
      <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }}>
        <Tab label="Channels" />
        <Tab label="Regions" />
      </Tabs>
      {tab === 0 ? <CatalogDimensionGridPanel config={CHANNEL_CONFIG} /> : null}
      {tab === 1 ? <CatalogDimensionGridPanel config={REGION_CONFIG} /> : null}
    </DataChrome>
  );
}
