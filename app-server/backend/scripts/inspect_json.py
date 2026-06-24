import json

json_path = "/Volumes/SYRAID/RAG_Files/data/tables/7e80966d0bf2/b5ec2ed0598af9fb2ef3b840d071ff75.json"
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

table = data['tables'][0]
print("Title:", table['title'])
print("Headers:", table['headers'])
print("Total rows:", len(table['rows']))

print("\n--- Rows 0 to 15 ---")
for idx, r in enumerate(table['rows'][:16]):
    print(f"Row {idx+1}: {r}")
