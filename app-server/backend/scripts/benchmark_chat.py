import asyncio
import sys
import time
sys.path.append("/app/backend")

from core.config import settings
from api.generate import ChatRequest, chat

async def main():
    print("🔍 测试智能助手对话请求: 分析本案件，是否可以受理，并给出依据")
    t0 = time.time()
    req = ChatRequest(
        message="分析本案件，是否可以受理，并给出依据",
        project_id="case_beef_2026",
        model="qwen3.8:27b-q4",
        chat_mode="deep",
        file_ids=[]
    )
    user = {"role": "admin", "username": "admin", "id": "admin"}
    
    t_start = time.time()
    resp = await chat(req, user)
    print(f"⏱️ 获取响应对象耗时: {time.time() - t_start:.2f}s")
    
    token_count = 0
    async for chunk in resp.body_iterator:
        token_count += 1
        if token_count <= 5 or token_count % 50 == 0:
            print(f"[{time.time() - t0:.2f}s] Chunk #{token_count}: {chunk[:60]}")
    print(f"🎉 全部完成，总耗时: {time.time() - t0:.2f}s, 总chunks: {token_count}")

if __name__ == "__main__":
    asyncio.run(main())
