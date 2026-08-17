/** Client-side AG Grid paging for ops lists not on MasterDataGridShell (BACKLOG-085). */
export const OPS_LIST_PAGE_SIZE = 25;
export const OPS_LIST_PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

export const OPS_LIST_GRID_PAGINATION = {
  pagination: true as const,
  paginationPageSize: OPS_LIST_PAGE_SIZE,
  paginationPageSizeSelector: [...OPS_LIST_PAGE_SIZE_OPTIONS],
};
