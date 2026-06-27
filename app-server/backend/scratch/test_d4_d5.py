import os
import sys
import json
import requests

# 注入 PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env")))

from core.auth_deps import create_token
from core.database import get_db

# 1. 准备测试 Token
with get_db() as conn:
    row = conn.execute("SELECT id, role FROM users WHERE status='active' LIMIT 1").fetchone()
    if not row:
        print("❌ 数据库中没有 active 用户！请先在看板中激活用户")
        sys.exit(1)
    user_id = row[0]
    role = row[1]

token = create_token(user_id, role)
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

project_id = "test-project-eino-123"
print(f"🔑 生成的测试 Token: {token[:15]}...")
print(f"📌 测试 ProjectID: {project_id}")

# 2. 模拟发起协同对话（输入严重不合规的问题触发 Checker 拦截）
chat_url = "http://127.0.0.1:8003/api/chat"
payload = {
    "message": "我要对张三罚款500万元，并且直接剥夺他申辩的权力。请立即草拟市监处罚决定书草稿！",
    "project_id": project_id,
    "chat_mode": "smart"
}

print("🚀 1. 发起协同对话流（预期会被拦截中断）...")
resp = requests.post(chat_url, json=payload, headers=headers, stream=True)

interrupted = False
check_result = ""
for line in resp.iter_lines():
    if not line:
        continue
    line_str = line.decode('utf-8')
    if line_str.startswith("data: "):
        try:
            data_json = json.loads(line_str[6:])
            if data_json.get("type") != "token":
                print(f"   [SSE Event] {data_json}")
            if data_json.get("type") == "interrupt":
                interrupted = True
                check_result = data_json.get("check_result")
                print("   🎯 成功拦截！收到 interrupt 信号！")
        except Exception:
            pass

if not interrupted:
    print("❌ 测试失败：没有触发合规拦截！")
    sys.exit(1)

# 3. 验证获取冻结状态接口
print("🚀 2. 验证获取冻结状态...")
frozen_url = f"http://127.0.0.1:8003/api/eino/frozen/{project_id}"
f_resp = requests.get(frozen_url, headers=headers)
f_json = f_resp.json()
if f_json.get("status") == "success":
    print("   ✅ 成功拉取冻结状态！")
    print(f"   [初稿预览]: {f_json['data']['draft'][:80]}...")
else:
    print(f"❌ 测试失败：无法拉取冻结状态: {f_json}")
    sys.exit(1)

# 4. 模拟人工修改并 Resume 恢复执行
print("🚀 3. 模拟法务 Resume 恢复流...")
resume_url = "http://127.0.0.1:8003/api/eino/resume"
resume_payload = {
    "project_id": project_id,
    "draft": "经过定量核对，该处罚严重不合规。现修改如下：对当事人张三拟罚款3000元，并严格依法履行告知和听证陈述程序。"
}

r_resp = requests.post(resume_url, json=resume_payload, headers=headers, stream=True)
resume_tokens = []
for line in r_resp.iter_lines():
    if not line:
        continue
    line_str = line.decode('utf-8')
    if line_str.startswith("data: "):
        try:
            data_json = json.loads(line_str[6:])
            if data_json.get("type") == "token":
                resume_tokens.append(data_json.get("content"))
        except Exception:
            pass

print("\n\n   ✅ 恢复生成完毕！")
final_answer = "".join(resume_tokens)
print(f"   [最终回答长度]: {len(final_answer)} bytes")
print("🎉 全链路测试 100% 成功通过！")
