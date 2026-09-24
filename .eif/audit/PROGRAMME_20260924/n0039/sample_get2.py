"""N-0039: 3rd (final) extra Takealot request - valid PLID without slug. Saves body for marker analysis."""
import re, httpx
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
u = "https://www.takealot.com/PLID98174082"
r = httpx.get(u, headers={"User-Agent": UA, "Accept": "text/html"}, follow_redirects=True, timeout=30)
b = r.text
open(__file__.replace("sample_get2.py", "tkl_valid_plid_noslug.html"), "w", encoding="utf-8").write(b)
t = re.search(r"<title[^>]*>(.*?)</title>", b, re.S | re.I)
print(r.status_code, r.url, len(b), repr(t.group(1)[:80] if t else ""), [h.url for h in r.history])
for pat in [r'<link rel="canonical"[^>]*>', r'og:title"[^>]*>', r'noindex', r'PLID98174082']:
    print(pat, re.findall(pat, b)[:2])
