# Launch addendum (coordinator, 25 Nov): session root vs worktree

The EIF guard refuses agents whose session root is a linked worktree (`IDENTITY_TOOL: WORKTREE_ROOT_UNSUPPORTED`) and says to open the agent at `C:\Users\warren_eliason\channel-intelligence-platform` and reach the worktree from there. This session therefore starts at that root. This replaces "your worktree is your current directory" and "never `cd`" in the common brief; everything else in it stands.

- Your session root is the main checkout. You must not edit, switch, stash, reset, clean, commit in or run installs/builds in it (it is the live deploy checkout). Read access there is fine (the guard files, `docs/`, `apps/api/.venv`).
- Every edit, write, commit, build, test, install and `program.py --project` call targets YOUR worktree, through absolute paths (`C:\Users\warren_eliason\channel-intelligence-platform\.worktrees\<name>\...`), `git -C <worktree>`, `pnpm --dir <worktree>`, and for web checks `node <worktree>\apps\web\node_modules\...` with the working-directory option of the tool (or a subshell `(cd <worktree>\apps\web && ...)`), never a bare relative path.
- Before the first edit, run `git -C <worktree> rev-parse --abbrev-ref HEAD` and confirm it is your branch. Before every commit run `git -C <worktree> status --short` and stage explicit paths only.
- `.worktrees/` is inside the root's folder but is a separate checkout; edits there are not edits to the main checkout.
- If a guard denial still happens for any other reason, stop that action, record the exact reason code in the tracker, continue with whatever is not blocked, and say so in the hand-back.
