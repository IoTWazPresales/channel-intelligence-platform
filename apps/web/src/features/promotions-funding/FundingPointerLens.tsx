'use client';

import { Box } from '@mui/material';

import { ModuleDataSection } from '@/components/ModuleDataSection';

/** Lab FundingSurface claims/payments/pricing lenses: one centred pointer, not a second workflow. */
export function FundingPointerLens({
  testId,
  title,
  description,
  primary,
  secondary,
}: {
  testId: string;
  title: string;
  description: string;
  primary: { label: string; href: string };
  secondary?: { label: string; href: string };
}) {
  return (
    <Box sx={{ mt: 2 }} data-testid={testId}>
      <ModuleDataSection
        isEmpty
        empty={{
          title,
          description,
          primary,
          secondary,
        }}
      >
        <span />
      </ModuleDataSection>
    </Box>
  );
}
