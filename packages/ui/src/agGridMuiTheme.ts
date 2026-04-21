import type { Theme } from '@mui/material/styles';
import { alpha } from '@mui/material/styles';

/**
 * Maps the active MUI theme to AG Grid "material" theme CSS variables so data grids
 * follow the same palette, typography, hover, and focus behavior as the rest of the app.
 */
export function getAgGridMuiCssVariables(theme: Theme): Record<string, string | number> {
  const mode = theme.palette.mode;
  const primary = theme.palette.primary.main;
  const secondary = theme.palette.secondary.main;
  const paper = theme.palette.background.paper;
  const textPrimary = theme.palette.text.primary;
  const textSecondary = theme.palette.text.secondary;
  const divider = typeof theme.palette.divider === 'string' ? theme.palette.divider : String(theme.palette.divider);
  const hover = theme.palette.action.hover;
  const selected = alpha(primary, mode === 'dark' ? 0.22 : 0.18);
  const headerLift = mode === 'dark' ? alpha(theme.palette.common.white, 0.06) : alpha(theme.palette.common.black, 0.04);
  const oddStripe = mode === 'dark' ? alpha(theme.palette.common.white, 0.035) : alpha(theme.palette.common.black, 0.025);
  const font =
    typeof theme.typography.fontFamily === 'string'
      ? theme.typography.fontFamily
      : (theme.typography.fontFamily as string[] | undefined)?.join(',') ??
        'Inter, "Segoe UI", system-ui, sans-serif';
  const fontSize = typeof theme.typography.body2?.fontSize === 'string' ? theme.typography.body2.fontSize : '0.8125rem';
  const radius = typeof theme.shape?.borderRadius === 'number' ? `${theme.shape.borderRadius}px` : '8px';

  return {
    '--ag-material-primary-color': primary,
    '--ag-material-accent-color': secondary,
    '--ag-font-family': font,
    '--ag-font-size': fontSize,
    '--ag-foreground-color': textPrimary,
    '--ag-data-color': textPrimary,
    '--ag-secondary-foreground-color': textSecondary,
    '--ag-disabled-foreground-color': alpha(textPrimary, 0.38),
    '--ag-background-color': paper,
    '--ag-header-background-color': headerLift,
    '--ag-header-foreground-color': textSecondary,
    '--ag-tooltip-background-color': paper,
    '--ag-odd-row-background-color': oddStripe,
    '--ag-row-hover-color': hover,
    '--ag-column-hover-color': hover,
    '--ag-selected-row-background-color': selected,
    '--ag-range-selection-border-color': primary,
    '--ag-range-selection-background-color': alpha(primary, 0.12),
    '--ag-range-selection-background-color-2': alpha(primary, 0.18),
    '--ag-range-selection-background-color-3': alpha(primary, 0.24),
    '--ag-range-selection-background-color-4': alpha(primary, 0.3),
    '--ag-border-color': divider,
    '--ag-secondary-border-color': divider,
    '--ag-header-cell-hover-background-color': alpha(primary, mode === 'dark' ? 0.08 : 0.06),
    '--ag-control-panel-background-color': paper,
    '--ag-subheader-background-color': alpha(paper, 0.92),
    '--ag-subheader-toolbar-background-color': alpha(paper, 0.85),
    '--ag-panel-background-color': paper,
    '--ag-menu-background-color': paper,
    '--ag-modal-overlay-background-color': alpha(theme.palette.common.black, mode === 'dark' ? 0.55 : 0.4),
    '--ag-side-button-selected-background-color': alpha(primary, 0.14),
    '--ag-checkbox-background-color': paper,
    '--ag-checkbox-checked-color': primary,
    '--ag-checkbox-unchecked-color': textSecondary,
    '--ag-input-border-color': divider,
    '--ag-input-focus-border-color': primary,
    '--ag-input-disabled-border-color': alpha(divider, 0.55),
    '--ag-input-disabled-background-color': alpha(paper, 0.5),
    '--ag-chip-background-color': alpha(primary, mode === 'dark' ? 0.12 : 0.1),
    '--ag-selected-tab-underline-color': primary,
    '--ag-selected-tab-underline-width': '2px',
    '--ag-invalid-color': theme.palette.error.main,
    '--ag-value-change-delta-up-color': theme.palette.success.main,
    '--ag-value-change-delta-down-color': theme.palette.error.main,
    '--ag-borders': 'solid 1px',
    '--ag-borders-critical': 'solid 1px',
    '--ag-border-radius': '0px',
    '--ag-wrapper-border-radius': '0px',
    '--ag-card-radius': radius,
    '--ag-row-height': theme.density === 'compact' ? '34px' : '42px',
    '--ag-header-height': theme.density === 'compact' ? '36px' : '42px',
    '--ag-grid-size': theme.density === 'compact' ? '6px' : '8px',
    '--ag-cell-horizontal-padding': theme.spacing(1.5),
    '--ag-icon-size': '18px',
    '--ag-input-focus-box-shadow': `0 0 0 2px ${alpha(primary, 0.25)}`,
    '--ag-card-shadow': theme.shadows[4] ?? 'none',
    '--ag-row-border-width': '1px',
    '--ag-header-column-separator-color': alpha(divider, 0.6),
    '--ag-row-border-color': divider,
  };
}

