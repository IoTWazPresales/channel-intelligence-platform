'use client';

import type { MouseEvent } from 'react';
import {
  Alert,
  Backdrop,
  Box,
  Checkbox,
  CircularProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import type { ImportStewardCandidateRowBase, ImportStewardCandidateWorkspaceProps } from './importStewardCandidateWorkspace.types';
import { ImportStewardCandidateWorkspaceSkeleton } from './ImportStewardCandidateWorkspaceSkeleton';

export function ImportStewardCandidateWorkspace<TRow extends ImportStewardCandidateRowBase>({
  listDomainId,
  importJobId,
  copy,
  openRows,
  filteredRows,
  isLoading,
  busy,
  busyOverlay,
  skeletonRowCount,
  columns,
  selection,
  tabsSlot,
  filtersSlot,
  bulkFormSlot,
  toolbarSlot,
  actionFeedback,
  getRowSx,
  rootTestId = 'import-steward-candidate-workspace',
  filtersRegionTestId,
  filtersRegionAriaLabel,
  onRowClick,
  embedded = false,
  keepTableWhenFilterEmpty = false,
  mainContentSlot,
}: ImportStewardCandidateWorkspaceProps<TRow>) {
  const showEmptyOpen =
    importJobId != null && !isLoading && openRows.length === 0 && !keepTableWhenFilterEmpty;
  const showTable =
    importJobId != null && !isLoading && (openRows.length > 0 || keepTableWhenFilterEmpty);
  const showFilteredEmptyInsideTable = showTable && filteredRows.length === 0;

  const headerChecked =
    selection?.headerState === 'all'
      ? true
      : selection?.headerState === 'partial'
        ? false
        : false;
  const headerIndeterminate = selection?.headerState === 'partial';

  const colSpan = (selection ? 1 : 0) + columns.length;

  const scrollBody = mainContentSlot ? (
    <Box
      data-testid="import-steward-candidate-workspace-main-content"
      sx={
        embedded
          ? { flex: 1, minHeight: 0, overflow: 'auto', pr: 0.5 }
          : undefined
      }
    >
      {mainContentSlot}
    </Box>
  ) : null;

  const shell = (
      <Stack
        spacing={2}
        sx={embedded ? { flex: 1, minHeight: 0, minWidth: 0 } : undefined}
      >
        {copy.title ? (
          <Typography variant="h6" component="div">
            {copy.title}
          </Typography>
        ) : null}
        {copy.description ? (
          <Typography variant="body2" color="text.secondary">
            {copy.description}
          </Typography>
        ) : null}
        {importJobId == null && copy.missingJobPrompt ? <Box>{copy.missingJobPrompt}</Box> : null}
        {tabsSlot ? <Box data-testid="import-steward-candidate-workspace-tabs">{tabsSlot}</Box> : null}
        {actionFeedback ? (
          <Alert
            severity={actionFeedback.severity}
            onClose={actionFeedback.onDismiss}
            data-testid="import-steward-candidate-workspace-action-feedback"
          >
            {actionFeedback.message}
          </Alert>
        ) : null}
        {toolbarSlot ? <Box data-testid="import-steward-candidate-workspace-toolbar">{toolbarSlot}</Box> : null}
        {bulkFormSlot ? <Box data-testid="import-steward-candidate-workspace-bulk-form">{bulkFormSlot}</Box> : null}
        {filtersSlot ? (
          <Box
            data-testid={filtersRegionTestId}
            role="region"
            aria-label={filtersRegionAriaLabel ?? 'Filter mapping candidates'}
          >
            {filtersSlot}
          </Box>
        ) : null}
        {scrollBody}
        {mainContentSlot == null && importJobId != null && isLoading ? (
          <Stack spacing={1.5} data-testid="import-steward-candidate-workspace-loading">
            {copy.loadingMessage ? (
              <Typography variant="body2" color="text.secondary">
                {copy.loadingMessage}
              </Typography>
            ) : copy.loadingLabel ? (
              <Typography variant="body2" color="text.secondary">
                {copy.loadingLabel}
              </Typography>
            ) : null}
            <ImportStewardCandidateWorkspaceSkeleton
              columnCount={columns.length}
              hasSelection={Boolean(selection)}
              rowCount={skeletonRowCount}
            />
          </Stack>
        ) : null}
        {mainContentSlot == null && showEmptyOpen ? (
          <Typography variant="body2" color="text.secondary">
            {copy.emptyOpenListMessage ?? 'No open mapping candidates for this job.'}
          </Typography>
        ) : null}
        {mainContentSlot == null && showTable ? (
          <Box
            sx={{
              position: 'relative',
              ...(embedded ? { flex: 1, minHeight: 0, overflow: 'auto', pr: 0.5 } : undefined),
            }}
          >
            <Backdrop
              sx={{
                color: 'text.primary',
                position: 'absolute',
                zIndex: 1,
                borderRadius: 1,
                flexDirection: 'column',
                gap: 1,
              }}
              open={busy && openRows.length > 0}
            >
              <CircularProgress color="inherit" size={28} />
              {busyOverlay?.message ? (
                <Typography variant="body2" sx={{ px: 2, textAlign: 'center', maxWidth: 360 }}>
                  {busyOverlay.message}
                </Typography>
              ) : null}
            </Backdrop>
            <TableContainer sx={{ maxWidth: '100%' }}>
            <Table size="small" stickyHeader sx={{ opacity: busy && openRows.length > 0 ? 0.55 : 1 }}>
              <TableHead>
                <TableRow>
                  {selection ? (
                    <TableCell padding="checkbox">
                      <Checkbox
                        size="small"
                        indeterminate={headerIndeterminate}
                        checked={headerChecked}
                        onChange={() => selection.onToggleAllVisible()}
                        inputProps={{ 'aria-label': 'Select all visible candidates' }}
                      />
                    </TableCell>
                  ) : null}
                  {columns.map((c) => (
                    <TableCell key={c.id} align={c.align === 'right' ? 'right' : c.align === 'center' ? 'center' : 'left'}>
                      {c.header}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {showFilteredEmptyInsideTable ? (
                  <TableRow>
                    <TableCell colSpan={colSpan}>
                      <Typography variant="body2" color="text.secondary">
                        {openRows.length === 0
                          ? (copy.emptyOpenListMessage ??
                            'No open mapping candidates for this import job.')
                          : (copy.emptyFilteredMessage ??
                            'No rows match the current filters. Clear filters or pick a different combination.')}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredRows.map((r) => {
                    const rowSx = getRowSx?.(r);
                    return (
                    <TableRow
                      key={r.id}
                      sx={rowSx ?? (selection || onRowClick ? { cursor: 'pointer' } : undefined)}
                      onClick={(e: MouseEvent<HTMLTableRowElement>) => {
                        const el = e.target as HTMLElement;
                        if (el.closest('input[type="checkbox"]') || el.closest('.MuiCheckbox-root')) return;
                        if (el.closest('button') || el.closest('a') || el.closest('[role="button"]')) return;
                        if (selection) {
                          selection.onToggle(r.id, e);
                          return;
                        }
                        if (onRowClick) onRowClick(r);
                      }}
                    >
                      {selection ? (
                        <TableCell padding="checkbox" onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            size="small"
                            checked={selection.selectedIds.has(r.id)}
                            onClick={(e) => {
                              e.stopPropagation();
                              selection.onToggle(r.id, e);
                            }}
                            inputProps={{ 'aria-label': `Select candidate ${r.id}` }}
                          />
                        </TableCell>
                      ) : null}
                      {columns.map((c) => (
                        <TableCell
                          key={c.id}
                          align={c.align === 'right' ? 'right' : c.align === 'center' ? 'center' : 'left'}
                          sx={c.cellSx}
                        >
                          {c.cell(r)}
                        </TableCell>
                      ))}
                    </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>
            </TableContainer>
          </Box>
        ) : null}
      </Stack>
  );

  if (embedded) {
    return (
      <Box
        data-testid={rootTestId}
        data-list-domain={listDomainId}
        sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, minWidth: 0 }}
      >
        {shell}
      </Box>
    );
  }

  return (
    <Paper sx={{ p: 2 }} data-testid={rootTestId} data-list-domain={listDomainId}>
      {shell}
    </Paper>
  );
}
