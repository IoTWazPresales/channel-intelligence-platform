'use client';

import { Box, Typography } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';

import { CporCaseWorkspace } from '@/features/cpor/CporCaseWorkspace';

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
          borderLeft: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
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
        borderLeft: `1px solid ${alpha(theme.palette.common.white, 0.12)}`,
        minHeight: 0,
      }}
    >
      <CporCaseWorkspace caseId={caseId} embedded defaultTab={4} />
    </Box>
  );
}
