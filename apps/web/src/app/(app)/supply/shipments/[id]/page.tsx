'use client';

import { Alert } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'next/navigation';

import { ModuleDataSection } from '@/components/ModuleDataSection';
import { ShipmentReceiptView, type ShipmentReceipt } from '@/features/supply-inbound/ShipmentReceiptView';
import { SupplyChrome } from '@/features/supply-inbound/SupplyChrome';
import { apiGet, safeDisplayError } from '@/lib/api';

export default function ShipmentReceiptPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const query = useQuery({
    queryKey: ['shipment-receipt', id],
    queryFn: ({ signal }) => apiGet<ShipmentReceipt>(`/api/v1/shipping/shipments/${id}`, { signal }),
    enabled: Boolean(id),
  });

  return (
    <SupplyChrome>
      <ModuleDataSection
        isLoading={query.isPending}
        isError={query.isError}
        error={query.isError ? new Error(safeDisplayError(query.error)) : null}
        onRetry={() => void query.refetch()}
        isEmpty={!query.data}
        empty={{ title: 'Shipment not found', description: 'This shipment is not on the current list.' }}
      >
        {query.data ? <ShipmentReceiptView receipt={query.data} /> : <Alert severity="info">Loading</Alert>}
      </ModuleDataSection>
    </SupplyChrome>
  );
}
