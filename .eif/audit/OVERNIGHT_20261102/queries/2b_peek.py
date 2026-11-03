import json, random
d = json.load(open(".eif/audit/OVERNIGHT_20261102/queries/2b_dump_lines.out.json"))
L = d["lines"]; M = d["master"]
random.seed(1)
for r in random.sample(L, 25):
    print({k: r[k] for k in ("item_code","sales_model_name","ean_code","upc_code","mpor_item_no","quantity","tok","distributor")})
print("--- master samples")
for r in random.sample(M, 12):
    print({k: r[k] for k in ("sku","part_number","sales_model_name","model_name","ean","upc","series_name","product_line","category")})
