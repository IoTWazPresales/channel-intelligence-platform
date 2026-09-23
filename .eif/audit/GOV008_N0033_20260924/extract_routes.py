import json, re

with open(".eif/audit/GOV008_N0033_20260924/openapi.json", "r", encoding="utf-8") as f:
    spec = json.load(f)

paths = spec.get("paths", {})
get_routes = []
for path, methods in paths.items():
    if "get" in methods:
        get_routes.append(path)

get_routes.sort()
print(f"TOTAL_GET_ROUTES={len(get_routes)}")

# Substitute path params with 1
def substitute(p):
    return re.sub(r"\{[^}]+\}", "1", p)

with open(".eif/audit/GOV008_N0033_20260924/get_routes.txt", "w", encoding="utf-8") as f:
    for p in get_routes:
        f.write(substitute(p) + "\n")

# Also dump ones under /api/v1
v1 = [p for p in get_routes if p.startswith("/api/v1")]
print(f"V1_GET_ROUTES={len(v1)}")
with open(".eif/audit/GOV008_N0033_20260924/get_routes_v1.txt", "w", encoding="utf-8") as f:
    for p in v1:
        f.write(substitute(p) + "\n")

non_v1 = [p for p in get_routes if not p.startswith("/api/v1")]
print("NON_V1_ROUTES:", non_v1)
