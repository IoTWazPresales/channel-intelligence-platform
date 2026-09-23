"""Read-only SQL helper. Usage: python ro_sql.py [--db NAME] "SQL" ["SQL" ...]
Prints current_database() first; session is read-only."""
import sys, psycopg
args = sys.argv[1:]
db = "cip"
if args and args[0] == "--db":
    db = args[1]; args = args[2:]
conn = psycopg.connect(host="localhost", port=5432, user="cip", password="cip", dbname=db)
conn.read_only = True
cur = conn.cursor()
cur.execute("select current_database()"); print("current_database() =", cur.fetchone()[0])
for q in args:
    print("--", q.strip().splitlines()[0][:160])
    cur.execute(q)
    if cur.description:
        cols = [d[0] for d in cur.description]; print(" | ".join(cols))
        for r in cur.fetchall(): print(" | ".join("" if v is None else str(v) for v in r))
conn.rollback(); conn.close()
