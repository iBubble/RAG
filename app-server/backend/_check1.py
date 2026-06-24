import sqlite3

conn = sqlite3.connect('rag.db')
c = conn.cursor()

print("=== Projects ===")
c.execute('SELECT id, name, status FROM projects ORDER BY created_at DESC LIMIT 5')
for r in c.fetchall():
    print(f'  id={r[0][:20]} name={r[1]} status={r[2]}')

print("\n=== 毗卢 files ===")
c.execute("SELECT id, filename, status, chunk_count, project_id FROM files WHERE filename LIKE '%毗卢%'")
for r in c.fetchall():
    print(f'  id={r[0][:20]} file={r[1]} status={r[2]} chunks={r[3]} project={r[4][:20] if r[4] else None}')

print("\n=== All files with chunk_count ===")
c.execute("SELECT project_id, filename, status, chunk_count FROM files ORDER BY project_id, filename")
for r in c.fetchall():
    print(f'  proj={r[0][:16] if r[0] else "None":16s} file={r[1]:50s} status={r[2]:12s} chunks={r[3]}')

conn.close()
