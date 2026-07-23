'use client';

import type { ReactNode } from 'react';
import { Box } from '@mui/material';

export type StewardWorkspaceViewportShellProps = {
  /** Candidate list / filters / pagination column (scrolls inside viewport on md+). */
  left: ReactNode;
  /** Optional steward drawer; sticky beside the list on md+. */
  drawer?: ReactNode | null;
  rootTestId?: string;
  minHeight?: number;
  /**
   * Shipment mounts a bordered workspace chrome; DSI uses an unbordered row.
   * Behavioural layout (viewport cap) is identical either way.
   */
  bordered?: boolean;
};

/**
 * Two-column steward workspace shell: left column is viewport-capped on md+
 * so the candidate table scrolls inside the workspace and the sticky drawer
 * stays on-screen (DSI pattern). Used by DSI, shipment, and CPOR historical.
 */
export function StewardWorkspaceViewportShell({
  left,
  drawer = null,
  rootTestId = 'steward-workspace-viewport-shell',
  minHeight = 360,
  bordered = false,
}: StewardWorkspaceViewportShellProps) {
  return (
    <Box
      data-testid={rootTestId}
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', md: 'row' },
        alignItems: 'stretch',
        gap: 0,
        minHeight,
        ...(bordered
          ? {
              border: '1px solid',
              borderColor: 'divider',
              borderRadius: 1,
              overflow: 'hidden',
            }
          : {}),
      }}
    >
      <Box
        data-testid={`${rootTestId}-left`}
        sx={{
          flex: 1,
          minWidth: 0,
          minHeight: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5,
          maxHeight: { md: 'calc(100vh - 120px)' },
          overflow: { md: 'hidden' },
          ...(bordered ? { p: 2 } : {}),
        }}
      >
        {left}
      </Box>
      {drawer}
    </Box>
  );
}
