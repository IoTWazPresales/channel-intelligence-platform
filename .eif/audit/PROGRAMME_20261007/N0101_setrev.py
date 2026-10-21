"""Set expected_revision in an N-0101 payload file: python N0101_setrev.py <file> <rev>."""
import json
import sys

p, rev = sys.argv[1], int(sys.argv[2])
d = json.load(open(p, encoding="utf-8"))
d["expected_revision"] = rev
json.dump(d, open(p, "w", encoding="utf-8"))
print(p, rev)
