"""Patch docs/memory/CURRENT.md for N-0111 repair 2. Exact-match replaces; fails loudly."""

import pathlib

p = pathlib.Path("docs/memory/CURRENT.md")
s = p.read_text(encoding="utf-8")


def sub(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)


sub(
    "Reloading the same invoice lines replaces their figures and keeps the old ones; lines with a new invoice number are added.",
    "Reloading the same invoice lines replaces their figures and keeps the old ones; lines with a new invoice number are added. "
    "Lines repeated inside one file (same distributor, customer, product, date and invoice): lines that differ in any column are "
    "summed; lines identical in every column count once and are flagged duplicate.",
)
sub(
    "A week with no on-hand shows **No on-hand reported** and the next report shows **Chain restarts**.",
    "A week with sales but no on-hand shows **No on-hand reported** and is not compared itself; the next report is compared across it "
    "(last on-hand + matched deliveries - all sales in between). When sales are also missing for a week in between, the next report "
    "shows **Unreported weeks** (a data gap, nothing compared) and the chain starts fresh.",
)
sub(
    "**N-0111 repair (2026-10-16), at verify,",
    "**N-0111 repair 2 (2026-10-16), at verify, VERIFIED_WITH_LIMITATIONS, operator acceptance pending:** Warren's D-0112 to D-0114 "
    "recorded. **D-0112** the stock chain bridges weeks with no on-hand (corrects D-0105's restart): compared at the next reported "
    "on-hand as last on-hand + matched deliveries - all sales in between, when sales are reported for every week in between; otherwise "
    "the next report is **Unreported weeks** (stored `chain_restart`, no migration). Weeks with neither on-hand nor sales store no row. "
    "A stock-only row is not a sales week. Partly covered gaps count as unreported (my reading). **D-0113** repeated Pinnacle lines in "
    "one file follow D-0091 (differing lines summed with the later price, identical lines once, flagged `duplicate`; load report counts "
    "them loaded, `repeated_line` is gone; job summary has `summed_lines`, `duplicate_lines`). **D-0114** Compuspeed/Syntech un-merge "
    "PARKED: BACKLOG-212 holds the read-only cip count (shipments 214 of 5,499 OPEN_CHANNEL rows name them in raw text, shipment evidence "
    "lines 1,414 of 31,975, lineup lines 52 of 92; text hits, not proof), the trace file and the trigger (before distributor-level "
    "reporting is shown to users). cip stock positions recomputed once (737 positions; compared 16 / flagged 16 / no on-hand 36 / "
    "unreported weeks 298 / first report 387; was 16 / 16 / 3,457 / 298 / 387 on 4,158 positions): the data has no gap with sales for "
    "every missing week (289 of 298 gaps have no sales row at all), so the bridge compares nothing new today. Full API pytest on cip_test "
    "3041 passed, 21 skipped, 0 failed; full web vitest 187 files 872 passed (2 workers). Commits `0aeffcbc`, `045fd68a`. Web build "
    "`IJmu4NDqQX50Pq1SZ7SkS`; API and web restarted (local /health 200, /login 200). Not rendered (sign-in). Same session, not "
    "independent. N-0099 does the second look. Proof: `.eif/audit/PROGRAMME_20261016/n0111_repair2/N0111R2_PROOF.md`.\n\n"
    "**N-0111 repair (2026-10-16), at verify,",
)
p.write_text(s, encoding="utf-8")
print("patched")
