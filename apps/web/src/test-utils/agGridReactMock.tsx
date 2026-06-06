import React from 'react';

/** Minimal AG Grid React mock with api surface used by admin grid pages. */
export function createAgGridReactMock() {
  return {
    AgGridReact: (props: Record<string, unknown>) => {
      (globalThis as unknown as { __agGridLastProps?: Record<string, unknown> }).__agGridLastProps = props;
      const rowData = (props.rowData as unknown[] | undefined) ?? [];
      const gridOptions = props.gridOptions as { onGridReady?: (e: { api: unknown }) => void } | undefined;
      const api = {
        getDisplayedRowCount: () => rowData.length,
        getSelectedRows: () => [] as unknown[],
        deselectAll: () => undefined,
        exportDataAsCsv: () => undefined,
        getColumnState: () => [] as unknown[],
        applyColumnState: () => undefined,
        setColumnsVisible: () => undefined,
        getColumns: () => [] as unknown[],
        forEachNodeAfterFilterAndSort: (
          cb: (node: { data?: unknown; setSelected: (v: boolean) => void }) => void
        ) => {
          rowData.forEach((row) => cb({ data: row, setSelected: () => undefined }));
        },
      };
      React.useEffect(() => {
        gridOptions?.onGridReady?.({ api });
      }, [gridOptions, rowData.length]);
      return React.createElement('div', {
        'data-testid': 'ag-grid-mock',
        'data-has-row-selection': props.rowSelection ? 'yes' : 'no',
        'data-displayed-rows': String(rowData.length),
      });
    },
  };
}
