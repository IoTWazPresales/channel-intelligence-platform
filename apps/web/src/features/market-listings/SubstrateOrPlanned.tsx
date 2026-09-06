'use client';

import { Box, Chip, Stack, Typography } from '@mui/material';

import { CapabilityStatus } from '@/features/shell/CapabilityStatus';
import type { LeafStatus } from '@/features/shell/navConfig';
import { Panel } from '@/features/workbench-ui/Panel';

export function SubstrateOrPlanned({
  status,
  title,
  body,
  related,
}: {
  status: Extract<LeafStatus, 'substrate' | 'planned'>;
  title: string;
  body: string;
  related: { label: string; href: string }[];
}) {
  return (
    <Box data-testid={`lens-${status}`} sx={{ mt: 2 }}>
      <Panel
        title={
          <Stack direction="row" spacing={1} alignItems="center">
            <span>{title}</span>
            <CapabilityStatus status={status} />
          </Stack>
        }
      >
        <Stack spacing={1.5} sx={{ maxWidth: 760 }}>
          <Typography variant="body2" color="text.secondary">
            {body}
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {related.map((r) => (
              <Chip key={r.href} component="a" href={r.href} clickable size="small" label={r.label} variant="outlined" />
            ))}
          </Stack>
        </Stack>
      </Panel>
    </Box>
  );
}
