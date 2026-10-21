"""Drop the one lease-release event that the log cannot replay."""
from pathlib import Path

path = Path(".eif/program/PROGRAM_LOG.ndjson")
lines = path.read_text(encoding="utf-8").splitlines()
last = lines[-1]
if '"seq":1945' not in last or "node.lease.release" not in last or "N-0109" not in last:
    raise SystemExit("last line is not the N-0109 release")
path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8", newline="\n")
print("trimmed_to", lines[-2][:80])