/** Global styles for MUI `<Table />` (TableContainer is themed in `createEnterpriseTheme`). */
export function getDataDisplayGlobalStyles(theme: Theme) {
  const paper = theme.palette.background.paper;
  const headerBg =
    theme.palette.mode === 'dark'
      ? alpha(theme.palette.common.white, 0.06)
      : alpha(theme.palette.common.black, 0.04);

  const agBodySelector = [
    '.ag-theme-material .ag-body-viewport',
    '.ag-theme-material-dark .ag-body-viewport',
    '.ag-theme-material .ag-center-cols-viewport',
    '.ag-theme-material-dark .ag-center-cols-viewport',
    '.ag-theme-material .ag-body-horizontal-scroll-viewport',
    '.ag-theme-material-dark .ag-body-horizontal-scroll-viewport',
    '.ag-theme-material .ag-body',
    '.ag-theme-material-dark .ag-body',
    '.ag-theme-material .ag-center-cols-container',
    '.ag-theme-material-dark .ag-center-cols-container',
    '.ag-theme-material .ag-overlay',
    '.ag-theme-material-dark .ag-overlay',
    '.ag-theme-material .ag-overlay-wrapper',
    '.ag-theme-material-dark .ag-overlay-wrapper',
  ].join(', ');

  return {
    '.MuiTable-root': {
      fontFamily: theme.typography.fontFamily,
      color: theme.palette.text.primary,
      backgroundColor: paper,
    },
    '.MuiTableCell-root': {
      borderColor: theme.palette.divider,
      color: theme.palette.text.primary,
    },
    '.MuiTableHead-root .MuiTableCell-root': {
      fontWeight: theme.typography.fontWeightMedium ?? 500,
      color: theme.palette.text.secondary,
      backgroundColor:
        theme.palette.mode === 'dark'
          ? alpha(theme.palette.common.white, 0.04)
          : alpha(theme.palette.common.black, 0.03),
    },
    '.MuiTableBody-root .MuiTableRow-root:hover': {
      backgroundColor: theme.palette.action.hover,
    },
    '.MuiTableBody-root .MuiTableRow-root.Mui-selected': {
      backgroundColor: alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.18 : 0.12),
    },
    // AG Grid v33 ships hardcoded white backgrounds in ag-theme-material.css that beat
    // CSS-variable overrides.  Force every internal surface to match the MUI dark palette.
    '.ag-theme-material, .ag-theme-material-dark': {
      '--ag-background-color': `${paper} !important`,
      '--ag-header-background-color': `${headerBg} !important`,
    },
    '.ag-theme-material .ag-root-wrapper, .ag-theme-material-dark .ag-root-wrapper': {
      backgroundColor: `${paper} !important`,
      color: `${theme.palette.text.primary} !important`,
    },
    [agBodySelector]: {
      backgroundColor: `${paper} !important`,
    },
    '.ag-theme-material .ag-row, .ag-theme-material-dark .ag-row': {
      backgroundColor: `${paper} !important`,
    },
    '.ag-theme-material .ag-row-odd, .ag-theme-material-dark .ag-row-odd': {
      backgroundColor: `${theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.035)' : 'rgba(0,0,0,0.025)'} !important`,
    },
    '.ag-theme-material .ag-overlay-no-rows-wrapper, .ag-theme-material-dark .ag-overlay-no-rows-wrapper': {
      backgroundColor: `${paper} !important`,
    },
    '.ag-theme-material .ag-cell, .ag-theme-material-dark .ag-cell': {
      color: `${theme.palette.text.primary} !important`,
    },
    '.ag-theme-material .ag-header-cell, .ag-theme-material-dark .ag-header-cell': {
      color: `${theme.palette.text.secondary} !important`,
    },
  };
}
