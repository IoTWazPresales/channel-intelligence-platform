'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

import { SettlementDeskLive } from '@/features/settlement/SettlementDeskLive';

type Props = {
  caseId: number | null;
};

export function SettlementCasePane({ caseId }: Props) {
  const theme = useTheme();

  if (!caseId) {
    return (
      <Box
        data-testid="settlement-case-empty"
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: 240,
          color: alpha(theme.palette.text.primary, 0.45),
          borderLeft: `1px solid ${theme.palette.divider}`,
        }}
      >
        <Typography variant="body2">Select a case from the queue</Typography>
      </Box>
    );
  }

  return (
    <Box
      data-testid="settlement-case-pane"
      sx={{
        height: '100%',
        overflow: 'auto',
        borderLeft: `1px solid ${theme.palette.divider}`,
        minHeight: 0,
      }}
    >
      <SettlementDeskLive caseId={caseId} embedded />
    </Box>
  );
}
