'use client';

import {
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
} from '@mui/material';

const DEFAULT_ROW_COUNT = 8;

/** Skeleton rows aligned with `ImportStewardCandidateWorkspace` table layout. */
export function ImportStewardCandidateWorkspaceSkeleton({
  columnCount,
  hasSelection = true,
  rowCount = DEFAULT_ROW_COUNT,
}: {
  columnCount: number;
  hasSelection?: boolean;
  rowCount?: number;
}) {
  const colSpan = (hasSelection ? 1 : 0) + columnCount;

  return (
    <TableContainer sx={{ maxWidth: '100%' }} data-testid="import-steward-candidate-workspace-skeleton">
      <Table size="small">
        <TableHead>
          <TableRow>
            {hasSelection ? (
              <TableCell padding="checkbox">
                <Skeleton variant="rectangular" width={18} height={18} />
              </TableCell>
            ) : null}
            {Array.from({ length: columnCount }).map((_, i) => (
              <TableCell key={`h-${i}`}>
                <Skeleton variant="text" width={i === 2 ? 120 : 72} />
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {Array.from({ length: rowCount }).map((_, rowIdx) => (
            <TableRow key={rowIdx}>
              {hasSelection ? (
                <TableCell padding="checkbox">
                  <Skeleton variant="rectangular" width={18} height={18} />
                </TableCell>
              ) : null}
              {Array.from({ length: columnCount }).map((_, colIdx) => (
                <TableCell key={`${rowIdx}-${colIdx}`}>
                  <Skeleton
                    variant="text"
                    width={colIdx === 2 ? '90%' : colIdx === 5 ? '70%' : '55%'}
                  />
                  {colIdx === 2 ? <Skeleton variant="text" width="40%" sx={{ mt: 0.5 }} /> : null}
                </TableCell>
              ))}
            </TableRow>
          ))}
          <TableRow sx={{ visibility: 'hidden', height: 0, lineHeight: 0 }}>
            <TableCell colSpan={colSpan} sx={{ p: 0, border: 0 }} />
          </TableRow>
        </TableBody>
      </Table>
    </TableContainer>
  );
}
