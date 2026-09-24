'use client';

import { getAgGridMuiCssVariables } from '@cip/ui';
import { AllCommunityModule, ModuleRegistry } from 'ag-grid-community';
import type { ColDef, GridOptions } from 'ag-grid-community';
import { AgGridReact } from 'ag-grid-react';
import { Box } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { usePathname } from 'next/navigation';
import type { CSSProperties, ForwardedRef, ReactElement } from 'react';
import { forwardRef, useMemo } from 'react';

import { gridDensityCssVars, gridRowMetrics } from '@/theme/gridDensity';

import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-material.css';

ModuleRegistry.registerModules([AllCommunityModule]);

type Props<T> = {
  rowData: T[];
  columnDefs: ColDef<T>[];
  height?: number | string;
  gridOptions?: GridOptions<T>;
};

function EnterpriseDataGridInner<T>(
  { rowData, columnDefs, height = 480, gridOptions }: Props<T>,
  ref: ForwardedRef<AgGridReact<T>>
) {
  const pathname = usePathname();
  const theme = useTheme();
  const isDark = theme.palette.mode === 'dark';

  const agVars = useMemo(() => getAgGridMuiCssVariables(theme), [theme]);

  /** Inline custom properties beat `ag-theme-material*.css` so grids match the active MUI palette. */
  const agVarsInline = useMemo(() => {
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(agVars)) {
      out[k] = typeof v === 'number' ? String(v) : v;
    }
    // Row/header heights come from the one source in `@/theme/gridDensity`; setting them here means
    // the CSS variables and the AgGridReact props below are always the same numbers.
    Object.assign(out, gridDensityCssVars(theme.density));
    return out as CSSProperties;
  }, [agVars, theme.density]);

  const { rowHeight, headerHeight } = gridRowMetrics(theme.density);

  const defaultColDef = useMemo<ColDef>(
    () => ({
      sortable: true,
      filter: true,
      resizable: true,
      floatingFilter: false,
      tooltipValueGetter: (p) => {
        const v = p.valueFormatted ?? p.value;
        if (v == null || v === '') return undefined;
        return String(v);
      },
    }),
    []
  );

  const { rowSelection, onRowClicked, ...restGridOptions } = gridOptions ?? {};
  const clickableRows = typeof onRowClicked === 'function';

  const shellSx = useMemo(
    () => ({
      // `&&` bumps specificity so MUI-driven variables win over ag-theme-material defaults
      '&&': {
        ...agVars,
        width: '100%',
        height,
        borderRadius: 0,
        overflow: 'hidden',
        border: `1px solid ${theme.palette.divider}`,
        backgroundColor: `${theme.palette.background.paper} !important`,
        '& .ag-root-wrapper': {
          border: 'none',
          borderRadius: 0,
          backgroundColor: `${theme.palette.background.paper} !important`,
        },
        '& .ag-body-viewport, & .ag-center-cols-viewport, & .ag-body-horizontal-scroll-viewport, & .ag-body, & .ag-center-cols-container, & .ag-overlay, & .ag-overlay-wrapper, & .ag-overlay-no-rows-wrapper':
          {
            backgroundColor: `${theme.palette.background.paper} !important`,
          },
        '& .ag-row': {
          backgroundColor: `${theme.palette.background.paper} !important`,
          cursor: clickableRows ? 'pointer' : 'default',
        },
        '& .ag-cell': {
          display: 'flex',
          alignItems: 'center',
          overflow: 'hidden',
          minWidth: 0,
        },
        '& .ag-cell-wrapper, & .ag-cell-value': {
          minWidth: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        },
        '& .ag-row-odd': {
          backgroundColor: `${isDark ? 'rgba(255,255,255,0.035)' : 'rgba(0,0,0,0.025)'} !important`,
        },
        '& .ag-header, & .ag-header-viewport': {
          backgroundColor: `var(--ag-header-background-color, ${theme.palette.background.paper}) !important`,
        },
      },
    }),
    [agVars, theme, height, isDark, clickableRows]
  );

  const gridClass = isDark ? 'ag-theme-material-dark' : 'ag-theme-material';
  const agGridInstanceKey = `${pathname ?? '_'}_${rowSelection ? 'bulk-select' : 'normal'}`;

  return (
    <Box className={gridClass} sx={shellSx} style={agVarsInline}>
      <AgGridReact
        ref={ref}
        key={agGridInstanceKey}
        rowData={rowData}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        animateRows
        headerHeight={headerHeight}
        rowHeight={rowHeight}
        {...restGridOptions}
        enableCellTextSelection
        ensureDomOrder
        onRowClicked={onRowClicked}
        rowSelection={rowSelection}
        theme="legacy"
      />
    </Box>
  );
}

/** Preserve row-type generics through forwardRef (default forwardRef collapses T → unknown). */
export const EnterpriseDataGrid = forwardRef(EnterpriseDataGridInner) as <T>(
  props: Props<T> & { ref?: ForwardedRef<AgGridReact<T>> }
) => ReactElement | null;
