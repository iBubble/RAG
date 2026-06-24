import sqlite3

# Check rag.db tables
conn = sqlite3.connect('rag.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
print("=== rag.db tables ===")
for r in c.fetchall():
    print(f'  {r[0]}')
conn.close()

# Check rag_metadata.db 
print("\n=== rag_metadata.db tables ===")
conn2 = sqlite3.connect('/app/data/rag_metadata.db')
c2 = conn2.cursor()
c2.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
for r in c2.fetchall():
    print(f'  {r[0]}')
conn2.close()

# Check /app/backend/.data/rag.db
import os
for dbpath in ['/app/backend/.data/rag.db', '/app/backend/data/rag.db', '/app/data/rag.db']:
    if os.path.exists(dbpath):
        print(f"\n=== {dbpath} exists, size={os.path.getsize(dbpath)} ===")
        conn3 = sqlite3.connect(dbpath)
        c3 = conn3.cursor()
        c3.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        for r in c3.fetchall():
            print(f'  {r[0]}')
        conn3.close()
