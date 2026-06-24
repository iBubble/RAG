import sqlite3, json, os

db_path = '/Volumes/SYRAID/RAG_Files/shengyao.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check projects schema
c.execute("PRAGMA table_info(projects)")
print("=== projects schema ===")
for r in c.fetchall():
    print(f"  {r}")

c.execute("SELECT * FROM projects LIMIT 5")
rows = c.fetchall()
cols = [d[1] for d in c.description]
print(f"\n=== projects rows ({len(rows)}) ===")
for row in rows:
    print(f"  {dict(zip(cols, row))}")

# Check files schema and data
c.execute("PRAGMA table_info(files)")
print("\n=== files schema ===")
for r in c.fetchall():
    print(f"  {r}")

# Find 毗卢 file
c.execute("SELECT * FROM files WHERE filename LIKE '%毗卢%'")
rows = c.fetchall()
cols = [d[1] for d in c.description]
print(f"\n=== 毗卢 files ({len(rows)}) ===")
for row in rows:
    print(f"  {dict(zip(cols, row))}")

# All files
c.execute("SELECT id, filename, project_id FROM files ORDER BY project_id, filename")
rows = c.fetchall()
print(f"\n=== All files ({len(rows)}) ===")
for r in rows:
    print(f"  proj={r[2][:16] if r[2] else None:16s} id={r[0][:16]}... file={r[1]:50s}")

conn.close()
