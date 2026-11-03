"""Offline viewer (no database access) for 3_keys.out.json."""
import json

d = json.load(open(".eif/audit/OVERNIGHT_20261102/queries/3_keys.out.json"))
for k in ("fact_key_shape", "applied_lines_vs_site_keys", "site_like_payload_keys_all_customers", "job900_vs_files_sites"):
    print("==", k)
    for r in d[k]:
        print(r)
for r in d["job900_meta"]:
    print(r["id"], r["file_name"], json.dumps(r["meta"])[:900])
    print("  parse", json.dumps(r["parse"])[:400])
    print("  headers", json.dumps(r["file_headers"])[:300])
