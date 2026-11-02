"""Prints the render metrics (the numbers BATCH3_REPORT.md quotes). Run from the repo root."""
import json

b = json.load(open(".eif/audit/REVIEW_20261102/batch3/renders/builder/metrics.json"))
for k, v in b.items():
    ws = v["widgets"]
    print(k, "docOverflow", v["horizontalOverflow"], "cards", len(ws), "textOverlaps", sum(w["textOverlaps"] for w in ws),
          "textSpill", sum(w["textSpill"] for w in ws), "angledBoxOverlaps", sum(w["angledTickBoxOverlaps"] for w in ws))
for tag in ("otw-before", "otw"):
    o = json.load(open(f".eif/audit/REVIEW_20261102/batch3/renders/{tag}/metrics.json"))
    for k, v in o.items():
        l = v["layout"]
        print(tag, k, {x: l[x] for x in ("labelOverlaps", "labelsOutsideMap", "labelsOverPortNames", "noteOverCaption", "noteOverPortNames", "noteOverLabels", "horizontalOverflow")}, "labels", l["labels"])
