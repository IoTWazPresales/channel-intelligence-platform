import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8001"

with open(".eif/audit/GOV008_N0033_20260924/get_routes_v1.txt", "r", encoding="utf-8") as f:
    routes = [line.strip() for line in f if line.strip()]

results = []
non_401 = []
for path in routes:
    url = BASE + path
    req = urllib.request.Request(url, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:
        code = f"ERR:{e}"
    results.append((path, code))
    if code != 401:
        non_401.append((path, code))

with open(".eif/audit/GOV008_N0033_20260924/enumeration_results.txt", "w", encoding="utf-8") as f:
    for path, code in results:
        f.write(f"{code}\t{path}\n")

print(f"TOTAL_ROUTES_TESTED={len(results)}")
print(f"NON_401_COUNT={len(non_401)}")
for path, code in non_401:
    print(f"NON_401: {code} {path}")
