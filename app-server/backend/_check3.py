import sqlite3, json, os

db_path = '/Volumes/SYRAID/RAG_Files/shengyao.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

# List tables
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in c.fetchall()]
print("=== Tables ===")
for t in tables:
    print(f"  {t}")

# Check projects
if 'projects' in tables:
    print("\n=== Projects ===")
    c.execute("SELECT id, name, status, created_at FROM projects ORDER BY created_at DESC LIMIT 5")
    for r in c.fetchall():
        print(f"  id={r[0]} name={r[1]} status={r[2]} created={r[3]}")

# Check files
if 'files' in tables:
    print("\n=== Files (project 053c8cdb97f1) ===")
    c.execute("SELECT id, filename, status, chunk_count, file_size FROM files WHERE project_id='053c8cdb97f1' ORDER BY filename")
    for r in c.fetchall():
        print(f"  id={r[0][:16]}... file={r[1]:45s} status={r[2]:12s} chunks={r[3]:5s} size={r[4]}")

# Check for 毗卢 file specifically
print("\n=== 毗卢 files ===")
c.execute("SELECT id, filename, status, chunk_count, file_size, project_id FROM files WHERE filename LIKE '%毗卢%'")
rows = c.fetchall()
for r in rows:
    print(f"  id={r[0][:20]}... file={r[1]} status={r[2]} chunks={r[3]} size={r[4]} project={r[5][:16] if r[5] else None}")

conn.close()

# Also check table registry
tables_dir = '/Volumes/SYRAID/RAG_Files/data/tables'
if os.path.exists(tables_dir):
    print(f"\n=== Tables dir ===")
    for sub in os.listdir(tables_dir):
        subpath = os.path.join(tables_dir, sub)
        if os.path.isdir(subpath):
            count = len(os.listdir(subpath))
            print(f"  {sub}: {count} json files")

# Check the specific project table file
proj_table_dir = os.path.join(tables_dir, '053c8cdb97f1')
if os.path.exists(proj_table_dir):
    print(f"\n=== Table files for project 053c8cdb97f1 ===")
    for f in os.listdir(proj_table_dir):
        print(f"  {f}")
