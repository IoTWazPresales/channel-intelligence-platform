# VERIFY seed — <UNIT_ID>

Branch: <BRANCH> @ <SHORT_SHA> (pushed)
Unit prompt: .tmp/<UNIT_ID>_cursor_prompt.md
Changed paths (git diff --name-only <BASE>..HEAD):
<PATH_LIST>

Waiver lines copied verbatim from the unit prompt (empty if none):
<WAIVER_LINES>

## Your task
You are the independent verifier. Do not trust this seed's framing, Cursor's
report, or any checklist — they are claims. Open the files yourself.

1. Read docs/STEWARD_EXPERIENCE_CONTRACT.md (version header included below must
   match the file; if not, STOP: stale seed).
2. For EACH row S1–S14: locate the shipped implementation in the tree at
   path:line, compare COMPARATIVELY against the row's behavior column, and grade
   PASS / PARTIAL / ABSENT / WAIVED.
3. Grade evidence rules: imports are not evidence; filled props/behavior are.
   Tests green is not evidence of a slot. Docs/commits saying done are claims.
4. REQUIRED row PARTIAL or ABSENT without a matching waiver line → VERDICT: STOP,
   naming the row(s) and the missing behavior.
5. Output: the S1–S14 table with path:line per row, then a single final line
   `VERDICT: PASS` or `VERDICT: STOP`.

Contract version expected: <CONTRACT_VERSION>
