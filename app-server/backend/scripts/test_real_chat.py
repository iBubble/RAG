import requests
import json
import time

url = "http://localhost:8003/api/chat"
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwYjg0Mzk3ZS0yMzhmLTQwMWMtODMxMS01MjI5OGExZWM1ZDMiLCJ1c2VybmFtZSI6Ilx1N2NmYlx1N2VkZlx1N2JhMVx1NzQwNlx1NTQ1OCIsInJvbGUiOiJhZG1pbiIsImV4cCI6MTc4ODg4NDYyNn0.DYNt31vDcH6Mp7YU7GhtSs8HiKDc3MnTgf1pN1Ejdj0"

payload = {
    "message": "分析本案件，是否可以受理，并给出依据",
    "project_id": "case_beef_2026",
    "model": "qwen3.8:27b-q4",
    "chat_mode": "deep",
    "file_ids": []
}

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

print("🚀 开始请求 /api/chat...")
t0 = time.time()
r = requests.post(url, json=payload, headers=headers, stream=True, timeout=120)
print(f"Status: {r.status_code}, 响应建立耗时: {time.time()-t0:.2f}s")

first_token = False
full_text = []
for line in r.iter_lines():
    if line:
        decoded = line.decode('utf-8')
        if decoded.startswith('data: '):
            try:
                data = json.loads(decoded[6:])
                tok = data.get("token") or data.get("content")
                if tok:
                    if not first_token:
                        print(f"⚡ 首字耗时: {time.time()-t0:.2f}s\n--- 答案正文 ---")
                        first_token = True
                    print(tok, end='', flush=True)
                    full_text.append(tok)
            except Exception:
                pass
print(f"\n\n🏁 完成！总耗时: {time.time()-t0:.2f}s, 生成字数: {sum(len(t) for t in full_text)}")
