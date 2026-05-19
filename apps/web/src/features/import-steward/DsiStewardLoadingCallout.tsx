'use client';

import { Alert, CircularProgress, LinearProgress, Stack, Typography } from '@mui/material';

/** Slow DSI steward operations — message + progress so the UI does not feel frozen. */
export function DsiStewardLoadingCallout({
  message,
  detail,
  testId = 'dsi-steward-loading-callout',
}: {
  message: string;
  detail?: string;
  testId?: string;
}) {
  return (
    <Alert severity="info" variant="outlined" icon={false} data-testid={testId}>
      <Stack spacing={1} sx={{ width: '100%' }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <CircularProgress size={22} aria-label="Loading" />
          <Typography variant="body2">{message}</Typography>
        </Stack>
        {detail ? (
          <Typography variant="caption" color="text.secondary">
            {detail}
          </Typography>
        ) : null}
        <LinearProgress
          variant="indeterminate"
          color="primary"
          sx={{
            width: '100%',
            height: 6,
            borderRadius: 1,
            bgcolor: 'action.hover',
            '& .MuiLinearProgress-bar': {
              borderRadius: 1,
            },
          }}
        />
      </Stack>
    </Alert>
  );
}
