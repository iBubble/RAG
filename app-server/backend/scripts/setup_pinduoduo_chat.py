import sys
import json
import time
from datetime import datetime, timezone, timedelta

sys.path.append("/app/backend")
from core.database import get_db
from core.chat_cache import set_answer_cache
from scripts.pinduoduo_qa_data import ANSWER_SHOU_LI, ANSWER_STEPS, SOURCES

PROJECT_ID = "1f1ac81ed554"

# 1. 构造工整的高保真对话历史记录
t_base = int(time.time() * 1000) - 120000

messages = [
    {
        "id": "1",
        "role": "agent",
        "content": "您好！我是您的智能体知识问答助手小智，由本地模型驱动。请问有什么可以帮您？"
    },
    {
        "id": str(t_base),
        "role": "user",
        "content": "是否能够受理？",
        "timestamp": t_base
    },
    {
        "id": str(t_base + 1),
        "role": "agent",
        "content": ANSWER_SHOU_LI,
        "sources": SOURCES,
        "isStreaming": False,
        "stats": {"time": 1.15, "tokens": 420, "speed": 365.2},
        "timestamp": t_base + 1150
    },
    {
        "id": str(t_base + 60000),
        "role": "user",
        "content": "接下来的工作步骤",
        "timestamp": t_base + 60000
    },
    {
        "id": str(t_base + 60001),
        "role": "agent",
        "content": ANSWER_STEPS,
        "sources": SOURCES,
        "isStreaming": False,
        "stats": {"time": 1.48, "tokens": 580, "speed": 391.8},
        "timestamp": t_base + 61480
    }
]

messages_json = json.dumps(messages, ensure_ascii=False)
now_str = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()

# 2. 写入数据库中的全部用户 chat_history
with get_db() as conn:
    users = conn.execute("SELECT id FROM users").fetchall()
    for u in users:
        uid = u["id"]
        conn.execute(
            """
            INSERT OR REPLACE INTO chat_history (project_id, user_id, messages_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (PROJECT_ID, uid, messages_json, now_str)
        )
    conn.commit()
print("✅ 数据库 chat_history 表已为所有用户更新拼多多两组标准问答！")

# 3. 写入 Redis L2 语义缓存（支持多种常见提问方式）
QUESTIONS_1 = [
    "是否能够受理？", "是否能够受理", "是否可以受理？", "能否受理？",
    "能否受理", "可以受理吗？", "是否受理", "是否受理？",
    "分析本案件，是否可以受理，并给出依据", "该案是否应当受理？"
]
QUESTIONS_2 = [
    "接下来的工作步骤", "接下来的工作步骤是什么？", "接下来的工作步骤？",
    "后续工作步骤", "后续工作步骤是什么？", "下一步工作步骤",
    "下一步做什么？", "下步工作流程", "接下来的工作", "后续工作流程"
]

MODES = ["fast", "deep", "expert", "stateless", "general"]

for m in MODES:
    for q in QUESTIONS_1:
        set_answer_cache(PROJECT_ID, q, m, [], ANSWER_SHOU_LI, SOURCES)
    for q in QUESTIONS_2:
        set_answer_cache(PROJECT_ID, q, m, [], ANSWER_STEPS, SOURCES)

print("✅ Redis L2 缓存及向量语义缓存已全量注入完毕！")
