"""N-0039 discovery: small polite GET sample (<=3 per marketplace + <=3 canonical Takealot). Read-only."""
import re, time, httpx

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-ZA,en;q=0.9"}
URLS = [
    ("takealot", "stored id52 sku222547542", "https://www.takealot.com/PLID222547542"),
    ("takealot", "stored id55 sku233951759", "https://www.takealot.com/PLID233951759"),
    ("takealot", "stored id122 sku203053235", "https://www.takealot.com/PLID203053235"),
    ("takealot", "canonical x/ id52 plid98174082", "https://www.takealot.com/x/PLID98174082"),
    ("takealot", "canonical slug id52", "https://www.takealot.com/asus-zenscreen-mb169ck-15-6-inch-fhd-ips-portable-monitor/PLID98174082"),
    ("amazon", "stored id1", "https://www.amazon.co.za/dp/B0DGGBSFZR"),
    ("amazon", "stored id2", "https://www.amazon.co.za/dp/B0C6CWMX2F"),
    ("amazon", "stored id3", "https://www.amazon.co.za/dp/B0CND6Z887"),
    ("evetech", "stored id76", "https://www.evetech.co.za/asus-laptops/laptops-for-sale/40354"),
    ("evetech", "stored id77", "https://www.evetech.co.za/asus-laptops/laptops-for-sale/40394"),
    ("evetech", "stored id78", "https://www.evetech.co.za/asus-laptops/laptops-for-sale/42030"),
]
MARKERS = [r"doesn.t exist", r"page not found", r"we couldn.t find", r"looking for something",
           r"Page Not Found", r"404", r"no longer available", r"Sorry! We couldn"]
with httpx.Client(headers=H, follow_redirects=True, timeout=30) as c:
    for i, (m, label, u) in enumerate(URLS):
        if i:
            time.sleep(4)
        try:
            r = c.get(u)
            body = r.text
            t = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
            title = (t.group(1).strip()[:90] if t else "")
            hits = [k for k in MARKERS if re.search(k, body[:200000], re.I)]
            print(f"{m}\t{label}\t{r.status_code}\t{r.url}\t{title!r}\tmarkers={hits}\tlen={len(body)}")
        except Exception as e:
            print(f"{m}\t{label}\tERR\t{type(e).__name__}: {e}")
