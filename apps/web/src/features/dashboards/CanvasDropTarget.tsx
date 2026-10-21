'use client';

import { useDroppable } from '@dnd-kit/core';
import { Box } from '@mui/material';
import type { ReactNode } from 'react';

/** The dashboard canvas: metrics dragged from the metric list drop here to open the widget editor. */
export function CanvasDropTarget({ children }: { children: ReactNode }) {
  const { setNodeRef, isOver } = useDroppable({ id: 'dashboard-canvas' });
  return (
    <Box
      ref={setNodeRef}
      data-testid="dashboard-canvas"
      sx={{
        minHeight: 320,
        outline: isOver ? '2px dashed' : 'none',
        outlineColor: 'primary.main',
        borderRadius: 1,
      }}
    >
      {children}
    </Box>
  );
}
