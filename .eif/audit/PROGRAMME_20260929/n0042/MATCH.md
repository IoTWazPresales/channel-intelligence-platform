# N-0042 — saved grid views

2026-09-29. The earlier chrome stored the find text only. This pass stores the layout.

## Storage

Named views stay in `cip.grid.<gridId>.views.v1`. Each view holds the find text, the picker column list, AG Grid column state (order, hide, width, sort, pin), and the filter model.

Applying a view writes the picker list back through `useFactColumns.replaceOptionalFields`, which persists `cip.grid.<gridId>.optional.v1`. That is the N-0034 layout key. The view list is not a second live layout.

Older find-only views still load. They do not clear columns.

All clears the find text and the grid filters. It does not wipe the picker columns.

Delete removes the named view and returns to All.

## Browser

Rebuilt web (`BUILD_ID 5SsAWwTHaVl0Gr47rIieU`) and restarted `next start` on :3000. Warren was already signed in.

On `/roadmap` (empty grid): Save view was enabled with an empty Find. Saved "Empty check". The chip survived a reload. Selecting it showed Delete view. Delete removed the chip.

On `/stock?lens=movement` Sell-out: the same Save view and Export sit on the Scope bar next to Search SKU / product / customer. The grid was still loading, so a column-sort round trip on live rows was not clicked.
