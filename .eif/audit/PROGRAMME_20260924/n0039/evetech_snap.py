"""N-0039: read stored Evetech snapshots (read-only) for page identity."""
import re, zlib, gzip, psycopg
c = psycopg.connect(host="localhost", port=5432, user="cip", password="cip", dbname="cip"); c.read_only = True
cur = c.cursor()
cur.execute("""select l.id, l.url, o.fetched_at::date, o.raw_snapshot, o.extracted_price from listing_observation o join customer_listing l on l.id=o.listing_id
 where l.id in (76,77,78) order by l.id""")
for lid, url, d, blob, price in cur.fetchall():
    b = bytes(blob)
    try: t = gzip.decompress(b).decode("utf-8", "replace")
    except Exception: t = zlib.decompress(b).decode("utf-8", "replace")
    ti = re.search(r"<title[^>]*>(.*?)</title>", t, re.S | re.I)
    can = re.search(r'<link[^>]+rel="canonical"[^>]*>', t)
    print(lid, d, price, len(t), repr(ti.group(1)[:90] if ti else ""), can.group(0)[:160] if can else "")
c.rollback()
