'use client';

import { Card, CardActionArea, CardContent, Stack, Typography } from '@mui/material';
import NextLink from 'next/link';

import { StatusChip } from '@/features/workbench-ui/controls';

export type ImportJobCardRow = {
  id: number;
  file_name: string;
  status: string;
  template_slug?: string | null;
};

function tone(status: string): 'danger' | 'warning' | 'success' | 'info' | 'neutral' {
  if (status === 'failed' || status === 'validation_failed') return 'danger';
  if (status === 'pending') return 'warning';
  if (status === 'completed') return 'success';
  if (status === 'validated') return 'info';
  return 'neutral';
}

export function ImportJobCards({ rows }: { rows: ImportJobCardRow[] }) {
  return (
    <Stack spacing={1} data-testid="import-job-cards">
      {rows.map((j) => (
        <Card key={j.id} variant="outlined" sx={{ boxShadow: 'none' }}>
          <CardActionArea component={NextLink} href={`/admin/imports?job=${j.id}`}>
            <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
              <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={1}>
                <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                  {j.file_name}
                </Typography>
                <StatusChip label={j.status} tone={tone(j.status)} />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                #{j.id} · {j.template_slug || '—'}
              </Typography>
            </CardContent>
          </CardActionArea>
        </Card>
      ))}
    </Stack>
  );
}
