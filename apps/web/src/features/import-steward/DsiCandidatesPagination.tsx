'use client';

import { FormControl, InputLabel, MenuItem, Select, Stack, Typography } from '@mui/material';

import { DsiPendingButton } from './DsiPendingButton';
import { DSI_CANDIDATE_PAGE_SIZE_OPTIONS, type DsiCandidatePageSize } from './dsiCandidatesQuery';

export function DsiCandidatesPagination({
  page,
  pageCount,
  pageSize,
  total,
  skip,
  pageItemCount,
  busy,
  onPageChange,
  onPageSizeChange,
}: {
  page: number;
  pageCount: number;
  pageSize: DsiCandidatePageSize;
  total: number;
  skip: number;
  pageItemCount: number;
  busy?: boolean;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: DsiCandidatePageSize) => void;
}) {
  const from = total === 0 ? 0 : skip + 1;
  const to = skip + pageItemCount;

  return (
    <Stack
      direction={{ xs: 'column', sm: 'row' }}
      spacing={1}
      alignItems={{ sm: 'center' }}
      justifyContent="space-between"
      flexWrap="wrap"
      useFlexGap
      data-testid="dsi-candidates-pagination"
    >
      <Typography variant="caption" color="text.secondary">
        Showing {from}–{to} of {total} candidates
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <FormControl size="small" sx={{ minWidth: 120 }}>
          <InputLabel id="dsi-candidates-page-size">Rows per page</InputLabel>
          <Select
            labelId="dsi-candidates-page-size"
            label="Rows per page"
            value={String(pageSize)}
            onChange={(e) => onPageSizeChange(Number(e.target.value) as DsiCandidatePageSize)}
            disabled={busy}
          >
            {DSI_CANDIDATE_PAGE_SIZE_OPTIONS.map((n) => (
              <MenuItem key={n} value={String(n)}>
                {n}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
        <DsiPendingButton
          size="small"
          variant="outlined"
          disabled={page <= 0 || busy}
          onClick={() => onPageChange(page - 1)}
          data-testid="dsi-candidates-prev-page"
        >
          Previous
        </DsiPendingButton>
        <Typography variant="caption" color="text.secondary" sx={{ px: 0.5 }}>
          Page {page + 1} of {pageCount}
        </Typography>
        <DsiPendingButton
          size="small"
          variant="outlined"
          disabled={page + 1 >= pageCount || busy}
          onClick={() => onPageChange(page + 1)}
          data-testid="dsi-candidates-next-page"
        >
          Next
        </DsiPendingButton>
      </Stack>
    </Stack>
  );
}
