import sqlite3

db_path = '/Volumes/SYRAID/RAG_Files/shengyao.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in c.fetchall()]
print("=== All tables ===")
for t in tables:
    print(f"  {t}")
    c.execute(f"SELECT COUNT(*) FROM \"{t}\"")
    cnt = c.fetchone()[0]
    print(f"    rows: {cnt}")

# Get all projects properly
c.execute("SELECT * FROM projects")
rows = c.fetchall()
col_names = [d[0] for d in c.description]
print(f"\n=== Projects ({len(rows)} rows, cols={col_names}) ===")
for row in rows:
    for i, val in enumerate(row):
        print(f"  {col_names[i]}: {val}")
    print("  ---")

# Check operation_logs table for file references
c.execute("PRAGMA table_info(operation_logs)")
print("\n=== operation_logs schema ===")
for r in c.fetchall():
    print(f"  {r}")

c.execute("SELECT COUNT(*) FROM operation_logs")
print(f"  rows: {c.fetchone()[0]}")

# Check operation_logs for ingest/ingestion
c.execute("SELECT * FROM operation_logs WHERE operation LIKE '%ingest%' LIMIT 3")
col_names = [d[0] for d in c.description]
for row in c.fetchall():
    for i, val in enumerate(row):
        print(f"    {col_names[i]}: {str(val)[:80]}")

conn.close()
