# N-0035 ledger close

Stage 2.2 (`a4fe957`, grid-scoped 13px) and Stage 2.3 (`459f4c9`, comfortable density 40/40) landed outside the ledger. GOV-008 `GOV008_N0035_20260924` already recorded ux, a11y, rendered, and referent passes.

The close on 2026-09-29 was refused because the node had no `implementation_run`. This pass adds an implementation baseline and stamps `node.stage -> implement` so that recorded review can satisfy the provenance gate. It does not change the type token or the density numbers.
