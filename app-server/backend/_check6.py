import json, os

tables_dir = '/Volumes/SYRAID/RAG_Files/data/tables/053c8cdb97f1'
for fname in os.listdir(tables_dir):
    with open(os.path.join(tables_dir, fname)) as f:
        d = json.load(f)
    filename = d.get('filename', '?')
    file_id = d.get('file_id', '?')
    table_count = len(d.get('tables', []))
    # Get table titles
    titles = [t.get('title','?') for t in d.get('tables', [])]
    print(f"{file_id[:16]}... | {filename:50s} | {table_count} tables: {titles[:3]}")
