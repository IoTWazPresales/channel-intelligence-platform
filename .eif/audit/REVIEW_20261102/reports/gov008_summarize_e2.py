import json
import sys

d = json.load(open(sys.argv[1], encoding="utf-8"))
for block in d:
    for r in block.get("pure", []):
        print("PURE", repr(r["label"]), "cover", r["cover_A1"], "label", r["label_cell"], "xml<f>", r["xml_formula"], "type_f", r["any_f"])
    if block.get("pure"):
        print("PURE numbers", block["pure"][0]["numbers"])
    for r in block.get("http", []):
        print("HTTP", repr(r["label"]), r["path"], "cells", r["label_cells"], r["label_types"], "cover", r["cover_A1"],
              "formula", r["any_formula"], "hdr", r["data_header"], "B", r["data_B_types"])
