'use client';

import type { ColDef } from 'ag-grid-community';
import { Chip, Stack, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';
import { ModuleDataSection } from '@/components/ModuleDataSection';
import { apiGet } from '@/lib/api';

type QualityCell = 'pass' | 'flag' | 'no_data' | string;

type QualityRow = {
  listing_id: number;
  marketplace: string;
  flag_count: number;
  fetched_at: string | null;
  price_and_stock: QualityCell;
  price_and_stock_evidence: string;
  title: QualityCell;
  title_evidence: string;
  images: QualityCell;
  images_evidence: string;
  description: QualityCell;
  description_evidence: string;
  key_specs: QualityCell;
  key_specs_evidence: string;
  buy_box: QualityCell;
  buy_box_evidence: string;
  reviews: QualityCell;
  reviews_evidence: string;
};

const COLUMNS: { field: keyof QualityRow; evidence: keyof QualityRow; header: string }[] = [
  { field: 'price_and_stock', evidence: 'price_and_stock_evidence', header: 'Price and stock' },
  { field: 'title', evidence: 'title_evidence', header: 'Title' },
  { field: 'images', evidence: 'images_evidence', header: 'Images' },
  { field: 'description', evidence: 'description_evidence', header: 'Description' },
  { field: 'key_specs', evidence: 'key_specs_evidence', header: 'Key specs' },
  { field: 'buy_box', evidence: 'buy_box_evidence', header: 'Buy box' },
  { field: 'reviews', evidence: 'reviews_evidence', header: 'Reviews' },
];

function cellLabel(status: QualityCell): string {
  if (status === 'flag') return 'Flag';
  if (status === 'pass') return 'Pass';
  return 'No data';
}

export function ListingQualityLens() {
  const [selected, setSelected] = useState<QualityRow | null>(null);
  const query = useQuery({
    queryKey: ['listing-capture', 'quality'],
    queryFn: ({ signal }) => apiGet<{ items: QualityRow[] }>('/api/v1/listing-capture/quality', { signal }),
  });
  const rows = query.data?.items ?? [];
  const columnDefs = useMemo<ColDef<QualityRow>[]>(() => {
    const checks: ColDef<QualityRow>[] = COLUMNS.map((col) => ({
      field: col.field,
      headerName: col.header,
      valueFormatter: (p) => cellLabel(String(p.value ?? 'no_data')),
      tooltipValueGetter: (p) => String(p.data?.[col.evidence] ?? 'No data'),
      cellRenderer: (p: { value?: string }) => {
        const status = String(p.value ?? 'no_data');
        if (status === 'flag') return <Chip size="small" label="Flag" color="warning" />;
        return cellLabel(status);
      },
    }));
    return [
      { field: 'listing_id', headerName: 'Listing', width: 110 },
      { field: 'marketplace', headerName: 'Retailer', width: 130 },
      { field: 'flag_count', headerName: 'Flags', width: 90 },
      { field: 'fetched_at', headerName: 'Last check', flex: 1 },
      ...checks,
    ];
  }, []);

  return (
    <Stack spacing={1.5} sx={{ mt: 2 }}>
      <Typography variant="body2" color="text.secondary">
        Checks use the last stored snapshot for Takealot and Evetech. A flag is amber and does not block anything.
        Missing fields say No data. Amazon is not checked. Search position is deferred.
      </Typography>
      <ModuleDataSection
        isLoading={query.isLoading}
        isError={query.isError}
        error={query.isError ? new Error('Listing quality could not be loaded.') : null}
        isEmpty={!query.isLoading && rows.length === 0}
        empty={{ title: 'No listings', description: 'No monitored listings to check.' }}
      >
        <EnterpriseDataGrid<QualityRow>
          rowData={rows}
          columnDefs={columnDefs}
          height={420}
          gridOptions={{ onRowClicked: (event) => setSelected(event.data ?? null) }}
        />
      </ModuleDataSection>
      {selected ? (
        <Stack spacing={0.5}>
          <Typography variant="subtitle2">Listing {selected.listing_id}</Typography>
          {COLUMNS.map((col) => (
            <Typography key={col.field} variant="body2">
              {col.header}: {cellLabel(String(selected[col.field]))}. {String(selected[col.evidence])}
            </Typography>
          ))}
        </Stack>
      ) : null}
    </Stack>
  );
}
