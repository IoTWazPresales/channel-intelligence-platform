'use client';

import { Alert, Box, Button, CircularProgress, Typography } from '@mui/material';
import type { ComponentProps } from 'react';
import { ReactNode } from 'react';

import { EmptyWorkspace } from '@/components/EmptyWorkspace';

type EmptyProps = ComponentProps<typeof EmptyWorkspace>;

export function ModuleDataSection({
  intro,
  introWhen = 'empty',
  toolbar,
  isLoading = false,
  isError = false,
  error,
  onRetry,
  isEmpty,
  empty,
  children,
  loadingLabel = 'Loading data…',
}: {
  intro?: ReactNode;
  introWhen?: 'always' | 'empty';
  toolbar?: ReactNode;
  isLoading?: boolean;
  isError?: boolean;
  error?: Error | null;
  onRetry?: () => void;
  isEmpty: boolean;
  empty: EmptyProps;
  children: ReactNode;
  loadingLabel?: string;
}) {
  // Data is truly ready to display only when not loading, not errored, and has rows.
  const hasData = !isLoading && !isError && !isEmpty;
  const showDataEmpty = !isLoading && !isError && isEmpty;
  const showIntro =
    intro != null && (introWhen === 'always' || (introWhen === 'empty' && showDataEmpty));

  let body: ReactNode;
  if (isError) {
    body = (
      <Alert
        severity="error"
        role="alert"
        action={
          onRetry ? (
            <Button color="inherit" size="small" onClick={onRetry}>
              Retry
            </Button>
          ) : null
        }
      >
        {error?.message ?? 'Something went wrong. Try refreshing or use Retry.'}
      </Alert>
    );
  } else if (isLoading) {
    body = (
      <Box
        role="status"
        aria-busy="true"
        aria-label={loadingLabel}
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: 360,
          gap: 2,
          borderRadius: 1,
          border: '1px dashed',
          borderColor: 'divider',
          bgcolor: 'action.hover',
        }}
      >
        <CircularProgress size={36} />
        <Typography variant="body2" color="text.secondary">
          {loadingLabel}
        </Typography>
      </Box>
    );
  } else if (showDataEmpty) {
    body = <EmptyWorkspace {...empty} />;
  } else if (hasData) {
    body = children;
  } else {
    // Fallback: any state we didn't anticipate — show empty rather than a blank grid.
    body = <EmptyWorkspace {...empty} />;
  }

  return (
    <>
      {toolbar ? <>{toolbar}</> : null}
      {showIntro ? (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2, maxWidth: 900 }}>
          {intro}
        </Typography>
      ) : null}
      {body}
    </>
  );
}
